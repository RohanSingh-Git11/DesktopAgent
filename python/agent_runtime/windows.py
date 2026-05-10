from __future__ import annotations
import logging
from typing import Optional, List

log = logging.getLogger(__name__)

class WindowManager:
    def __init__(self):
        self.target_window_title: Optional[str] = None

    def bind_to_window(self, title_re: str) -> bool:
        """
        Locks the agent to a specific window.
        """
        log.info(f"Bind to window: {title_re}")
        self.target_window_title = title_re
        return True

    def get_active_window_info(self) -> dict:
        return {"title": self.target_window_title or "Mock Window"}

    def ensure_focus(self) -> bool:
        return True

# Placeholder for when running on Windows
try:
    import pygetwindow as gw
    class RealWindowManager(WindowManager):
        def bind_to_window(self, title_re: str) -> bool:
            try:
                windows = gw.getWindowsWithTitle(title_re)
                if windows:
                    self.target_window_title = windows[0].title
                    windows[0].activate()
                    return True
                return False
            except:
                return False
except:
    pass
