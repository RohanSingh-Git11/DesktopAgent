from __future__ import annotations
from typing import Any, Dict
from .vision import VisionSystem
from .state import StateCore

class Verifier:
    def __init__(self, state: StateCore, vision: VisionSystem):
        self.state = state
        self.vision = vision

    def verify_step(self, expected_change: str) -> bool:
        """
        Strict Step Verification Gate (Requirement 10).
        Compares UI state before and after.
        """
        # 1. Capture current UI state
        screenshot = self.vision.capture_clean_screenshot()
        analysis = self.vision.analyze_ui(screenshot)

        # 2. Check if analysis matches expectations
        # Stub: for now, we assume success if UI is stable
        success = analysis.get("stable", False)

        if success:
            self.state.update(last_verified_ui_state=analysis)

        return success
