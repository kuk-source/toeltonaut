"""
MMPose Pose-Estimator v0.2 – hrnet_w32_horse10 (22 Keypoints, mAP ~88).

Oxford VGG Horse-10 Keypoints (echte Indizes aus dem Dataset):
  0: Nose              1: Eye
  2: Nearknee          3: Nearfrontfetlock   ← LF (left front)
  4: Nearfrontfoot     5: Offknee
  6: Offfrontfetlock   ← RF (right front)    7: Offfrontfoot
  8: Shoulder          9: Midshoulder        10: Elbow          11: Girth
  12: Wither          13: Nearhindhock
  14: Nearhindfetlock  ← LH (left hind)     15: Nearhindfoot
  16: Hip             17: Stifle            18: Offhindhock
  19: Offhindfetlock   ← RH (right hind)   20: Offhindfoot     21: Ischium

FETLOCK_INDICES: lf=3, rf=6, lh=14, rh=19, withers=12
  (werden von GaitDetector für LAP/DF-Berechnung verwendet)

Benötigt: mmcv + mmpose (nicht in requirements.txt).
Docker: im Dockerfile separat via pip/mim installiert.
Fallback: model_version: v0.1 in config.yaml
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .base_pose_estimator import BasePoseEstimator

# Reale Horse-10-Keypoints im Oxford VGG Schema
HORSE10_KEYPOINTS: list[str] = [
    "Nose",             # 0
    "Eye",              # 1
    "Nearknee",         # 2  linkes Vorderknie
    "Nearfrontfetlock", # 3  ← LF Fesselgelenk
    "Nearfrontfoot",    # 4
    "Offknee",          # 5  rechtes Vorderknie
    "Offfrontfetlock",  # 6  ← RF Fesselgelenk
    "Offfrontfoot",     # 7
    "Shoulder",         # 8
    "Midshoulder",      # 9
    "Elbow",            # 10
    "Girth",            # 11
    "Wither",           # 12 ← Widerrist (Topline)
    "Nearhindhock",     # 13 linkes Sprunggelenk
    "Nearhindfetlock",  # 14 ← LH Fesselgelenk
    "Nearhindfoot",     # 15
    "Hip",              # 16
    "Stifle",           # 17 linkes Kniegelenk hinten
    "Offhindhock",      # 18 rechtes Sprunggelenk
    "Offhindfetlock",   # 19 ← RH Fesselgelenk
    "Offhindfoot",      # 20
    "Ischium",          # 21
]

# Default config + checkpoint im Docker-Image-Pfad
_DEFAULT_CONFIG = Path("/app/models/horse10_hrnet_w32_1x.py")
_DEFAULT_CHECKPOINT = Path("/app/models/hrnet_w32_horse10_256x256_split1.pth")


class MMPosePoseEstimator(BasePoseEstimator):
    """v0.2: Echter ML-Pose-Estimator via MMPose hrnet_w32_horse10."""

    NUM_KEYPOINTS = 22
    KEYPOINT_NAMES = HORSE10_KEYPOINTS

    # KP-Indizes für GaitDetector (LAP/DF-Berechnung)
    FETLOCK_INDICES = {
        "l_front":  3,   # Nearfrontfetlock
        "r_front":  6,   # Offfrontfetlock
        "l_hind":  14,   # Nearhindfetlock
        "r_hind":  19,   # Offhindfetlock
        "withers": 12,   # Wither
        "l_hock":  13,   # Nearhindhock  (Sprunggelenk HL)
        "r_hock":  18,   # Offhindhock   (Sprunggelenk HR)
        "stifle":  17,   # Stifle        (Kniegelenk HB)
        "l_carpus": 2,   # Nearknee      (Karpalgelenk VL)
        "r_carpus": 5,   # Offknee       (Karpalgelenk VR)
        "elbow":   10,   # Elbow         (Ellbogengelenk)
    }

    def __init__(self, model_path: str, config_path: str, device: str = "cpu") -> None:
        try:
            from mmpose.apis import init_model, inference_topdown  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "MMPose nicht installiert. Fallback: model_version: v0.1 in config.yaml."
            ) from exc

        # Auto-Fallback auf gebundelte Docker-Pfade
        if not config_path:
            config_path = str(_DEFAULT_CONFIG)
        if not model_path:
            model_path = str(_DEFAULT_CHECKPOINT)

        if not Path(config_path).exists():
            raise FileNotFoundError(f"MMPose-Config nicht gefunden: {config_path}")
        if not Path(model_path).exists():
            raise FileNotFoundError(f"MMPose-Checkpoint nicht gefunden: {model_path}")

        self._model = init_model(config_path, model_path, device=device)
        self._inference = inference_topdown

    def estimate(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        facing_left: bool = True,
    ) -> list[tuple[int, int, float]]:
        x1, y1, x2, y2 = bbox
        results = self._inference(self._model, frame, bboxes=[[x1, y1, x2, y2]])
        if not results:
            return [(0, 0, 0.0)] * self.NUM_KEYPOINTS
        kps = results[0].pred_instances.keypoints[0]
        scores = getattr(results[0].pred_instances, "keypoint_scores", None)
        if scores is not None:
            scores = scores[0].tolist()
        else:
            scores = [1.0] * len(kps)
        return [(int(x), int(y), float(s)) for (x, y), s in zip(kps, scores)]

    def keypoint_names(self) -> list[str]:
        return self.KEYPOINT_NAMES
