from __future__ import annotations
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class MemoryEntry(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    task_id: str
    goal: str
    steps: List[Dict[str, Any]]
    success: bool
    final_output: Optional[Dict[str, Any]] = None

class GlobalMemory:
    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.memory_dir / "task_history.jsonl"

    def record_task(self, entry: MemoryEntry):
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def get_recent_tasks(self, limit: int = 10) -> List[MemoryEntry]:
        if not self.history_path.exists():
            return []
        entries = []
        with open(self.history_path, "r", encoding="utf-8") as f:
            for line in f:
                entries.append(MemoryEntry.model_validate_json(line))
        return entries[-limit:]
