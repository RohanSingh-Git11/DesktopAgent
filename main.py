#!/usr/bin/env python3
"""
chatgpt-scraper - production-grade async ChatGPT scraper

Usage examples
--------------
# Inline prompts
python main.py -p "What is Python?" "Explain asyncio" "Name 3 sorting algorithms"

# From file (one prompt per line, blank lines / # comments ignored)
python main.py --file prompts.txt

# Tune concurrency and output format
python main.py --file prompts.txt --concurrency 3 --format both --timeout 60

# Debug mode (visible browser, verbose logs)
python main.py -p "Hello" --no-headless --log-level DEBUG

# Human-like typing (slower but more evasive)
python main.py --file prompts.txt --human-typing

# Reuse a logged-in ChatGPT session across runs
python main.py --file prompts.txt --no-headless --storage-state .auth/chatgpt.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper import (
    Config,
    LiveProgress,
    OutputManager,
    ScraperEngine,
    configure_logging,
    get_logger,
    print_banner,
    print_result,
    print_summary,
)

log = get_logger(__name__)

_shutdown_event: asyncio.Event | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_json(event_type: str, **payload: Any) -> None:
    print(
        json.dumps(
            {"type": event_type, "timestamp": _utc_now(), **payload},
            ensure_ascii=True,
        ),
        flush=True,
    )


def load_prompts_from_file(path: str) -> list[str]:
    prompt_path = Path(path)
    if not prompt_path.exists():
        sys.exit(f"[error] prompt file not found: {path}")

    prompts = [
        line.strip()
        for line in prompt_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not prompts:
        sys.exit("[error] prompt file is empty or contains only comments")
    return prompts


def _install_signal_handlers(*, json_events: bool) -> asyncio.Event:
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    def _handle(sig: signal.Signals) -> None:  # type: ignore[name-defined]
        if json_events:
            _emit_json("signal", signal=sig.name)
        else:
            print(
                f"\n[signal] {sig.name} received - finishing in-flight tasks then exiting..."
            )
        assert _shutdown_event is not None
        _shutdown_event.set()

    loop = asyncio.get_running_loop()
    signals = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        signals.append(signal.SIGTERM)

    for sig in signals:
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle(s))
        except NotImplementedError:
            try:
                signal.signal(sig, lambda _signum, _frame, s=sig: _handle(s))
            except ValueError:
                pass

    return _shutdown_event


async def run(
    cfg: Config,
    prompts: list[str],
    run_id: str,
    *,
    json_events: bool = False,
) -> None:
    shutdown = _install_signal_handlers(json_events=json_events)

    configure_logging(
        level=cfg.log_level,
        log_dir=cfg.output_dir,
        console_stream=sys.stderr if json_events else sys.stdout,
    )
    log.info(
        "run_id=%s  prompts=%d  concurrency=%d",
        run_id,
        len(prompts),
        cfg.concurrency,
    )

    if json_events:
        _emit_json(
            "run_started",
            run_id=run_id,
            prompt_count=len(prompts),
            concurrency=cfg.concurrency,
        )
    else:
        print_banner(len(prompts), cfg.concurrency, run_id)

    progress = LiveProgress(cfg.concurrency)
    wall_start = time.monotonic()
    completed = 0
    ok_count = 0

    def _handle_start(prompt: str) -> None:
        if json_events:
            _emit_json("prompt_started", run_id=run_id, prompt=prompt)
        else:
            progress.start(prompt)

    with OutputManager(cfg.output_dir, cfg.output_format, run_id) as out:
        async with ScraperEngine(cfg) as engine:
            async for result in engine.run(prompts, on_start=_handle_start):
                if shutdown.is_set():
                    log.warning("Shutdown requested - stopping early")
                    break

                completed += 1
                if result.ok:
                    ok_count += 1

                out.write(result)

                if json_events:
                    _emit_json(
                        "result",
                        run_id=run_id,
                        completed=completed,
                        total=len(prompts),
                        result=result.to_dict(),
                    )
                else:
                    progress.finish(result.prompt, result.status.value)
                    print_result(
                        prompt=result.prompt,
                        response=result.response,
                        status=result.status.value,
                        attempt=result.attempts,
                        duration=result.duration_s,
                        index=completed,
                        total=len(prompts),
                    )

    wall_time = time.monotonic() - wall_start
    if json_events:
        _emit_json(
            "run_finished",
            run_id=run_id,
            ok=ok_count,
            errors=completed - ok_count,
            wall_time_s=round(wall_time, 3),
            output_dir=str(Path(cfg.output_dir) / run_id),
        )
    else:
        print_summary(
            ok=ok_count,
            errors=completed - ok_count,
            total_s=wall_time,
            output_dir=cfg.output_dir,
            run_id=run_id,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gemini-scraper",
        description="Async Gemini scraper with retry, backoff, and structured output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "-p",
        "--prompts",
        nargs="+",
        metavar="PROMPT",
        help="One or more prompts passed directly on the command line",
    )
    src.add_argument(
        "--file",
        metavar="PATH",
        help="Path to a .txt file with one prompt per line (# for comments)",
    )

    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=2,
        metavar="N",
        help="Number of parallel browser tabs (default: 2)",
    )
    parser.add_argument(
        "--retries",
        "-r",
        type=int,
        default=3,
        metavar="N",
        help="Retry attempts per prompt on timeout (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=45.0,
        metavar="SEC",
        help="Seconds to wait for a stable response (default: 45)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["jsonl", "csv", "both"],
        default="jsonl",
        dest="output_format",
        help="Output format (default: jsonl)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="results",
        metavar="DIR",
        help="Directory for output files (default: results/)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log verbosity (default: INFO)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window (useful for debugging)",
    )
    parser.add_argument(
        "--human-typing",
        action="store_true",
        help="Type prompts character-by-character with random delays",
    )
    parser.add_argument(
        "--storage-state",
        metavar="PATH",
        help="Load a Playwright storage-state JSON file for an authenticated session",
    )
    parser.add_argument(
        "--save-storage-state",
        metavar="PATH",
        help="Save Playwright storage state on shutdown (defaults to --storage-state)",
    )
    parser.add_argument(
        "--backoff-base",
        type=float,
        default=2.0,
        metavar="N",
        help="Exponential backoff base between retries (default: 2.0)",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini"],
        default=None,
        help="Primary provider to target first (Gemini only)",
    )
    parser.add_argument(
        "--fallback-provider",
        choices=["", "gemini"],
        default=None,
        help="Fallback provider to use when the primary is blocked/unavailable",
    )
    parser.add_argument(
        "--disable-fallback-on-block",
        action="store_true",
        help="Disable automatic provider fallback when the primary is blocked",
    )
    parser.add_argument(
        "--reuse-conversation",
        action="store_true",
        help="Reuse the active conversation/tab between prompts when possible",
    )
    parser.add_argument(
        "--json-events",
        action="store_true",
        help="Emit newline-delimited JSON events for desktop UI integration",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    defaults = Config()

    prompts: list[str] = (
        args.prompts if args.prompts else load_prompts_from_file(args.file)
    )

    cfg = Config(
        headless=not args.no_headless,
        storage_state_path=args.storage_state,
        save_storage_state_path=args.save_storage_state,
        concurrency=args.concurrency,
        retries=args.retries,
        response_timeout=args.timeout,
        output_format=args.output_format,
        output_dir=args.output_dir,
        log_level=args.log_level,
        human_typing=args.human_typing,
        backoff_base=args.backoff_base,
        primary_provider=args.provider or defaults.primary_provider,
        fallback_provider=(
            args.fallback_provider
            if args.fallback_provider is not None
            else defaults.fallback_provider
        ),
        fallback_on_block=(
            False if args.disable_fallback_on_block else defaults.fallback_on_block
        ),
        reuse_conversation=args.reuse_conversation or defaults.reuse_conversation,
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    try:
        asyncio.run(run(cfg, prompts, run_id, json_events=args.json_events))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        if args.json_events:
            _emit_json("error", message=str(exc))
        raise


if __name__ == "__main__":
    main()
