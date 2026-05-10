#!/usr/bin/env python3
"""
Persistent JSON bridge for the Desktop AI Agent.
"""

from __future__ import annotations
import asyncio
import json
import signal
import sys
import logging
from pathlib import Path
from typing import Any, Optional

# Add the local 'python' directory to sys.path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / "python"))

from scraper import Config, configure_logging, get_logger
from agent_runtime import AgentRuntime
from agent_runtime.models.settings import AgentSettings

log = get_logger(__name__)

def _emit(event_type: str, payload: Any = None) -> None:
    data = {"type": event_type, "timestamp": ""}
    if isinstance(payload, dict):
        data.update(payload)
    elif payload is not None:
        data["payload"] = payload

    print(
        json.dumps(data, ensure_ascii=True),
        flush=True,
    )

class DesktopBackend:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._running = True
        self._agent_runtime: Optional[AgentRuntime] = None
        self._active_task: Optional[asyncio.Task] = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
            try:
                loop.add_signal_handler(sig, lambda: setattr(self, '_running', False))
            except NotImplementedError:
                pass

        _emit("backend_state", {"state": "ready"})

        while self._running:
            raw = await asyncio.to_thread(sys.stdin.readline)
            if not raw:
                break
            raw = raw.strip()
            if not raw:
                continue
            try:
                command = json.loads(raw)
                await self._handle_command(command)
            except Exception as e:
                _emit("error", {"message": f"Bridge error: {e}"})

    async def _handle_command(self, command: dict[str, Any]) -> None:
        cmd_type = command.get("type")

        if cmd_type == "agent_settings":
            settings = AgentSettings.from_payload(command.get("settings", {}))
            if self._agent_runtime is None:
                self._agent_runtime = AgentRuntime(
                    settings,
                    self._mock_llm_caller,
                    state_dir=Path(self._cfg.output_dir) / "agent_runtime"
                )
            else:
                self._agent_runtime.update_settings(settings)
            _emit("backend_state", {"state": "ready"})
            return

        if cmd_type == "agent_task":
            prompt = command.get("prompt")
            request_id = command.get("request_id", "task-1")
            if self._agent_runtime:
                self._active_task = asyncio.create_task(
                    self._agent_runtime.run(prompt, _emit, request_id)
                )
            return

        if cmd_type == "stop":
            if self._active_task:
                self._active_task.cancel()
            _emit("stopped", {"reason": "user_stop"})
            return

        if cmd_type == "shutdown":
            self._running = False
            return

    async def _mock_llm_caller(self, prompt: str) -> str:
        # Mocking LLM response for planning
        if "Decompose" in prompt:
            return json.dumps([
                {"index": 0, "description": "Identify target application"},
                {"index": 1, "description": "Perform requested actions"},
                {"index": 2, "description": "Verify final state"}
            ])
        return "Mocked LLM Response"

async def _main() -> None:
    cfg = Config(output_dir="data")
    configure_logging(level="INFO", log_dir="data/logs", console_stream=sys.stderr)
    backend = DesktopBackend(cfg)
    await backend.run()

if __name__ == "__main__":
    asyncio.run(_main())
