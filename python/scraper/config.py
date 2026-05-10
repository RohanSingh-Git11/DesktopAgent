from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Config:
    concurrency: int = 2
    retries: int = 3
    headless: bool = True
    output_format: str = "jsonl"
    output_dir: str = "results"
    log_level: str = "INFO"
    response_timeout: float = 45.0
    human_typing: bool = False
    storage_state_path: Optional[str] = None
    save_storage_state_path: Optional[str] = None
    backoff_base: float = 2.0
    primary_provider: str = "gemini"
    fallback_provider: str = ""
    fallback_on_block: bool = True
    reuse_conversation: bool = True
    observer_poll_interval: float = 0.1
    completion_quiet_ms: int = 650
    max_completion_quiet_ms: int = 1100
    generation_start_timeout: float = 14.0
    hard_stall_timeout: float = 4.5
    stable_threshold: float = 1.0
    warmup_tabs: bool = False

    def __post_init__(self):
        # Override with environment variables if present
        if os.getenv("SCRAPER_CONCURRENCY"):
            self.concurrency = int(os.getenv("SCRAPER_CONCURRENCY"))
        if os.getenv("SCRAPER_HEADLESS"):
            self.headless = os.getenv("SCRAPER_HEADLESS").lower() == "true"
        if os.getenv("SCRAPER_STORAGE_STATE"):
            self.storage_state_path = os.getenv("SCRAPER_STORAGE_STATE").strip()

        assert self.concurrency > 0
        assert self.output_format in ["jsonl", "csv", "both"]
        assert self.stable_threshold > 0

        if self.storage_state_path and not self.save_storage_state_path:
            self.save_storage_state_path = self.storage_state_path
