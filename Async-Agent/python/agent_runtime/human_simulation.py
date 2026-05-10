from __future__ import annotations
import time
import random
import numpy as np
import logging
from typing import List, Tuple

log = logging.getLogger(__name__)

def get_bezier_curve(start: Tuple[int, int], end: Tuple[int, int], control_points: int = 2) -> List[Tuple[int, int]]:
    """
    Generates a list of points representing a Bezier curve between start and end.
    """
    points = [start]

    # Generate random control points
    controls = []
    for _ in range(control_points):
        x = random.randint(min(start[0], end[0]), max(start[0], end[0]))
        y = random.randint(min(start[1], end[1]), max(start[1], end[1]))
        controls.append((x, y))

    points.extend(controls)
    points.append(end)

    # Number of steps based on distance
    dist = np.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
    steps = max(10, int(dist / 10))

    curve = []
    for t in np.linspace(0, 1, steps):
        point = _calculate_bezier(points, t)
        curve.append(point)

    return curve

def _calculate_bezier(points: List[Tuple[int, int]], t: float) -> Tuple[int, int]:
    n = len(points) - 1
    x = 0
    y = 0
    for i, p in enumerate(points):
        coeff = _binomial_coeff(n, i) * ((1 - t) ** (n - i)) * (t ** i)
        x += coeff * p[0]
        y += coeff * p[1]
    return int(x), int(y)

def _binomial_coeff(n: int, k: int) -> int:
    import math
    return math.comb(n, k)

def human_move(target_x: int, target_y: int):
    """
    Moves mouse to target using a human-like path.
    """
    try:
        import pyautogui
        start_x, start_y = pyautogui.position()

        # Don't move if already there
        if abs(start_x - target_x) < 2 and abs(start_y - target_y) < 2:
            return

        curve = get_bezier_curve((start_x, start_y), (target_x, target_y))

        for x, y in curve:
            pyautogui.moveTo(x, y)
            # Add micro-jitter
            time.sleep(random.uniform(0.001, 0.005))

    except Exception as e:
        log.error(f"Human move failed: {e}")

def human_type(text: str, interval: float = 0.1):
    """
    Types text with variable speed and occasional pauses.
    """
    try:
        import pyautogui
        for char in text:
            pyautogui.write(char)

            # Randomize delay between keys
            delay = random.uniform(interval * 0.5, interval * 1.5)

            # Add longer pauses for spaces or punctuation
            if char in " ,.!?":
                delay += random.uniform(0.1, 0.3)

            # Occasional "thinking" pause
            if random.random() < 0.05:
                time.sleep(random.uniform(0.5, 1.5))

            time.sleep(delay)
    except Exception as e:
        log.error(f"Human type failed: {e}")

def think_delay(min_s: float = 0.5, max_s: float = 2.0):
    """
    Simulates a human looking at the screen or thinking.
    """
    time.sleep(random.uniform(min_s, max_s))
