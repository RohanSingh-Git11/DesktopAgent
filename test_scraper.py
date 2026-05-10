"""
Tests for the scraper package.
Run with:  pytest tests/ -v
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config  import Config
from scraper.models  import ScrapeResult, Status
from scraper.output  import CSVWriter, JSONLWriter, OutputManager


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self):
        cfg = Config()
        assert cfg.concurrency == 2
        assert cfg.retries == 3
        assert cfg.headless is True
        assert cfg.output_format == "jsonl"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_CONCURRENCY", "5")
        monkeypatch.setenv("SCRAPER_HEADLESS", "false")
        cfg = Config()
        assert cfg.concurrency == 5
        assert cfg.headless is False

    def test_invalid_format_raises(self):
        with pytest.raises(AssertionError):
            Config(output_format="xml")

    def test_invalid_concurrency_raises(self):
        with pytest.raises(AssertionError):
            Config(concurrency=0)

    def test_storage_state_path_reused_for_save(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_STORAGE_STATE", "  auth/state.json  ")
        cfg = Config()
        assert cfg.storage_state_path == "auth/state.json"
        assert cfg.save_storage_state_path == "auth/state.json"

    def test_invalid_stable_threshold_raises(self):
        with pytest.raises(AssertionError):
            Config(stable_threshold=0)


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class TestScrapeResult:
    def _make(self, status=Status.OK) -> ScrapeResult:
        return ScrapeResult(
            prompt="test prompt",
            response="test response",
            status=status,
            attempts=1,
            duration_s=1.23,
        )

    def test_ok_property_true(self):
        assert self._make(Status.OK).ok is True

    def test_ok_property_false(self):
        assert self._make(Status.ERROR).ok is False

    def test_to_dict_serialisable(self):
        d = self._make().to_dict()
        assert json.dumps(d)  # must not raise
        assert d["status"] == "ok"
        assert "timestamp" in d

    def test_status_is_string_in_dict(self):
        d = self._make(Status.ERROR).to_dict()
        assert isinstance(d["status"], str)


# ─────────────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def result():
    return ScrapeResult(
        prompt="Hello?",
        response="Hello!",
        status=Status.OK,
        attempts=1,
        duration_s=2.5,
    )


class TestJSONLWriter:
    def test_writes_valid_jsonl(self, tmp_path, result):
        path = tmp_path / "out.jsonl"
        w = JSONLWriter(path)
        w.write(result)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["prompt"] == "Hello?"

    def test_appends_multiple(self, tmp_path, result):
        path = tmp_path / "out.jsonl"
        w = JSONLWriter(path)
        w.write(result)
        w.write(result)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2


class TestCSVWriter:
    def test_writes_header_and_row(self, tmp_path, result):
        path = tmp_path / "out.csv"
        w = CSVWriter(path)
        w.write(result)
        text = path.read_text()
        assert "prompt" in text
        assert "Hello?" in text

    def test_no_duplicate_header_on_reopen(self, tmp_path, result):
        path = tmp_path / "out.csv"
        CSVWriter(path).write(result)
        CSVWriter(path).write(result)
        lines = [l for l in path.read_text().strip().split("\n") if l]
        headers = [l for l in lines if l.startswith("timestamp")]
        assert len(headers) == 1


class TestOutputManager:
    def test_finalise_writes_summary(self, tmp_path, result):
        with OutputManager(str(tmp_path), "jsonl", "run123") as om:
            om.write(result)
        summary_path = tmp_path / "run123" / "summary.json"
        assert summary_path.exists()
        data = json.loads(summary_path.read_text())
        assert data["total"] == 1
        assert data["ok"] == 1
        assert data["success_rate"] == 100.0

    def test_both_format_creates_two_files(self, tmp_path, result):
        with OutputManager(str(tmp_path), "both", "runX") as om:
            om.write(result)
        assert (tmp_path / "runX" / "results.jsonl").exists()
        assert (tmp_path / "runX" / "results.csv").exists()

    def test_summary_stats_on_mixed_results(self, tmp_path):
        ok_r  = ScrapeResult("q1", "a1", Status.OK,    1, 1.0)
        err_r = ScrapeResult("q2", "ERR", Status.ERROR, 3, 5.0)
        with OutputManager(str(tmp_path), "jsonl", "runY") as om:
            om.write(ok_r)
            om.write(err_r)
        data = json.loads((tmp_path / "runY" / "summary.json").read_text())
        assert data["ok"] == 1
        assert data["errors"] == 1
        assert data["success_rate"] == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Completion heuristics (unit-level, no browser)
# ─────────────────────────────────────────────────────────────────────────────

class TestCompletionHeuristics:
    def test_response_completion_heuristic(self):
        from scraper.engine import _response_looks_complete

        assert _response_looks_complete("All done.")
        assert _response_looks_complete("```python\nprint('ok')\n```")
        assert not _response_looks_complete("Still working")
        assert not _response_looks_complete("```python\nprint('open fence')")

    def test_completion_quiet_ms_is_adaptive(self):
        from scraper.engine import _pick_completion_quiet_ms

        cfg = Config(completion_quiet_ms=800, max_completion_quiet_ms=1500)
        assert _pick_completion_quiet_ms("Finished.", cfg) == 800
        assert _pick_completion_quiet_ms("Still streaming", cfg) == 1500


class TestTab:
    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_status(self):
        from scraper.engine import Tab

        fake_page = MagicMock()
        fake_locator = MagicMock()

        with patch.object(Tab, "_ensure_page", AsyncMock(return_value=fake_page)):
            with patch(
                "scraper.engine._snapshot_last_response",
                AsyncMock(return_value=(0, "")),
            ):
                with patch(
                    "scraper.engine._wait_for_ready_input",
                    AsyncMock(return_value=(fake_locator, "textarea#prompt-textarea")),
                ):
                    with patch("scraper.engine._fill_prompt", AsyncMock()):
                        with patch("scraper.engine._submit_prompt", AsyncMock()):
                            with patch(
                                "scraper.engine._wait_for_generation_start",
                                AsyncMock(),
                            ):
                                with patch(
                                    "scraper.engine._wait_for_completed_response",
                                    AsyncMock(side_effect=TimeoutError("timed out")),
                                ):
                                    tab = Tab(MagicMock(), Config(retries=1), "session-1")
                                    result = await tab.ask("hello")

        assert result.status == Status.TIMEOUT
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_stalled_returns_stalled_status(self):
        from scraper.engine import StalledGenerationError, Tab

        fake_page = MagicMock()
        fake_locator = MagicMock()

        with patch.object(Tab, "_ensure_page", AsyncMock(return_value=fake_page)):
            with patch(
                "scraper.engine._snapshot_last_response",
                AsyncMock(return_value=(0, "")),
            ):
                with patch(
                    "scraper.engine._wait_for_ready_input",
                    AsyncMock(return_value=(fake_locator, "textarea#prompt-textarea")),
                ):
                    with patch("scraper.engine._fill_prompt", AsyncMock()):
                        with patch("scraper.engine._submit_prompt", AsyncMock()):
                            with patch(
                                "scraper.engine._wait_for_generation_start",
                                AsyncMock(),
                            ):
                                with patch(
                                    "scraper.engine._wait_for_completed_response",
                                    AsyncMock(
                                        side_effect=StalledGenerationError("partial")
                                    ),
                                ):
                                    tab = Tab(MagicMock(), Config(retries=1), "session-1")
                                    result = await tab.ask("hello")

        assert result.status == Status.STALLED
        assert result.partial_response == "partial"


class TestScraperEngine:
    @pytest.mark.asyncio
    async def test_run_invokes_on_start_callback(self):
        from scraper.engine import ScraperEngine, Tab

        engine = ScraperEngine(Config(concurrency=1))
        engine._context = MagicMock()
        started: list[str] = []

        fake_result = ScrapeResult(
            prompt="job",
            response="done",
            status=Status.OK,
            attempts=1,
            duration_s=0.01,
        )

        with patch.object(Tab, "warmup", AsyncMock()):
            with patch.object(Tab, "ask", AsyncMock(return_value=fake_result)):
                results = [
                    result
                    async for result in engine.run(["job"], on_start=started.append)
                ]

        assert started == ["job"]
        assert [result.prompt for result in results] == ["job"]

    @pytest.mark.asyncio
    async def test_run_returns_all_results(self):
        from scraper.engine import ScraperEngine, Tab

        engine = ScraperEngine(Config(concurrency=2))
        engine._context = MagicMock()

        fake_results = [
            ScrapeResult("job1", "done1", Status.OK, 1, 0.01),
            ScrapeResult("job2", "done2", Status.OK, 1, 0.02),
        ]

        with patch.object(Tab, "warmup", AsyncMock()):
            with patch.object(Tab, "ask", AsyncMock(side_effect=fake_results)):
                results = [result async for result in engine.run(["job1", "job2"])]

        assert sorted(result.prompt for result in results) == ["job1", "job2"]
