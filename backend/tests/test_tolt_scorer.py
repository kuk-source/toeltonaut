import pytest
from app.tolt_scorer import ToltScorer, _CONTACT_THRESHOLD


def _track(landing_frames: list[int], n: int, contact_len: int = 4) -> list[dict]:
    """Build a y_norm track: >= CONTACT_THRESHOLD at landing_frames, below otherwise."""
    high = _CONTACT_THRESHOLD + 0.05
    low  = _CONTACT_THRESHOLD - 0.30
    frames = []
    on_ground = set()
    for lf in landing_frames:
        for offset in range(contact_len):
            on_ground.add(lf + offset)
    for f in range(n):
        frames.append({"frame": f, "y_norm": high if f in on_ground else low})
    return frames


def _perfect_toelt(n_cycles: int = 4) -> dict:
    """HL→VL→HR→VR with equal spacing, no simultaneous landings."""
    cycle = 20
    n = n_cycles * cycle + 5
    offsets = {"HL": 0, "VL": 5, "HR": 10, "VR": 15}
    tracks = {}
    for leg, off in offsets.items():
        landings = [off + i * cycle for i in range(n_cycles) if off + i * cycle < n]
        tracks[leg] = _track(landings, n)
    return tracks


def test_too_few_frames_returns_zero():
    scorer = ToltScorer()
    tiny = {leg: [{"frame": f, "y_norm": 0.5} for f in range(5)] for leg in ("VL", "VR", "HL", "HR")}
    result = scorer.score(tiny, fps=25.0)
    assert result.score == 0.0
    assert result.feif_grade == "–"


def test_perfect_toelt_high_score():
    scorer = ToltScorer()
    tracks = _perfect_toelt(n_cycles=4)
    result = scorer.score(tracks, fps=25.0)
    assert result.score >= 7.0, f"Expected ≥7.0, got {result.score}"
    assert len([e for e in result.errors if e.type == "trabeinlage"]) == 0
    assert len([e for e in result.errors if e.type == "pass_einlage"]) == 0
    assert result.takt_regularity > 0.5


def test_trabeinlage_reduces_score_and_adds_error():
    """VL+HR landing simultaneously → Trabeinlage."""
    scorer = ToltScorer()
    n = 60
    landings = [5, 15, 25, 35, 45]
    tracks = {
        "VL": _track(landings, n),
        "HR": _track(landings, n),    # diagonal pair – same frames
        "VR": _track([10, 20, 30, 40], n),
        "HL": _track([10, 20, 30, 40], n),
    }
    result = scorer.score(tracks, fps=25.0)
    trabeinlagen = [e for e in result.errors if e.type == "trabeinlage"]
    assert len(trabeinlagen) >= 1, "Expected at least one Trabeinlage error"
    assert result.score < 7.0, f"Trabeinlage should penalize score, got {result.score}"


def test_pass_einlage_adds_error():
    """VL+HL landing simultaneously → Pass-Einlage."""
    scorer = ToltScorer()
    n = 60
    landings = [5, 15, 25, 35]
    tracks = {
        "VL": _track(landings, n),
        "HL": _track(landings, n),    # lateral pair – same frames
        "VR": _track([10, 20, 30, 40], n),
        "HR": _track([10, 20, 30, 40], n),
    }
    result = scorer.score(tracks, fps=25.0)
    pass_einlagen = [e for e in result.errors if e.type == "pass_einlage"]
    assert len(pass_einlagen) >= 1


def test_feif_grade_rounds_to_half():
    scorer = ToltScorer()
    tracks = _perfect_toelt(n_cycles=6)
    result = scorer.score(tracks, fps=25.0)
    # feif_grade must be a string like "7.5" or "8.0"
    grade_val = float(result.feif_grade)
    assert grade_val % 0.5 == 0.0
    assert 0.0 <= grade_val <= 10.0
