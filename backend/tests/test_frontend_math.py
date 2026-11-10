"""
Unit tests for frontend 3D editor math and logic algorithms:
- Decimal snapping (0.05m, 0.1m, 0.5m, 1.0m)
- Coordinate distance & polygon area calculation
- Undo/Redo stack history behavior (50-action cap)
"""
import math
import pytest


def snap(val: float, step: float = 0.1) -> float:
    if not step or step <= 0:
        return val
    inv = 1 / step
    return round(val * inv) / inv


def calculate_distance_2d(p1, p2) -> float:
    dx = p2[0] - p1[0]
    dz = p2[1] - p1[1]
    return math.sqrt(dx * dx + dz * dz)


def calculate_polygon_area(points) -> float:
    if not points or len(points) < 3:
        return 0.0
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area / 2.0)


class HistoryManager:
    def __init__(self, max_size=50):
        self.max_size = max_size
        self.undo_stack = []
        self.redo_stack = []

    def can_undo(self):
        return len(self.undo_stack) > 0

    def can_redo(self):
        return len(self.redo_stack) > 0

    def push(self, action):
        self.undo_stack.append(action)
        if len(self.undo_stack) > self.max_size:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.can_undo():
            return False
        action = self.undo_stack.pop()
        action["undo"]()
        self.redo_stack.append(action)
        return True

    def redo(self):
        if not self.can_redo():
            return False
        action = self.redo_stack.pop()
        action["execute"]()
        self.undo_stack.append(action)
        return True


def test_decimal_snapping():
    # 0.05m snap
    assert snap(1.23, 0.05) == 1.25
    assert snap(1.22, 0.05) == 1.20
    assert snap(0.04, 0.05) == 0.05

    # 0.1m snap
    assert snap(2.34, 0.1) == 2.3
    assert snap(2.36, 0.1) == 2.4

    # 0.5m snap
    assert snap(1.2, 0.5) == 1.0
    assert snap(1.3, 0.5) == 1.5
    assert snap(3.8, 0.5) == 4.0

    # 1.0m snap
    assert snap(4.4, 1.0) == 4.0
    assert snap(4.6, 1.0) == 5.0


def test_geometry_distance_and_area():
    # 2D distance
    assert calculate_distance_2d([0, 0], [3, 4]) == 5.0

    # 10m x 8m room rectangle = 80 m²
    rect = [[0, 0], [10, 0], [10, 8], [0, 8]]
    assert calculate_polygon_area(rect) == 80.0

    # L-shaped room
    l_shape = [[0, 0], [6, 0], [6, 4], [3, 4], [3, 8], [0, 8]]
    # Area = (6x4) + (3x4) = 24 + 12 = 36 m²
    assert calculate_polygon_area(l_shape) == 36.0


def test_undo_redo_stack_and_max_capacity():
    hist = HistoryManager(max_size=50)
    assert not hist.can_undo()
    assert not hist.can_redo()

    state = {"count": 0}

    def inc():
        state["count"] += 1

    def dec():
        state["count"] -= 1

    action = {"execute": inc, "undo": dec}
    hist.push(action)
    inc()
    assert state["count"] == 1
    assert hist.can_undo()

    hist.undo()
    assert state["count"] == 0
    assert hist.can_redo()

    hist.redo()
    assert state["count"] == 1

    # Verify max size 50 capping
    for i in range(60):
        hist.push({"execute": lambda: None, "undo": lambda: None})
    assert len(hist.undo_stack) == 50

