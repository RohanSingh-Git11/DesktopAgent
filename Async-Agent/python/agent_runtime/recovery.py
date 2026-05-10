from __future__ import annotations
import logging
from typing import Optional, Tuple
from .state import StateCore

log = logging.getLogger(__name__)

class RecoverySystem:
    def __init__(self, state: StateCore):
        self.state = state

    def classify_failure(self, error: Exception) -> str:
        """
        Identify failure type (Requirement 6).
        """
        err_str = str(error).lower()
        if "window" in err_str:
            return "WRONG_WINDOW"
        if "timeout" in err_str:
            return "UI_TIMEOUT"
        if "element" in err_str:
            return "UI_MISSING"
        return "UNKNOWN"

    def decide_recovery(self, failure_type: str) -> str:
        """
        Decide: retry, fix state, or rebuild plan.
        """
        if failure_type == "UI_TIMEOUT":
            return "RETRY_STEP"
        if failure_type == "WRONG_WINDOW":
            return "FIX_STATE"
        return "REBUILD_PLAN"

    def handle_failure(self, error: Exception) -> str:
        failure_type = self.classify_failure(error)
        decision = self.decide_recovery(failure_type)
        log.warning(f"Failure: {failure_type} -> Decision: {decision}")
        self.state.update(failure_reason=f"{failure_type}: {str(error)}")
        return decision
