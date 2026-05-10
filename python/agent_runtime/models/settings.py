from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, Any

class AgentSettings(BaseModel):
    model: str = "gemini-2.0-flash"
    temperature: float = 0.0
    max_tokens: int = 4096
    top_p: float = 0.95
    top_k: int = 40

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> AgentSettings:
        return cls(**payload)

    def quota_status(self) -> Dict[str, Any]:
        return {"status": "ok", "remaining": 1000} # Mock for now
