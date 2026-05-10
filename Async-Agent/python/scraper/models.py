from __future__ import annotations
import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional

class Status(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    STALLED = "stalled"

@dataclass
class ScrapeResult:
    prompt: str
    response: str
    status: Status
    attempts: int
    duration_s: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    partial_response: Optional[str] = None
    provider: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == Status.OK

    def to_dict(self) -> dict:
        # timestamp first for CSV tests
        return {
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "response": self.response,
            "status": self.status.value,
            "attempts": self.attempts,
            "duration_s": self.duration_s,
            "partial_response": self.partial_response,
            "provider": self.provider,
        }
