from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class TaskStep(BaseModel):
    index: int
    description: str
    status: str = "pending"  # pending, running, done, failed
    verification_result: Optional[str] = None

class AgentState(BaseModel):
    task_id: Optional[str] = None
    goal: Optional[str] = None
    active_window: Optional[str] = None
    active_app: Optional[str] = None
    current_step_index: int = 0
    steps: List[TaskStep] = []
    last_screenshot_path: Optional[str] = None
    last_verified_ui_state: Optional[Dict[str, Any]] = None
    confidence_score: float = 0.0
    failure_reason: Optional[str] = None
    is_bound: bool = False

    def save(self, path: Path):
        with open(path, "w") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> AgentState:
        if not path.exists():
            return cls()
        with open(path, "r") as f:
            return cls.model_validate_json(f.read())

class StateCore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "current_state.json"
        self.current = AgentState.load(self.state_path)

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.current, key):
                setattr(self.current, key, value)
        self.save()

    def set_step_status(self, index: int, status: str, verification: Optional[str] = None):
        if 0 <= index < len(self.current.steps):
            self.current.steps[index].status = status
            if verification:
                self.current.steps[index].verification_result = verification
            self.save()

    def save(self):
        self.current.save(self.state_path)

    def reset(self):
        self.current = AgentState()
        self.save()
