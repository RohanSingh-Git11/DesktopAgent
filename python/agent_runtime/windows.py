from __future__ import annotations
import logging
import re
import psutil
import time
from typing import Optional, List, Dict, Any

log = logging.getLogger(__name__)

class WindowManager:
    def __init__(self):
        self.target_window_title: Optional[str] = None
        self.target_pid: Optional[int] = None
        self.desktop_refs: Dict[str, Any] = {}

    def bind_to_window(self, title_pattern: str) -> bool:
        log.info(f"Attempting to bind to window pattern: {title_pattern}")
        try:
            import pygetwindow as gw
            windows = gw.getAllWindows()
            for w in windows:
                if re.search(title_pattern, w.title, re.IGNORECASE):
                    self.target_window_title = w.title
                    log.info(f"Successfully bound to: {w.title}")
                    return True
        except Exception as e:
            log.error(f"Window binding failed: {e}")
        return False

    def get_desktop_snapshot(self) -> str:
        if not self.target_window_title:
            return "No target window bound."

        snapshot_lines = []
        self.desktop_refs = {}

        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(title_re=f".*{self.target_window_title}.*", timeout=5)
            main_win = app.window(title_re=f".*{self.target_window_title}.*")

            elements = main_win.descendants()

            ref_idx = 0
            for el in elements:
                try:
                    info = el.element_info
                    ctrl_type = info.control_type

                    if ctrl_type in ["Button", "MenuItem", "Edit", "ListItem", "TreeItem", "CheckBox", "ComboBox", "TabItem", "Hyperlink"]:
                        name = info.name
                        if name:
                            ref_id = f"dx{ref_idx}"
                            self.desktop_refs[ref_id] = el
                            snapshot_lines.append(f"[{ref_id}] {ctrl_type}: \"{name}\"")
                            ref_idx += 1
                except: continue
        except Exception as e:
            log.warning(f"Accessibility snapshot failed: {e}")
            return f"Failed to inspect desktop UI: {e}"

        return "\\n".join(snapshot_lines)

    def interact_with_ref(self, ref_id: str, action: str = "click", text: Optional[str] = None):
        el = self.desktop_refs.get(ref_id)
        if not el: return False

        try:
            if action == "click":
                el.click_input()
            elif action == "double_click":
                el.double_click_input()
            elif action == "right_click":
                el.right_click_input()
            elif action == "type" and text:
                el.type_keys(text, with_spaces=True, pause=0.05)
            elif action == "hover":
                el.move_mouse()
            return True
        except Exception as e:
            log.error(f"Desktop interaction {action} failed: {e}")
            return False

    def get_running_apps(self) -> List[str]:
        apps = []
        for proc in psutil.process_iter(['name']):
            try:
                name = proc.info['name']
                if name not in apps:
                    apps.append(name)
            except: pass
        return apps
