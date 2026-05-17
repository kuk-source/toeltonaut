"""
ONNX-basierter Pose-Estimator für Töltonaut v0.2-rtmpose.

Erwartet ein ONNX-Modell im HRNet-W32- oder RTMPose-m-Format,
trainiert auf dem Oxford VGG Horse-10 Schema (22 Keypoints).
Kein mmcv/mmpose nötig – läuft rein mit onnxruntime (CPU-only).

Laut Benchmark ~3,4× schneller als MMPose/mmcv auf CPU.

--------------------------------------------------------------------------
Modell-Export aus bestehendem MMPose-Checkpoint:
    mim run mmpose tools/deployment/pytorch2onnx.py \\
        horse10_hrnet_w32_1x.py hrnet_w32_horse10_256x256_split1.pth \\
        --output-file horse10_hrnet_w32.onnx --shape 1 3 256 256

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

FETLOCK_INDICES: lf=3, rf=6, lh=14, rh=19 — kritisch für GaitDetector LAP/DF.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .base_pose_estimator import BasePoseEstimator

_DEFAULT_MODEL = Path("/app/models/horse10_hrnet_w32.onnx")

# ImageNet Normalisierung (Standard für Top-Down Pose-Modelle)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

HORSE10_KEYPOINTS: list[str] = [
    "Nose",              # 0
    "Eye",               # 1
    "Nearknee",          # 2  linkes Vorderknie (Karpalgelenk VL)
    "Nearfrontfetlock",  # 3  ← LF Fesselgelenk
    "Nearfrontfoot",     # 4
    "Offknee",           # 5  rechtes Vorderknie (Karpalgelenk VR)
    "Offfrontfetlock",   # 6  ← RF Fesselgelenk
    "Offfrontfoot",      # 7
    "Shoulder",          # 8
    "Midshoulder",       # 9
    "Elbow",             # 10
    "Girth",             # 11
    "Wither",            # 12 ← Widerrist (Topline)
    "Nearhindhock",      # 13 linkes Sprunggelenk
    "Nearhindfetlock",   # 14 ← LH Fesselgelenk
    "Nearhindfoot",      # 15
    "Hip",               # 16
    "Stifle",            # 17 linkes Kniegelenk hinten
    "Offhindhock",       # 18 rechtes Sprunggelenk
    "Offhindfetlock",    # 19 ← RH Fesselgelenk
    "Offhindfoot",       # 20
    "Ischium",           # 21
]


class OnnxPoseEstimator(BasePoseEstimator):
    """v0.2-rtmpose: Pose-Estimator via onnxruntime – kein mmcv/mmpose nötig."""

    NUM_KEYPOINTS = 22
    KEYPOINT_NAMES = HORSE10_KEYPOINTS

    # KP-Indizes für GaitDetector (LAP/DF-Berechnung)
    FETLOCK_INDICES = {
        "lf":       3,   # Nearfrontfetlock
        "rf":       6,   # Offfrontfetlock
        "lh":      14,   # Nearhindfetlock
        "rh":      19,   # Offhindfetlock
        "withers": 12,   # Wither
        "l_front":  3,
        "r_front":  6,
        "l_hind":  14,
        "r_hind":  19,
        "l_hock":  13,   # Nearhindhock  (Sprunggelenk HL)
        "r_hock":  18,   # Offhindhock   (Sprunggelenk HR)
        "stifle":  17,   # Stifle        (Kniegelenk HB)
        "l_carpus": 2,   # Nearknee      (Karpalgelenk VL)
        "r_carpus": 5,   # Offknee       (Karpalgelenk VR)
        "elbow":   10,   # Elbow
    }

    def __init__(
        self,
        model_path: str | None = None,
        input_size: tuple[int, int] = (256, 256),
    ) -> None:
        """
        Parameters
        ----------
        model_path:
            Pfad zur ONNX-Datei. Fehlt die Angabe, wird
            ``/app/models/horse10_hrnet_w32.onnx`` verwendet.
        input_size:
            (Breite, Höhe) des Modell-Inputs in Pixeln.
            Standard 256×256 für hrnet_w32_horse10.
        """
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

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def estimate(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        facing_left: bool = True,
    ) -> list[tuple[int, int, float]]:
        """
        Schätzt 22 Keypoints im Original-Frame-Koordinatensystem.

        Parameters
        ----------
        frame:      BGR-Frame (H × W × 3, uint8)
        bbox:       (x1, y1, x2, y2) Bounding-Box des Pferdes
        facing_left: wird für spätere Symmetrie-Korrekturen übergeben

        Returns
        -------
        Liste von (x, y, confidence) – eine pro Keypoint, Reihenfolge Horse-10.
        """
        inp, crop_info = self._preprocess(frame, bbox)
        outputs = self._session.run(None, {self._input_name: inp})
        return self._postprocess(outputs, bbox, crop_info)

    def keypoint_names(self) -> list[str]:
        return self.KEYPOINT_NAMES

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------

    def _preprocess(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> tuple[np.ndarray, dict]:
        """Crop → Resize → Normalize → CHW → Batch.

        Returns
        -------
        inp:        (1, 3, H, W) float32-Array für ONNX-Session
        crop_info:  dict mit x1, y1, crop_w, crop_h (für Rückprojektion)
        """
        x1, y1, x2, y2 = bbox
        h_frame, w_frame = frame.shape[:2]

        # Koordinaten auf Frame-Grenzen klemmen
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w_frame, x2)
        y2 = min(h_frame, y2)

        crop = frame[y1:y2, x1:x2]
        crop_h, crop_w = crop.shape[:2]

        if crop_h == 0 or crop_w == 0:
            # Leerer Crop → alle Keypoints auf (0,0,0)
            dummy = np.zeros((1, 3, self._input_size[1], self._input_size[0]), dtype=np.float32)
            return dummy, {"x1": x1, "y1": y1, "crop_w": 1, "crop_h": 1}

        # Resize auf Modell-Input
        import cv2
        resized = cv2.resize(crop, self._input_size, interpolation=cv2.INTER_LINEAR)

        # BGR → RGB, float32, /255
        rgb = resized[:, :, ::-1].astype(np.float32) / 255.0

        # ImageNet-Normalisierung
        rgb = (rgb - _MEAN) / _STD

        # HWC → CHW → Batch
        inp = rgb.transpose(2, 0, 1)[np.newaxis, ...]  # (1, 3, H, W)

        crop_info = {
            "x1": x1,
            "y1": y1,
            "crop_w": crop_w,
            "crop_h": crop_h,
        }
        return inp.astype(np.float32), crop_info

    def _postprocess(
        self,
        outputs: list[np.ndarray],
        bbox: tuple[int, int, int, int],
        crop_info: dict,
    ) -> list[tuple[int, int, float]]:
        """Heatmap-Peak oder direkte (x,y,score)-Ausgabe → Original-Koordinaten.

        Unterstützte Output-Formate:
        - Heatmap: (1, 22, H/4, W/4) – Standard HRNet
        - Direkt:  (1, 22, 3) oder (22, 3) – [x_norm, y_norm, score]
        """
        raw = outputs[0]  # erstes Output-Tensor
        raw = np.squeeze(raw)  # batch-Dim entfernen: z.B. (22, H, W) oder (22, 3)

        x1 = crop_info["x1"]
        y1 = crop_info["y1"]
        crop_w = crop_info["crop_w"]
        crop_h = crop_info["crop_h"]
        in_w, in_h = self._input_size

        result: list[tuple[int, int, float]] = []

        if raw.ndim == 3:
            # Heatmap-Format: (num_kp, hm_h, hm_w)
            num_kp, hm_h, hm_w = raw.shape
            for k in range(min(num_kp, self.NUM_KEYPOINTS)):
                hm = raw[k]
                flat_idx = int(np.argmax(hm))
                py, px = divmod(flat_idx, hm_w)
                conf = float(np.clip(hm.max(), 0.0, 1.0))
                # Heatmap-Pixel → Input-Pixel → Crop-Pixel → Frame-Pixel
                x_crop = px * (in_w / hm_w)
                y_crop = py * (in_h / hm_h)
                x_orig = int(x_crop * (crop_w / in_w) + x1)
                y_orig = int(y_crop * (crop_h / in_h) + y1)
                result.append((x_orig, y_orig, conf))

        elif raw.ndim == 2 and raw.shape[1] == 3:
            # Direktes Format: (num_kp, 3) mit [x_norm, y_norm, score]
            num_kp = raw.shape[0]
            for k in range(min(num_kp, self.NUM_KEYPOINTS)):
                xn, yn, score = raw[k]
                conf = float(np.clip(score, 0.0, 1.0))
                x_orig = int(float(xn) * crop_w + x1)
                y_orig = int(float(yn) * crop_h + y1)
                result.append((x_orig, y_orig, conf))

        elif raw.ndim == 2 and raw.shape[1] == 2:
            # Direktes Format: (num_kp, 2) mit [x_norm, y_norm], ohne Score
            num_kp = raw.shape[0]
            for k in range(min(num_kp, self.NUM_KEYPOINTS)):
                xn, yn = raw[k]
                x_orig = int(float(xn) * crop_w + x1)
                y_orig = int(float(yn) * crop_h + y1)
                result.append((x_orig, y_orig, 1.0))

        else:
            # Unbekanntes Format → Fallback: alle Keypoints auf Bbox-Mitte
            cx = int((bbox[0] + bbox[2]) / 2)
            cy = int((bbox[1] + bbox[3]) / 2)
            result = [(cx, cy, 0.0)] * self.NUM_KEYPOINTS
            return result

        # Fehlende Keypoints auffüllen (falls Modell weniger als 22 liefert)
        while len(result) < self.NUM_KEYPOINTS:
            result.append((0, 0, 0.0))

        return result
