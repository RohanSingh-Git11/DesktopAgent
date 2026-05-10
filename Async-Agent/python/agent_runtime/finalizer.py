from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
from .state import StateCore

class Finalizer:
    def __init__(self, state: StateCore, log_dir: Path):
        self.state = state
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def finalize_task(self) -> Dict[str, Any]:
        """
        Final output stage (Requirement 8).
        """
        summary = {
            "task_id": self.state.current.task_id,
            "goal": self.state.current.goal,
            "success": self.state.current.failure_reason is None,
            "completed_steps": [s.model_dump() for s in self.state.current.steps if s.status == "done"],
            "final_confidence": self.state.current.confidence_score,
            "failure_reason": self.state.current.failure_reason,
            "final_ui_state": self.state.current.last_verified_ui_state
        }

        # Store in persistent log
        log_path = self.log_dir / f"task_{self.state.current.task_id}_result.json"
        with open(log_path, "w") as f:
            json.dump(summary, f, indent=2)

        return summary
