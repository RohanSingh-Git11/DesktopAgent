from __future__ import annotations
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class FailurePattern(BaseModel):
    failure_type: str
    goal: str
    app_context: str
    recovery_action: str
    success: bool
    timestamp: float = Field(default_factory=time.time)

class LearnedProcedure(BaseModel):
    goal_pattern: str
    steps: List[str]
    app_context: str
    success_count: int = 1
    avg_confidence: float = 0.0

class LearningSystem:
    def __init__(self, learning_dir: Path):
        self.learning_dir = learning_dir
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_path = self.learning_dir / "failure_patterns.jsonl"
        self.procedures_path = self.learning_dir / "learned_procedures.jsonl"
        self._load_memory()

    def _load_memory(self):
        self.procedures: List[LearnedProcedure] = []
        if self.procedures_path.exists():
            with open(self.procedures_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        self.procedures.append(LearnedProcedure.model_validate_json(line))
                    except: pass

    def record_failure(self, failure: FailurePattern):
        with open(self.patterns_path, "a", encoding="utf-8") as f:
            f.write(failure.model_dump_json() + "\n")

    def record_success(self, goal: str, steps: List[str], app: str, confidence: float):
        # Update or create learned procedure
        found = False
        for p in self.procedures:
            if p.goal_pattern == goal and p.app_context == app:
                p.success_count += 1
                p.avg_confidence = (p.avg_confidence * (p.success_count-1) + confidence) / p.success_count
                found = True
                break

        if not found:
            self.procedures.append(LearnedProcedure(
                goal_pattern=goal,
                steps=steps,
                app_context=app,
                avg_confidence=confidence
            ))

        self._save_procedures()

    def _save_procedures(self):
        with open(self.procedures_path, "w", encoding="utf-8") as f:
            for p in self.procedures:
                f.write(p.model_dump_json() + "\n")

    def find_matching_procedure(self, goal: str, app: Optional[str]) -> Optional[LearnedProcedure]:
        """
        Retrieves the best matching procedure for a goal.
        """
        best_match = None
        # Simple exact match for now - could be upgraded to semantic search
        for p in self.procedures:
            if p.goal_pattern.lower() == goal.lower():
                if app is None or p.app_context == app:
                    best_match = p
                    break
        return best_match
