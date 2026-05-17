"""
ONNX-basierter Pose-Estimator für Töltonaut v0.2-rtmpose.

Erwartet ein ONNX-Modell im HRNet-W32-Format, trainiert auf dem Oxford VGG
Horse-10 Schema (22 Keypoints). Kein mmcv/mmpose nötig – läuft rein mit
onnxruntime (CPU-only).

Pre/Post-Processing repliziert exakt die MMPose TopdownAffine-Pipeline:
  1. GetBBoxCenterScale (padding=1.25)
  2. _fix_aspect_ratio  → quadratischer Crop (1:1 für 256×256 Input)
  3. get_warp_matrix    → cv2.warpAffine (kein Strecken, kein Beschneiden)
  4. ImageNet-Normalisierung
  5. Heatmap-argmax + refine_keypoints (±0.25 Subpixel)
  6. Inverse affine Rückprojektion → Original-Frame-Koordinaten

--------------------------------------------------------------------------
Modell-Export aus bestehendem MMPose-Checkpoint (im Backend-Container):
    python models/export_onnx.py
  oder manuell:
    from app.models.export_onnx import ...

Default-Suchpfad: /app/models/horse10_hrnet_w32.onnx
--------------------------------------------------------------------------

Horse-10 Keypoint-Schema (22 KP):
  0: Nose              1: Eye
  2: Nearknee          3: Nearfrontfetlock  ← LF Fesselgelenk
  4: Nearfrontfoot     5: Offknee
  6: Offfrontfetlock   ← RF Fesselgelenk   7: Offfrontfoot
  8: Shoulder          9: Midshoulder      10: Elbow          11: Girth
 12: Wither            13: Nearhindhock
 14: Nearhindfetlock   ← LH Fesselgelenk  15: Nearhindfoot
 16: Hip              17: Stifle           18: Offhindhock
 19: Offhindfetlock    ← RH Fesselgelenk  20: Offhindfoot    21: Ischium
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .base_pose_estimator import BasePoseEstimator

_DEFAULT_MODEL = Path("/app/models/horse10_hrnet_w32.onnx")

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

HORSE10_KEYPOINTS: list[str] = [
    "Nose",              # 0
    "Eye",               # 1
    "Nearknee",          # 2
    "Nearfrontfetlock",  # 3  ← LF
    "Nearfrontfoot",     # 4
    "Offknee",           # 5
    "Offfrontfetlock",   # 6  ← RF
    "Offfrontfoot",      # 7
    "Shoulder",          # 8
    "Midshoulder",       # 9
    "Elbow",             # 10
    "Girth",             # 11
    "Wither",            # 12
    "Nearhindhock",      # 13
    "Nearhindfetlock",   # 14 ← LH
    "Nearhindfoot",      # 15
    "Hip",               # 16
    "Stifle",            # 17
    "Offhindhock",       # 18
    "Offhindfetlock",    # 19 ← RH
    "Offhindfoot",       # 20
    "Ischium",           # 21
]


# ── Affine-Transform-Hilfsfunktionen (pure numpy/cv2, kein mmpose) ────────────

def _fix_aspect_ratio(scale: np.ndarray, aspect_ratio: float) -> np.ndarray:
    """Passt scale so an, dass w/h == aspect_ratio (wie MMPose TopdownAffine)."""
    w, h = scale
    if w > h * aspect_ratio:
        return np.array([w, w / aspect_ratio], dtype=np.float32)
    return np.array([h * aspect_ratio, h], dtype=np.float32)


def _get_warp_matrix(
    center: np.ndarray,
    scale: np.ndarray,
    rot_deg: float,
    output_size: tuple[int, int],
) -> np.ndarray:
    """2×3-Affinmatrix: Bbox-Region → output_size (wie MMPose get_warp_matrix)."""
    rot = np.deg2rad(rot_deg)
    cos_r, sin_r = np.cos(rot), np.sin(rot)
    src_w = scale[0]
    dst_w, dst_h = output_size

    src_dir = np.array([-src_w * 0.5 * cos_r, -src_w * 0.5 * sin_r], dtype=np.float32)
    dst_dir = np.array([-dst_w * 0.5, 0.0], dtype=np.float32)

    src = np.zeros((3, 2), dtype=np.float32)
    src[0] = center
    src[1] = center + src_dir
    d = src[1] - src[0]
    src[2] = src[1] + np.array([-d[1], d[0]])

    dst = np.zeros((3, 2), dtype=np.float32)
    dst[0] = np.array([dst_w * 0.5, dst_h * 0.5], dtype=np.float32)
    dst[1] = dst[0] + dst_dir
    d2 = dst[1] - dst[0]
    dst[2] = dst[1] + np.array([-d2[1], d2[0]])

    return cv2.getAffineTransform(src, dst)


def _decode_heatmaps(
    heatmaps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """argmax + refine_keypoints (±0.25 Subpixel) wie MSRAHeatmap.decode().

    Returns
    -------
    keypoints : (K, 2) float32 in Input-Space (z.B. 256×256)
    scores    : (K,)   float32 Konfidenz 0–1
    """
    K, H, W = heatmaps.shape
    flat = heatmaps.reshape(K, -1)
    flat_idx = np.argmax(flat, axis=1)
    scores = flat[np.arange(K), flat_idx].astype(np.float32)
    py, px = np.unravel_index(flat_idx, (H, W))
    kps = np.stack([px, py], axis=-1).astype(np.float32)

    # Subpixel-Refinement: ±0.25 in Richtung stärksten Gradienten
    for k in range(K):
        x, y = int(kps[k, 0]), int(kps[k, 1])
        dx = (heatmaps[k, y, x + 1] - heatmaps[k, y, x - 1]) if 1 < x < W - 1 else 0.0
        dy = (heatmaps[k, y + 1, x] - heatmaps[k, y - 1, x]) if 1 < y < H - 1 else 0.0
        kps[k] += np.sign([dx, dy]) * 0.25

    # Heatmap-Koordinaten → Input-Koordinaten (scale_factor = input/heatmap = 256/64 = 4)
    scale_factor = np.array([256.0 / W, 256.0 / H], dtype=np.float32)
    kps *= scale_factor
    return kps, np.clip(scores, 0.0, 1.0)


def _backproject(
    kps_input: np.ndarray,
    center: np.ndarray,
    scale: np.ndarray,
    input_size: tuple[int, int],
) -> np.ndarray:
    """Input-Space (256×256) → Original-Frame-Koordinaten (inverse affine)."""
    in_w, in_h = input_size
    kps = kps_input.copy().astype(np.float32)
    kps[:, 0] = kps[:, 0] / in_w * scale[0] + center[0] - scale[0] * 0.5
    kps[:, 1] = kps[:, 1] / in_h * scale[1] + center[1] - scale[1] * 0.5
    return kps


# ── Estimator ─────────────────────────────────────────────────────────────────

class OnnxPoseEstimator(BasePoseEstimator):
    """v0.2-rtmpose: Pose-Estimator via onnxruntime – kein mmcv/mmpose nötig."""

    NUM_KEYPOINTS = 22
    KEYPOINT_NAMES = HORSE10_KEYPOINTS

    FETLOCK_INDICES = {
        "lf":       3,
        "rf":       6,
        "lh":      14,
        "rh":      19,
        "withers": 12,
        "l_front":  3,
        "r_front":  6,
        "l_hind":  14,
        "r_hind":  19,
        "l_hock":  13,
        "r_hock":  18,
        "stifle":  17,
        "l_carpus": 2,
        "r_carpus": 5,
        "elbow":   10,
    }

    # Padding wie MMPose GetBBoxCenterScale
    _BBOX_PADDING = 1.25

    def __init__(
        self,
        model_path: str | None = None,
        input_size: tuple[int, int] = (256, 256),
    ) -> None:
        try:
            import onnxruntime as ort  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "onnxruntime ist nicht installiert. "
                "Bitte `pip install onnxruntime>=1.17` ausführen."
            ) from exc

        resolved = Path(model_path) if model_path else _DEFAULT_MODEL
        if not resolved.exists():
            raise FileNotFoundError(
                f"ONNX-Modell nicht gefunden: {resolved}\n"
                "Exportanleitung: siehe Docstring in onnx_pose_estimator.py"
            )

        self._input_size = input_size  # (W, H)
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 4
        self._session = ort.InferenceSession(
            str(resolved),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._input_name: str = self._session.get_inputs()[0].name

    def estimate(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        facing_left: bool = True,
    ) -> list[tuple[int, int, float]]:
        inp, center, scale = self._preprocess(frame, bbox)
        outputs = self._session.run(None, {self._input_name: inp})
        return self._postprocess(outputs, center, scale)

    def keypoint_names(self) -> list[str]:
        return self.KEYPOINT_NAMES

    # ------------------------------------------------------------------

    def _preprocess(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Affine-Transform-Crop → Normalize → CHW-Batch.

        Repliziert MMPose GetBBoxCenterScale + TopdownAffine exakt:
        - 1.25× Padding um Bbox
        - Aspect-Ratio auf quadratisch erzwingen (für 256×256 Input)
        - cv2.warpAffine (kein Strecken, kein Beschneiden)

        Returns (inp, center, scale) — center/scale für Rückprojektion.
        """
        x1, y1, x2, y2 = bbox
        h_fr, w_fr = frame.shape[:2]
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(w_fr, x2); y2 = min(h_fr, y2)

        in_w, in_h = self._input_size
        aspect_ratio = in_w / in_h  # = 1.0 für 256×256

        center = np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=np.float32)
        scale = np.array([x2 - x1, y2 - y1], dtype=np.float32) * self._BBOX_PADDING
        scale = _fix_aspect_ratio(scale, aspect_ratio)

        warp_mat = _get_warp_matrix(center, scale, rot_deg=0.0, output_size=(in_w, in_h))
        warped = cv2.warpAffine(frame, warp_mat, (in_w, in_h), flags=cv2.INTER_LINEAR)

        rgb = warped[:, :, ::-1].astype(np.float32) / 255.0
        rgb = (rgb - _MEAN) / _STD
        inp = rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32)  # (1, 3, H, W)
        return inp, center, scale

    def _postprocess(
        self,
        outputs: list[np.ndarray],
        center: np.ndarray,
        scale: np.ndarray,
    ) -> list[tuple[int, int, float]]:
        """Heatmap-Decode + Subpixel-Refinement + Inverse-Affine-Rückprojektion."""
        raw = np.squeeze(outputs[0])  # (22, 64, 64) oder (22, 3)

        if raw.ndim == 3:
            # Standard HRNet-Heatmap-Output
            kps_input, scores = _decode_heatmaps(raw)
            kps_frame = _backproject(kps_input, center, scale, self._input_size)
        elif raw.ndim == 2 and raw.shape[1] >= 2:
            # Direktes (x, y[, score])-Format — selten, aber defensiv unterstützt
            in_w, in_h = self._input_size
            kps_input = raw[:self.NUM_KEYPOINTS, :2].astype(np.float32)
            scores = raw[:self.NUM_KEYPOINTS, 2] if raw.shape[1] > 2 else np.ones(self.NUM_KEYPOINTS)
            kps_frame = _backproject(kps_input, center, scale, self._input_size)
        else:
            cx = int((center[0]))
            cy = int((center[1]))
            return [(cx, cy, 0.0)] * self.NUM_KEYPOINTS

        result: list[tuple[int, int, float]] = [
            (int(round(float(x))), int(round(float(y))), float(s))
            for (x, y), s in zip(kps_frame, scores)
        ]
        while len(result) < self.NUM_KEYPOINTS:
            result.append((0, 0, 0.0))
        return result
