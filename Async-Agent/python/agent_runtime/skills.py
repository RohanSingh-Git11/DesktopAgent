from __future__ import annotations
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class Skill(BaseModel):
    name: str
    description: str
    steps: List[str]
    app_context: Optional[str] = None
    success_count: int = 1
    last_used: float = Field(default_factory=time.time)

class SkillWorkshop:
    def __init__(self, state_dir: Path):
        self.db_path = state_dir / "agent_state.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    steps TEXT,
                    app_context TEXT,
                    success_count INTEGER DEFAULT 1,
                    last_used REAL
                )
            """)
            conn.commit()

    def save_skill(self, skill: Skill):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO skills (name, description, steps, app_context, success_count, last_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                skill.name,
                skill.description,
                json.dumps(skill.steps),
                skill.app_context,
                skill.success_count,
                skill.last_used
            ))
            conn.commit()

    def find_skill(self, goal: str, app: Optional[str] = None) -> Optional[Skill]:
        """
        Search for a skill that matches the goal.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT name, description, steps, app_context, success_count, last_used FROM skills").fetchall()
            for r in rows:
                # Simple keyword match for now
                if r[0].lower() in goal.lower() or r[1].lower() in goal.lower():
                    if app is None or r[3] == app:
                        return Skill(
                            name=r[0],
                            description=r[1],
                            steps=json.loads(r[2]),
                            app_context=r[3],
                            success_count=r[4],
                            last_used=r[5]
                        )
        return None

    def get_all_skills(self) -> List[Skill]:
        skills = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT name, description, steps, app_context, success_count, last_used FROM skills ORDER BY last_used DESC").fetchall()
            for r in rows:
                skills.append(Skill(
                    name=r[0],
                    description=r[1],
                    steps=json.loads(r[2]),
                    app_context=r[3],
                    success_count=r[4],
                    last_used=r[5]
                ))
        return skills
