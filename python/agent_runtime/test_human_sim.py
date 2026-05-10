import pytest
from pathlib import Path
from python.agent_runtime.human_simulation import get_bezier_curve, _calculate_bezier

def test_bezier_points():
    start = (0, 0)
    end = (100, 100)
    curve = get_bezier_curve(start, end, control_points=2)

    assert len(curve) >= 10
    assert curve[0] == start
    # End point might be slightly off due to rounding in _calculate_bezier but should be close
    assert abs(curve[-1][0] - end[0]) <= 1
    assert abs(curve[-1][1] - end[1]) <= 1

def test_calculate_bezier():
    points = [(0, 0), (50, 0), (50, 50), (100, 50)]
    p0 = _calculate_bezier(points, 0)
    p1 = _calculate_bezier(points, 1)

    assert p0 == (0, 0)
    assert p1 == (100, 50)
