import math
import pytest
from app.gait_detector import GaitDetector


BBOX = (0, 0, 200, 300)  # x1, y1, x2, y2 — bbox height = 300


def _make_keypoints(y11: int, y13: int, y15: int, y16: int) -> list[tuple[int, int]]:
    """Build a minimal 17-keypoint list with the four fetlock positions set."""
    kpts = [(100, 100)] * 17
    kpts[11] = (100, y11)
    kpts[13] = (100, y13)
    kpts[15] = (100, y15)
    kpts[16] = (100, y16)
    return kpts


def test_too_few_frames_returns_unknown():
    detector = GaitDetector()
    for _ in range(5):  # less than MIN_FRAMES=10
        kpts = _make_keypoints(250, 250, 250, 250)
        detector.update(kpts, BBOX)
    result = detector.detect()
    assert result.name == "---"
    assert result.confidence == 0.0


def test_stationary_horse_returns_schritt():
    """Very small variance → Schritt."""
    detector = GaitDetector()
    for _ in range(30):
        # All fetlocks near the same y position, barely moving
        kpts = _make_keypoints(250, 251, 250, 251)
        detector.update(kpts, BBOX)
    result = detector.detect()
    assert result.name == "Schritt"


def test_lateral_sync_returns_toelt():
    """LF in phase with LH, RF in phase with RH, but LF/RF offset by π/2 → high lat_sync, low diag_sync → Tölt."""
    detector = GaitDetector()
    for i in range(60):  # 2 full cycles for reliable correlation
        t = i / 30.0
        h = BBOX[3]  # 300
        # Lateral left pair in phase (phase 0); lateral right pair offset by π/2
        lf_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t)))
        lh_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t)))              # same as LF
        rf_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t + math.pi / 2)))
        rh_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t + math.pi / 2)))  # same as RF
        kpts = _make_keypoints(lf_y, rf_y, lh_y, rh_y)
        detector.update(kpts, BBOX)
    result = detector.detect()
    assert result.name in ("Tölt", "Rennpass"), f"Expected Tölt/Rennpass, got {result}"


def test_diagonal_sync_returns_trab():
    """LF in phase with RH, RF in phase with LH, offset by π/2 → high diag_sync, low lat_sync → Trab."""
    detector = GaitDetector()
    for i in range(60):  # 2 full cycles
        t = i / 30.0
        h = BBOX[3]
        # Diagonal pair 1 (LF + RH) in phase (phase 0)
        # Diagonal pair 2 (RF + LH) in phase (phase π/2)
        lf_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t)))
        rh_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t)))              # same as LF
        rf_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t + math.pi / 2)))
        lh_y = int(h * (0.7 + 0.18 * math.sin(2 * math.pi * t + math.pi / 2)))  # same as RF
        kpts = _make_keypoints(lf_y, rf_y, lh_y, rh_y)
        detector.update(kpts, BBOX)
    result = detector.detect()
    assert result.name == "Trab", f"Expected Trab, got {result}"


def test_reset_via_new_instance():
    """Two independent instances don't share state."""
    d1 = GaitDetector()
    d2 = GaitDetector()
    for _ in range(30):
        kpts = _make_keypoints(250, 250, 250, 250)
        d1.update(kpts, BBOX)
    # d2 has no frames
    assert d2.detect().name == "---"
    assert d1.detect().name == "Schritt"
