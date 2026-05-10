from __future__ import annotations
import time
import logging
import subprocess
import sys
import re
import random
from typing import Any, Dict, Optional, Callable
from .state import StateCore
from .vision import VisionSystem
from .human_simulation import human_move, human_type, think_delay

log = logging.getLogger(__name__)

class Executor:
    def __init__(self, state: StateCore, vision: VisionSystem, human_mode: bool = False):
        self.state = state
        self.vision = vision
        self.human_mode = human_mode

    def update_settings(self, human_mode: bool):
        self.human_mode = human_mode

    async def execute_step(self, description: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Executes a plan step using OS hooks and visual context.
        """
        log.info(f"Executing step: {description}")

        try:
            import pyautogui
            desc = description.lower()

            if self.human_mode:
                think_delay(0.5, 1.5)

            # 1. Closed-loop Ref targeting (Deterministic interaction)
            ref_match = re.search(r'\[(ax|dx|e)\d+\]', desc)
            if ref_match:
                ref_id = ref_match.group(0).strip('[]')
                action = "click"
                if "type" in desc: action = "type"
                elif "double" in desc: action = "double_click"
                elif "right" in desc: action = "right_click"
                elif "hover" in desc: action = "hover"

                text = None
                if action == "type":
                    text_match = re.search(r'["\'](.*?)["\']', desc)
                    text = text_match.group(1) if text_match else desc.split("type")[-1].strip()

                return await self.interact_with_ref(ref_id, action, text, context)

            # 2. Heuristic-based fallback
            if "open" in desc:
                app_name = desc.split("open")[-1].strip()
                self._launch_app(app_name)
            elif "type" in desc:
                text_match = re.search(r'["\'](.*?)["\']', desc)
                text = text_match.group(1) if text_match else desc.split("type")[-1].strip()
                self.type_text(text)
            elif "press" in desc:
                key = desc.split("press")[-1].strip()
                pyautogui.press(key)

        except Exception as e:
            log.error(f"Execution error: {e}")
            return False

        time.sleep(1.0)
        self.vision.wait_for_stability()
        return True

    async def interact_with_ref(self, ref_id: str, action: str, text: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Orchestrates interaction with a specific element reference.
        """
        log.info(f"Interacting with ref {ref_id} (Action: {action})")

        # Try Browser first if active
        if context and context.get("browser_engine") and ref_id.startswith("ax"):
            return await context["browser_engine"].act(action, ref_id, text)

        # Try Desktop if active
        if context and context.get("window_manager") and ref_id.startswith("dx"):
            return context["window_manager"].interact_with_ref(ref_id, action, text)

        return False

    def _launch_app(self, app_name: str):
        import pyautogui
        if sys.platform == 'win32' or 'linux' in sys.platform:
            # On linux we might not have 'win' key but we'll try for the mock test
            pyautogui.press('win')
            time.sleep(0.5)
            pyautogui.write(app_name, interval=0.1)
            time.sleep(0.5)
            pyautogui.press('enter')
        else:
            log.info(f"Platform {sys.platform} - simulate launch of {app_name}")

    def move_mouse_to(self, x: int, y: int):
        try:
            if self.human_mode:
                human_move(x, y)
            else:
                import pyautogui
                pyautogui.moveTo(x, y, duration=0.3)
        except: pass

    def click(self, x: Optional[int] = None, y: Optional[int] = None):
        try:
            import pyautogui
            if x is not None and y is not None:
                self.move_mouse_to(x, y)

            if self.human_mode:
                time.sleep(random.uniform(0.1, 0.3))
                pyautogui.click()
                time.sleep(random.uniform(0.1, 0.2))
            else:
                pyautogui.click()
        except: pass

    def type_text(self, text: str):
        try:
            if self.human_mode:
                human_type(text)
            else:
                import pyautogui
                pyautogui.write(text, interval=0.05)
        except: pass
