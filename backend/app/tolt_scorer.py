from dataclasses import dataclass, field

import numpy as np


@dataclass
class ToltError:
    type: str
    severity: str
    frame_range: tuple[int, int]
    description: str


@dataclass
class ToltScore:
    score: float
    feif_grade: str
    errors: list[ToltError]
    takt_regularity: float
    beat_intervals: list[float]
    disclaimer: str
    lap: float | None = None
    df: float | None = None
    subclassification: str | None = None


_DISCLAIMER = (
    "Experimentelle Analyse – kein offizieller FEIF-Befund. "
    "Ergebnis basiert auf automatisch erkannten Keypoints."
)

_CONTACT_THRESHOLD = 0.78
_SIMULTANEOUS_FRAMES = 3
_MIN_FRAMES = 20

_DIAGONAL_PAIRS = {frozenset({"VL", "HR"}), frozenset({"VR", "HL"})}
_LATERAL_PAIRS  = {frozenset({"VL", "HL"}), frozenset({"VR", "HR"})}

_CORRECT_ORDER = ["HL", "VL", "HR", "VR"]


def _feif_grade(score: float) -> str:
    clamped = max(0.0, min(10.0, score))
    rounded = round(clamped * 2) / 2
    return f"{rounded:.1f}"


def _find_landings(y_arr: np.ndarray) -> np.ndarray:
    """Frames where hoof transitions from air (y<threshold) to ground (y>=threshold)."""
    on_ground = y_arr >= _CONTACT_THRESHOLD
    transitions = np.where(~on_ground[:-1] & on_ground[1:])[0] + 1
    return transitions


class ToltScorer:
    def score(
        self,
        tracks: dict[str, list],
        fps: float = 25.0,
    ) -> ToltScore:
        leg_names = ["VL", "VR", "HL", "HR"]

        max_frame = 0
        for leg in leg_names:
            pts = tracks.get(leg, [])
            for p in pts:
                fn = p.frame if hasattr(p, "frame") else p["frame"]
                if fn > max_frame:
                    max_frame = fn

        if max_frame < _MIN_FRAMES:
            return ToltScore(
                score=0.0,
                feif_grade="–",
                errors=[],
                takt_regularity=0.0,
                beat_intervals=[],
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

        # LAP: (VL_landing – HL_landing) / T_stride, gemittelt über alle Schrittzyklen
        lap: float | None = None
        hl_land = landings["HL"]
        vl_land = landings["VL"]
        if len(hl_land) >= 2 and len(vl_land) >= 1:
            lap_vals: list[float] = []
            for idx in range(len(hl_land) - 1):
                hl_f    = int(hl_land[idx])
                hl_next = int(hl_land[idx + 1])
                t_stride = hl_next - hl_f
                if t_stride <= 0:
                    continue
                mask = (vl_land >= hl_f) & (vl_land < hl_next)
                vl_in = vl_land[mask]
                if len(vl_in) > 0:
                    lap_vals.append((int(vl_in[0]) - hl_f) / t_stride)
            if lap_vals:
                lap = float(np.mean(lap_vals))

        # DF: mittlerer Standphasenanteil aller 4 Beine
        df_vals = [
            float(np.mean(y_arrays[leg] >= _CONTACT_THRESHOLD))
            for leg in leg_names
            if len(y_arrays[leg]) > 0
        ]
        df: float | None = float(np.mean(df_vals)) if df_vals else None

        # Tölt-Subklassifikation nach FEIF-LAP-Grenzwerten
        subclassification: str | None = None
        if lap is not None:
            if lap < 0.22:
                subclassification = "passig"
            elif lap <= 0.28:
                subclassification = "correct"
            else:
                subclassification = "trabig"

        errors: list[ToltError] = []

        all_events: list[tuple[int, str]] = []
        for leg, frames in landings.items():
            for f in frames:
                all_events.append((int(f), leg))
        all_events.sort(key=lambda x: x[0])

        for i, (frame_a, leg_a) in enumerate(all_events):
            for j in range(i + 1, len(all_events)):
                frame_b, leg_b = all_events[j]
                if frame_b - frame_a > _SIMULTANEOUS_FRAMES:
                    break
                pair = frozenset({leg_a, leg_b})
                if pair in _DIAGONAL_PAIRS:
                    errors.append(ToltError(
                        type="trabeinlage",
                        severity="schwer",
                        frame_range=(frame_a, frame_b),
                        description=f"Trabeinlage: {leg_a}+{leg_b} landen gleichzeitig (Frame {frame_a}–{frame_b})",
                    ))
                elif pair in _LATERAL_PAIRS:
                    errors.append(ToltError(
                        type="pass_einlage",
                        severity="mittel",
                        frame_range=(frame_a, frame_b),
                        description=f"Pass-Einlage: {leg_a}+{leg_b} landen gleichzeitig (Frame {frame_a}–{frame_b})",
                    ))

        ms_per_frame = 1000.0 / fps if fps > 0 else 40.0
        beat_intervals_ms: list[float] = []

        if len(all_events) >= 2:
            for i in range(len(all_events) - 1):
                gap_frames = all_events[i + 1][0] - all_events[i][0]
                if gap_frames > _SIMULTANEOUS_FRAMES:
                    beat_intervals_ms.append(gap_frames * ms_per_frame)

        irregular_takt_count = 0
        if len(beat_intervals_ms) >= 4:
            arr_iv = np.array(beat_intervals_ms)
            median_iv = float(np.median(arr_iv))
            if median_iv > 0:
                deviations = np.abs(arr_iv - median_iv) / median_iv
                irregular_mask = deviations > 0.20
                irregular_takt_count = int(np.sum(irregular_mask))

                for idx, is_irr in enumerate(irregular_mask):
                    if is_irr:
                        f_start = all_events[idx][0] if idx < len(all_events) else 0
                        f_end   = all_events[idx + 1][0] if idx + 1 < len(all_events) else f_start
                        errors.append(ToltError(
                            type="unregelmaessiger_takt",
                            severity="leicht",
                            frame_range=(f_start, f_end),
                            description=(
                                f"Unregelmäßiger Takt: Intervall {arr_iv[idx]:.0f}ms "
                                f"({deviations[idx] * 100:.0f}% Abweichung vom Median {median_iv:.0f}ms)"
                            ),
                        ))

        if len(beat_intervals_ms) >= 2:
            arr_iv = np.array(beat_intervals_ms)
            mean_iv = float(np.mean(arr_iv))
            std_iv  = float(np.std(arr_iv))
            cv = std_iv / mean_iv if mean_iv > 0 else 1.0
            takt_regularity = float(np.clip(1.0 - cv / 0.5, 0.0, 1.0))
        else:
            takt_regularity = 0.0

        score = 7.0
        score += takt_regularity * 2.0

        trabeinlagen  = sum(1 for e in errors if e.type == "trabeinlage")
        pass_einlagen = sum(1 for e in errors if e.type == "pass_einlage")

        score -= trabeinlagen  * 1.5
        score -= pass_einlagen * 0.8
        score -= irregular_takt_count * 0.3

        score = float(np.clip(score, 0.0, 10.0))
        grade = _feif_grade(score)

        return ToltScore(
            score=round(score, 2),
            feif_grade=grade,
            errors=errors,
            takt_regularity=round(takt_regularity, 4),
            beat_intervals=beat_intervals_ms,
            disclaimer=_DISCLAIMER,
            lap=round(lap, 4) if lap is not None else None,
            df=round(df, 4) if df is not None else None,
            subclassification=subclassification,
        )
