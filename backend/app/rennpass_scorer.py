from dataclasses import dataclass, field

import numpy as np


@dataclass
class RennpassError:
    type: str
    severity: str
    frame_range: tuple[int, int]
    description: str


@dataclass
class RennpassScore:
    score: float
    feif_grade: str
    errors: list[RennpassError]
    lateral_sync: float
    suspension_detected: bool
    stride_count: int
    disclaimer: str


_DISCLAIMER = (
    "Experimentelle Analyse – kein offizieller FEIF-Befund. "
    "Ergebnis basiert auf automatisch erkannten Keypoints."
)

_CONTACT_THRESHOLD = 0.78
_SUSPENSION_THRESHOLD = 0.70
_LATERAL_WINDOW_FRAMES = 4
_MIN_FRAMES = 20

_LATERAL_PAIRS: dict[str, str] = {
    "VL": "HL",
    "HL": "VL",
    "VR": "HR",
    "HR": "VR",
}

_DIAGONAL_PAIRS = {frozenset({"VL", "HR"}), frozenset({"VR", "HL"})}


def _feif_grade(score: float) -> str:
    clamped = max(0.0, min(10.0, score))
    rounded = round(clamped * 2) / 2
    return f"{rounded:.1f}"


def _find_landings(y_arr: np.ndarray) -> np.ndarray:
    on_ground = y_arr >= _CONTACT_THRESHOLD
    transitions = np.where(~on_ground[:-1] & on_ground[1:])[0] + 1
    return transitions


class RennpassScorer:
    def score(
        self,
        tracks: dict[str, list],
        fps: float = 25.0,
    ) -> RennpassScore:
        leg_names = ["VL", "VR", "HL", "HR"]

        max_frame = 0
        for leg in leg_names:
            for p in tracks.get(leg, []):
                fn = p.frame if hasattr(p, "frame") else p["frame"]
                if fn > max_frame:
                    max_frame = fn

        if max_frame < _MIN_FRAMES:
            return RennpassScore(
                score=0.0,
                feif_grade="–",
                errors=[],
                lateral_sync=0.0,
                suspension_detected=False,
                stride_count=0,
                disclaimer=(
                    f"Zu wenige Frames ({max_frame} < {_MIN_FRAMES}) für eine Auswertung. "
                    + _DISCLAIMER
                ),
            )

        n = max_frame + 1
        y_arrays: dict[str, np.ndarray] = {}
        for leg in leg_names:
            arr = np.zeros(n)
            for p in tracks.get(leg, []):
                fn = p.frame if hasattr(p, "frame") else p["frame"]
                yn = p.y_norm if hasattr(p, "y_norm") else p["y_norm"]
                if fn < n:
                    arr[fn] = yn
            y_arrays[leg] = arr

        landings: dict[str, np.ndarray] = {
            leg: _find_landings(y_arrays[leg]) for leg in leg_names
        }

        all_events: list[tuple[int, str]] = []
        for leg, frames in landings.items():
            for f in frames:
                all_events.append((int(f), leg))
        all_events.sort(key=lambda x: x[0])

        errors: list[RennpassError] = []

        lateral_total = 0
        lateral_matched = 0

        for i, (frame_a, leg_a) in enumerate(all_events):
            lateral_total += 1
            partner = _LATERAL_PAIRS[leg_a]
            found_lateral = False
            for j in range(i + 1, len(all_events)):
                frame_b, leg_b = all_events[j]
                if frame_b - frame_a > _LATERAL_WINDOW_FRAMES:
                    break
                if leg_b == partner:
                    found_lateral = True
                    lateral_matched += 1
                    ms_per_frame = 1000.0 / fps if fps > 0 else 40.0
                    versatz_ms = (frame_b - frame_a) * ms_per_frame
                    if versatz_ms > 20.0:
                        errors.append(RennpassError(
                            type="lateraler_versatz",
                            severity="schwer" if versatz_ms > 40.0 else "mittel",
                            frame_range=(frame_a, frame_b),
                            description=(
                                f"Lateraler Versatz: {leg_a}+{partner} Landung "
                                f"{versatz_ms:.0f}ms auseinander (Frame {frame_a}–{frame_b})"
                            ),
                        ))
                    break

            if not found_lateral:
                pair_legs: list[str] = []
                for j in range(i + 1, len(all_events)):
                    frame_b, leg_b = all_events[j]
                    if frame_b - frame_a > _LATERAL_WINDOW_FRAMES:
                        break
                    pair = frozenset({leg_a, leg_b})
                    if pair in _DIAGONAL_PAIRS:
                        pair_legs.append(leg_b)
                if pair_legs:
                    errors.append(RennpassError(
                        type="sequenz_fehler",
                        severity="schwer",
                        frame_range=(frame_a, frame_a + _LATERAL_WINDOW_FRAMES),
                        description=(
                            f"Sequenz-Fehler: {leg_a} landet diagonal mit {pair_legs[0]} "
                            f"statt lateral mit {partner} (Frame {frame_a})"
                        ),
                    ))

        lateral_sync = lateral_matched / lateral_total if lateral_total > 0 else 0.0

        all_in_air = np.ones(n, dtype=bool)
        for leg in leg_names:
            all_in_air &= y_arrays[leg] < _SUSPENSION_THRESHOLD
        suspension_detected = bool(np.any(all_in_air))

        stride_count = max(len(landings["VL"]), len(landings["VR"]))

        if not suspension_detected:
            errors.append(RennpassError(
                type="keine_schwebephase",
                severity="mittel",
                frame_range=(0, n - 1),
                description="Keine Schwebephase erkannt – alle 4 Hufe waren nie gleichzeitig in der Luft",
            ))

        score = 7.0
        sync_bonus = lateral_sync * 2.5
        score += sync_bonus
        if suspension_detected:
            score += 0.5

        versatz_events = sum(1 for e in errors if e.type == "lateraler_versatz")
        sequenz_fehler = sum(1 for e in errors if e.type == "sequenz_fehler")

        score -= versatz_events * 0.8
        score -= sequenz_fehler * 1.5

        score = float(np.clip(score, 0.0, 10.0))
        grade = _feif_grade(score)

        return RennpassScore(
            score=round(score, 2),
            feif_grade=grade,
            errors=errors,
            lateral_sync=round(lateral_sync, 4),
            suspension_detected=suspension_detected,
            stride_count=stride_count,
            disclaimer=_DISCLAIMER,
        )
