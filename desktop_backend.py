#!/usr/bin/env python3
"""
Persistent JSON bridge for the Electron desktop app.

The process stays alive across prompts so Playwright, browser context, and the
active provider session remain warm instead of cold-starting for every request.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper import (
    Config,
    ScraperEngine,
    build_page_chunks,
    configure_logging,
    extract_pdf_pages,
    get_logger,
    merge_scan_results,
    write_scan_artifacts,
)
from scraper.engine import Tab
from agent_runtime import AgentRuntime
from agent_runtime.models import AgentSettings

log = get_logger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event_type: str, **payload: Any) -> None:
    print(
        json.dumps(
            {"type": event_type, "timestamp": _utc_now(), **payload},
            ensure_ascii=True,
        ),
        flush=True,
    )


class DesktopBackend:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._engine_cm: ScraperEngine | None = None
        self._engine: ScraperEngine | None = None
        self._tab: Tab | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._warm_task: asyncio.Task[None] | None = None
        self._tab_ready = False
        self._running = True
        self._request_seq = 0
        self._agent_runtime: AgentRuntime | None = None
        self._approval_waiters: dict[str, asyncio.Future[str]] = {}

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig.name)
            except NotImplementedError:
                pass

        self._engine_cm = ScraperEngine(self._cfg)
        self._engine = await self._engine_cm.__aenter__()
        self._agent_runtime = AgentRuntime(
            AgentSettings(),
            self._fallback_prompt,
            self._request_approval,
            state_dir=Path(self._cfg.output_dir) / "agent_runtime",
        )

        try:
            await self._ensure_warm_session(force=False)

            while self._running:
                raw = await asyncio.to_thread(sys.stdin.readline)
                if not raw:
                    break

                raw = raw.strip()
                if not raw:
                    continue

                try:
                    command = json.loads(raw)
                except json.JSONDecodeError:
                    _emit("bridge_error", message="Invalid command payload", raw=raw)
                    continue

                await self._handle_command(command)
        finally:
            await self._stop_generation("backend_shutdown", emit_event=False)
            if self._tab is not None:
                await self._tab.close()
                self._tab = None
            if self._engine_cm is not None:
                await self._engine_cm.__aexit__(None, None, None)

    def _handle_signal(self, name: str) -> None:
        log.warning("Signal received: %s", name)
        _emit("signal", signal=name)
        self._running = False

    async def _handle_command(self, command: dict[str, Any]) -> None:
        command_type = str(command.get("type") or "").strip().lower()

        if command_type == "submit":
            prompt = str(command.get("prompt") or "").strip()
            request_id = str(command.get("request_id") or "")
            if not prompt:
                _emit("error", message="Prompt cannot be empty.", request_id=request_id)
                return
            await self._submit(prompt, request_id)
            return

        if command_type == "agent_settings":
            settings = AgentSettings.from_payload(command.get("settings") or {})
            if self._agent_runtime is None:
                self._agent_runtime = AgentRuntime(
                    settings,
                    self._fallback_prompt,
                    self._request_approval,
                    state_dir=Path(self._cfg.output_dir) / "agent_runtime",
                )
            else:
                self._agent_runtime.update_settings(settings)
            _emit("quota_status", status=self._agent_runtime.quota_status())
            _emit("backend_state", state="ready", provider="command-center")
            return

        if command_type == "agent_approval_response":
            approval_id = str(command.get("approval_id") or "").strip()
            decision = str(command.get("decision") or "deny").strip().lower()
            future = self._approval_waiters.pop(approval_id, None)
            if future and not future.done():
                future.set_result("approve" if decision == "approve" else "deny")
            return

        if command_type == "agent_task":
            prompt = str(command.get("prompt") or "").strip()
            request_id = str(command.get("request_id") or "")
            if not prompt:
                _emit("error", message="Command cannot be empty.", request_id=request_id)
                return
            await self._run_agent_task(prompt, request_id)
            return

        if command_type == "scan_pdf":
            pdf_path = str(command.get("path") or "").strip()
            request_id = str(command.get("request_id") or "")
            if not pdf_path:
                _emit("error", message="PDF path cannot be empty.", request_id=request_id)
                return
            await self._scan_pdf(pdf_path, request_id)
            return

        if command_type == "stop":
            reason = str(command.get("reason") or "user_stop")
            await self._stop_generation(reason)
            return

        if command_type == "warmup":
            await self._warm_session(force=True)
            return

        if command_type == "shutdown":
            self._running = False
            return

        _emit("bridge_error", message=f"Unknown command: {command_type}")

    async def _fallback_prompt(self, prompt: str) -> str:
        await self._ensure_warm_session(force=False)
        tab = await self._ensure_tab()
        result = await tab.ask(prompt)
        return result.response or ""

    async def _request_approval(self, approval) -> str:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._approval_waiters[approval.id] = future
        try:
            return await future
        finally:
            self._approval_waiters.pop(approval.id, None)

    async def _ensure_tab(self) -> Tab:
        if self._engine is None:
            raise RuntimeError("Engine is not available")
        if self._tab is None:
            self._tab = self._engine.create_tab("desktop-1")
        return self._tab

    async def _warm_session(self, *, force: bool = False) -> None:
        if force and self._tab is not None:
            await self._tab.close()
            self._tab = None
            self._tab_ready = False

        tab = await self._ensure_tab()
        _emit("backend_state", state="warming")

        try:
            provider = await tab.prime(timeout_s=8.0)
        except Exception as exc:
            self._tab_ready = False
            log.warning("Warmup did not complete cleanly: %s", exc)
            _emit("backend_state", state="degraded", message=str(exc))
            return

        self._tab_ready = True
        _emit("backend_ready", provider=provider)
        _emit("backend_state", state="ready", provider=provider)

    def _schedule_warm_session(self, *, force: bool) -> asyncio.Task[None]:
        if self._warm_task and not self._warm_task.done():
            return self._warm_task

        self._warm_task = asyncio.create_task(
            self._warm_session(force=force),
            name=f"warm-session:{'force' if force else 'steady'}",
        )
        return self._warm_task

    async def _ensure_warm_session(self, *, force: bool) -> None:
        if (
            not force
            and self._tab_ready
            and self._tab is not None
            and (self._warm_task is None or self._warm_task.done())
        ):
            return

        task = self._schedule_warm_session(force=force)
        try:
            await task
        finally:
            if self._warm_task is task and task.done():
                self._warm_task = None

    async def _submit(self, prompt: str, request_id: str) -> None:
        if self._active_task and not self._active_task.done():
            _emit(
                "error",
                message="A generation is already running.",
                request_id=request_id,
            )
            return

        self._request_seq += 1
        if not request_id:
            request_id = f"req-{self._request_seq}"

        self._active_task = asyncio.create_task(
            self._run_prompt(prompt, request_id),
            name=f"prompt:{request_id}",
        )

    async def _scan_pdf(self, pdf_path: str, request_id: str) -> None:
        if self._active_task and not self._active_task.done():
            _emit(
                "error",
                message="A generation or PDF scan is already running.",
                request_id=request_id,
            )
            return

        self._request_seq += 1
        if not request_id:
            request_id = f"pdf-{self._request_seq}"

        self._active_task = asyncio.create_task(
            self._run_pdf_scan(pdf_path, request_id),
            name=f"pdf-scan:{request_id}",
        )

    async def _run_agent_task(self, prompt: str, request_id: str) -> None:
        if self._active_task and not self._active_task.done():
            _emit("error", message="A task is already running.", request_id=request_id)
            return

        self._request_seq += 1
        if not request_id:
            request_id = f"agent-{self._request_seq}"

        self._active_task = asyncio.create_task(
            self._execute_agent_task(prompt, request_id),
            name=f"agent-task:{request_id}",
        )

    async def _execute_agent_task(self, prompt: str, request_id: str) -> None:
        _emit("agent_task_started", prompt=prompt, request_id=request_id)

        def emit(event_type: str, payload: object) -> None:
            if isinstance(payload, dict):
                _emit(event_type, request_id=request_id, **payload)
            else:
                _emit(event_type, request_id=request_id, payload=payload)

        try:
            if self._agent_runtime is None:
                self._agent_runtime = AgentRuntime(AgentSettings(), self._fallback_prompt)
            await self._agent_runtime.run(prompt, emit, request_id)
            _emit("agent_task_finished", request_id=request_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Agent task failed")
            _emit("error", message=str(exc), request_id=request_id)
        finally:
            self._active_task = None

    async def _run_prompt(self, prompt: str, request_id: str) -> None:
        _emit("prompt_started", prompt=prompt, request_id=request_id)

        try:
            await self._ensure_warm_session(force=False)
            tab = await self._ensure_tab()
            self._tab_ready = False
            result = await tab.ask(prompt)
            payload = result.to_dict()
            payload["provider"] = tab.current_provider or payload.get("provider")
            _emit("result", request_id=request_id, result=payload)
            _emit(
                "backend_state",
                state="ready",
                provider=payload.get("provider"),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Prompt failed")
            _emit("error", message=str(exc), request_id=request_id)
        finally:
            self._active_task = None
            if self._running:
                self._schedule_warm_session(force=True)

    async def _run_pdf_scan(self, pdf_path: str, request_id: str) -> None:
        _emit("pdf_scan_preparing", path=pdf_path, request_id=request_id)
        old_concurrency = self._cfg.concurrency
        old_warmup_tabs = self._cfg.warmup_tabs

        try:
            if self._engine is None:
                raise RuntimeError("Engine is not available")

            if self._tab is not None:
                await self._tab.close()
                self._tab = None
                self._tab_ready = False

            pages = extract_pdf_pages(pdf_path)
            chunks = build_page_chunks(pages, pages_per_prompt=2)
            prompt_to_chunk = {chunk.prompt: chunk for chunk in chunks}
            results = []

            self._cfg.concurrency = 2
            self._cfg.warmup_tabs = True

            _emit(
                "pdf_scan_started",
                path=pdf_path,
                request_id=request_id,
                page_count=len(pages),
                chunk_count=len(chunks),
                pages_per_prompt=2,
                parallel_chats=2,
                provider="gemini",
            )

            def _on_start(prompt: str) -> None:
                chunk = prompt_to_chunk.get(prompt)
                if chunk is None:
                    return
                _emit(
                    "pdf_chunk_started",
                    request_id=request_id,
                    chunk_index=chunk.index,
                    start_page=chunk.start_page,
                    end_page=chunk.end_page,
                    total_chunks=len(chunks),
                )

            async for result in self._engine.run(
                [chunk.prompt for chunk in chunks],
                on_start=_on_start,
            ):
                results.append(result)
                chunk = prompt_to_chunk.get(result.prompt)
                _emit(
                    "pdf_chunk_finished",
                    request_id=request_id,
                    chunk_index=chunk.index if chunk else len(results),
                    start_page=chunk.start_page if chunk else None,
                    end_page=chunk.end_page if chunk else None,
                    completed=len(results),
                    total_chunks=len(chunks),
                    status=result.status.value,
                    provider=result.provider,
                )

            report = merge_scan_results(results)
            artifacts = write_scan_artifacts(self._cfg.output_dir, pdf_path, report)
            _emit(
                "pdf_scan_result",
                request_id=request_id,
                path=pdf_path,
                report=report,
                artifacts=artifacts,
            )
            _emit("backend_state", state="ready", provider="gemini")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("PDF scan failed")
            _emit("error", message=str(exc), request_id=request_id)
        finally:
            self._cfg.concurrency = old_concurrency
            self._cfg.warmup_tabs = old_warmup_tabs
            self._active_task = None
            if self._running:
                self._schedule_warm_session(force=True)

    async def _stop_generation(
        self,
        reason: str,
        *,
        emit_event: bool = True,
    ) -> None:
        task = self._active_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        self._active_task = None
        for future in self._approval_waiters.values():
            if not future.done():
                future.cancel()
        self._approval_waiters.clear()

        if self._tab is not None:
            await self._tab.close()
            self._tab = None
            self._tab_ready = False

        if emit_event:
            _emit("stopped", reason=reason)
            await self._ensure_warm_session(force=True)


async def _main() -> None:
    cfg = Config(
        primary_provider="gemini",
        fallback_provider="",
        fallback_on_block=False,
        reuse_conversation=True,
        observer_poll_interval=0.1,
        completion_quiet_ms=650,
        max_completion_quiet_ms=1100,
        generation_start_timeout=14.0,
        hard_stall_timeout=4.5,
        output_format="jsonl",
    )

    configure_logging(
        level=cfg.log_level,
        log_dir=cfg.output_dir,
        console_stream=sys.stderr,
    )

    _emit("backend_booting")
    backend = DesktopBackend(cfg)
    await backend.run()


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
