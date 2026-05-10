from __future__ import annotations
import time
import logging
import subprocess
import sys
import re
from typing import Any, Dict, Optional, Callable
from .state import StateCore
from .vision import VisionSystem

log = logging.getLogger(__name__)

class Executor:
    def __init__(self, state: StateCore, vision: VisionSystem):
        self.state = state
        self.vision = vision

    async def execute_step(self, description: str) -> bool:
        """
        Executes a plan step using OS hooks.
        Requirement 5: Mandatory wait and UI stabilization.
        """
        log.info(f"Executing step: {description}")

        try:
            import pyautogui

            desc = description.lower()

            if "open" in desc:
                app_name = desc.split("open")[-1].strip()
                self._launch_app(app_name)
            elif "type" in desc:
                text_match = re.search(r'["\'](.*?)["\']', desc)
                if text_match:
                    pyautogui.write(text_match.group(1), interval=0.05)
                else:
                    pyautogui.write(desc.split("type")[-1].strip(), interval=0.05)
            elif "press" in desc:
                key = desc.split("press")[-1].strip()
                pyautogui.press(key)

        except Exception as e:
            log.error(f"Execution error: {e}")
            return False

        time.sleep(1.0)
        self.vision.wait_for_stability()

        return True

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
            import pyautogui
            pyautogui.moveTo(x, y, duration=0.5)
        except: pass

    def click(self, x: Optional[int] = None, y: Optional[int] = None):
        try:
            import pyautogui
            pyautogui.click(x, y)
        except: pass

    def type_text(self, text: str):
        try:
            import pyautogui
            pyautogui.write(text, interval=0.1)
        except: pass
