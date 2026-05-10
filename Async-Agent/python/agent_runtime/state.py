from __future__ import annotations
import sqlite3
import json
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

class StateCore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "agent_state.db"
        self._init_db()
        self.current = self.load_latest_state()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT,
                    steps TEXT,
                    status TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def load_latest_state(self) -> AgentState:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT data FROM state WHERE id = 1").fetchone()
            if row:
                return AgentState.model_validate_json(row[0])
        return AgentState()

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
        data_json = self.current.model_dump_json()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO state (id, data) VALUES (1, ?)", (data_json,))
            # If there's an active task, also log it to history
            if self.current.task_id:
                conn.execute("""
                    INSERT OR REPLACE INTO task_history (task_id, goal, steps, status)
                    VALUES (?, ?, ?, ?)
                """, (
                    self.current.task_id,
                    self.current.goal,
                    json.dumps([s.model_dump() for s in self.current.steps]),
                    "completed" if all(s.status == "done" for s in self.current.steps) else "in_progress"
                ))
            conn.commit()

    def reset(self):
        self.current = AgentState()
        self.save()

    def get_task_history(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT task_id, goal, status, timestamp FROM task_history ORDER BY timestamp DESC").fetchall()
            return [{"task_id": r[0], "goal": r[1], "status": r[2], "timestamp": r[3]} for r in rows]
