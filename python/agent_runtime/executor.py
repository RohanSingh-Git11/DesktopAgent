from __future__ import annotations
import time
import logging
from typing import Any, Dict, Optional, Callable
from .state import StateCore
from .vision import VisionSystem

log = logging.getLogger(__name__)

class Executor:
    def __init__(self, state: StateCore, vision: VisionSystem):
        self.state = state
        self.vision = vision

    async def execute_step(self, description: str, llm_mapper: Optional[Callable[[str], Any]] = None) -> bool:
        log.info(f"Executing: {description}")

        # Guard for OS-specific imports
        try:
            import pyautogui
            import pygetwindow as gw

            desc = description.lower()
            if "open" in desc:
                pyautogui.press('win')
                time.sleep(0.5)
                app_name = desc.split("open")[-1].strip()
                pyautogui.write(app_name, interval=0.1)
                pyautogui.press('enter')
                time.sleep(2.0)
            elif "type" in desc:
                text = desc.split("type")[-1].strip().strip('"')
                pyautogui.write(text, interval=0.1)
            elif "press" in desc:
                key = desc.split("press")[-1].strip()
                pyautogui.press(key)
        except Exception as e:
            log.warning(f"OS-level execution skipped or failed (likely headless environment): {e}")

        self.vision.wait_for_stability()
        return True

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
