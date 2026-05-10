from __future__ import annotations
import time
import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import mss
import mss.tools
from PIL import Image
import numpy as np
import cv2
import logging

log = logging.getLogger(__name__)

class VisionSystem:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.screenshots_dir = data_dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.sct = mss.mss()
        except Exception as e:
            log.warning(f"MSS initialization failed (headless?): {e}")
            self.sct = None

    def capture_clean_screenshot(self, exclude_region: Optional[Tuple[int, int, int, int]] = None) -> Path:
        """
        Captures a clean screenshot.
        """
        filename = f"screenshot_{int(time.time())}.png"
        filepath = self.screenshots_dir / filename

        if not self.sct:
            # Fallback to mock for headless testing
            img = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
            img.save(filepath)
            return filepath

        monitor = self.sct.monitors[1]
        sct_img = self.sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        if exclude_region:
            draw_img = np.array(img)
            left, top, right, bottom = exclude_region
            # Clamp values
            top = max(0, top)
            left = max(0, left)
            bottom = min(draw_img.shape[0], bottom)
            right = min(draw_img.shape[1], right)
            draw_img[top:bottom, left:right] = 0
            img = Image.fromarray(draw_img)

        img.save(filepath)
        return filepath

    def analyze_ui(self, screenshot_path: Path) -> Dict[str, Any]:
        """
        Analyzes the UI for elements.
        """
        img = cv2.imread(str(screenshot_path))
        if img is None:
            return {"elements": [], "stable": False}

        # Basic edge detection to find 'elements'
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edged = cv2.Canny(gray, 30, 200)
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        elements = []
        for c in contours:
            (x, y, w, h) = cv2.boundingRect(c)
            if w > 20 and h > 20: # Filter noise
                elements.append({"x": x, "y": y, "w": w, "h": h})

        return {
            "elements": elements,
            "stable": True,
            "timestamp": time.time()
        }

    def wait_for_stability(self, threshold: float = 0.98, timeout: float = 5.0):
        if not self.sct:
            time.sleep(0.5)
            return True

        start_time = time.time()
        last_img = None

        while time.time() - start_time < timeout:
            monitor = self.sct.monitors[1]
            sct_img = self.sct.grab(monitor)
            curr_img = np.array(Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX"))
            curr_img = cv2.resize(curr_img, (640, 360)) # Resize for speed

            if last_img is not None:
                diff = cv2.absdiff(curr_img, last_img)
                non_zero = np.count_nonzero(diff)
                stability = 1.0 - (non_zero / diff.size)

                if stability >= threshold:
                    return True

            last_img = curr_img
            time.sleep(0.5)
        return False

    def calculate_confidence(self, state_binding: bool, ui_stability: bool, visual_clarity: float) -> float:
        score = 0.0
        if state_binding: score += 0.3
        if ui_stability: score += 0.3
        score += (visual_clarity * 0.4)
        return score
