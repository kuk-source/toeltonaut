import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from ultralytics import YOLO

from .config import DATABASE_URL, YOLO_MODEL, YOLO_CONF, YOLO_IMGSZ, VID_STRIDE, MAX_OUTPUT_WIDTH
from .gait_detector import GaitDetector
from .pose_estimator import detect_facing
from .pose_factory import get_pose_estimator

HORSE_CLASS_ID = 17

_FOCUS_LOCK_FRAME   = 5     # Nach N verarbeiteten Frames wird Fokus-ID eingefroren
_IOU_THRESHOLD      = 0.30  # Mindest-IoU für IoU-Fallback
_HIST_CORR_MIN      = 0.70  # Mindest-Korrelation für Histogramm-Re-Identifikation
_HIST_RATIO_MIN     = 1.25  # Bester Score muss ≥25% besser sein als zweitbester
_PENDING_ID_CONFIRM = 8     # Frames bis neue ByteTrack-ID als Fokus akzeptiert wird
_MIN_ABSENT_FRAMES  = 8     # Mindest-Absenz-Frames vor Re-ID-Versuch
_BBOX_SIZE_RATIO    = 0.45  # Kandidat-Bbox muss ≥45% der Referenz-Höhe haben


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    xi1, yi1 = max(a[0], b[0]), max(a[1], b[1])
    xi2, yi2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)

_instance: "VideoProcessor | None" = None
_lock = threading.Lock()

logger = logging.getLogger(__name__)

# psycopg3 sync needs "postgresql://..." without the "+psycopg" driver suffix
_DB_URL_SYNC = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


class _DbWriter:
    """Hält eine einzige psycopg3-Verbindung für alle Frames eines Videos offen."""

    BATCH = 100

    def __init__(self, video_id: str) -> None:
        import psycopg  # type: ignore
        self._conn = psycopg.connect(_DB_URL_SYNC, autocommit=False)
        self._cur = self._conn.cursor()
        self._video_id = video_id
        self._count = 0

    def write(
        self,
        frame_nr: int,
        timestamp_ms: float,
        keypoints_data: list,
        gait: str | None = None,
        is_side_view: bool | None = None,
        write_keypoints: bool = True,
    ) -> None:
        from psycopg.types.json import Jsonb  # type: ignore
        self._cur.execute(
            "INSERT INTO frames (video_id, frame_nr, timestamp_ms, gait, is_side_view) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (self._video_id, frame_nr, timestamp_ms, gait, is_side_view),
        )
        row = self._cur.fetchone()
        if row and write_keypoints and keypoints_data:
            self._cur.execute(
                "INSERT INTO keypoints (frame_id, data) VALUES (%s, %s)",
                (row[0], Jsonb(keypoints_data)),
            )
        self._count += 1
        if self._count % self.BATCH == 0:
            self._conn.commit()

    def close(self) -> None:
        self._conn.commit()
        self._cur.close()
        self._conn.close()

    def __enter__(self) -> "_DbWriter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def get_processor() -> "VideoProcessor":
    global _instance
    with _lock:
        if _instance is None:
            _instance = VideoProcessor()
    return _instance


class VideoProcessor:
    def __init__(self) -> None:
        self.model = YOLO(YOLO_MODEL)

    def _reset_tracker(self) -> None:
        """ByteTrack-State aus vorherigem Video löschen, sonst Dimensions-Fehler beim nächsten Video."""
        try:
            if hasattr(self.model, 'predictor') and self.model.predictor is not None:
                for tracker in getattr(self.model.predictor, 'trackers', []):
                    tracker.reset()
                self.model.predictor = None
        except Exception:
            pass

    def process(
        self,
        input_path: str,
        output_path: str,
        progress_callback: Callable[[int, str], None],
        video_db_id: str | None = None,
        stockmass_cm: int | None = None,
    ) -> tuple[str, str | None, float | None, float]:
        """Verarbeitet Video: Pferd erkennen, Skelett zeichnen, Gangart erkennen, H.264 kodieren.
        Gibt (erkannte_gangart, erkannter_kamerawinkel, speed_ms, output_fps) zurück."""
        self._reset_tracker()
        cap = cv2.VideoCapture(input_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        scale = MAX_OUTPUT_WIDTH / orig_w if orig_w > MAX_OUTPUT_WIDTH else 1.0
        out_w = int(orig_w * scale) if scale != 1.0 else orig_w
        out_h = (int(orig_h * scale) & ~1) if scale != 1.0 else orig_h

        tmp_path = output_path + ".tmp.mp4"
        writer = cv2.VideoWriter(
            tmp_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps / VID_STRIDE,
            (out_w, out_h),
        )

        pose_est = get_pose_estimator()
        fetlock_indices = getattr(pose_est, "FETLOCK_INDICES", None)
        gait_detector = GaitDetector(fps=fps, vid_stride=VID_STRIDE, fetlock_indices=fetlock_indices, stockmass_cm=stockmass_cm)
        current_gait: str | None = None
        gait_counts: dict[str, int] = {}   # für dominante Gangart am Ende
        pending_gait: str | None = None
        pending_count: int = 0
        MIN_HOLD = 10
        focus_horse_id: int | None = None
        last_known_box: tuple[int, int, int, int] | None = None
        _warmup_areas: dict[int, float] = {}
        _focus_histogram: np.ndarray | None = None
        _pending_new_id: int | None = None
        _pending_new_id_count: int = 0
        _focus_absent_count: int = 0   # aufeinanderfolgende Frames ohne Fokus-ID
        _focus_bbox_h_ref: float = 0.0  # Referenz-Bbox-Höhe des Fokuspferds (EMA)
        expected = max(1, total_frames // VID_STRIDE)
        facing_left_frames = 0
        facing_right_frames = 0
        db_writer: _DbWriter | None = None
        if video_db_id and _DB_URL_SYNC:
            try:
                db_writer = _DbWriter(video_db_id)
            except Exception:
                logger.exception("DB-Verbindung fehlgeschlagen – Keypoints werden nicht gespeichert")

        try:
            results = self.model.track(
                source=input_path,
                stream=True,
                classes=[HORSE_CLASS_ID],
                verbose=False,
                conf=YOLO_CONF,
                imgsz=YOLO_IMGSZ,
                device="cpu",
                vid_stride=VID_STRIDE,
                tracker="bytetrack.yaml",
                persist=True,
            )

            for i, result in enumerate(results):
                frame = result.orig_img.copy()
                if scale != 1.0:
                    frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)

                kpts: list[tuple[int, int]] | None = None
                if result.boxes is not None and len(result.boxes):
                    boxes = result.boxes
                    horse_indices = list(range(len(boxes)))
                    if not horse_indices:
                        writer.write(frame)
                        if i % 30 == 0:
                            pct = min(int(i / expected * 88), 88)
                            progress_callback(pct, f"Frame {i}/{expected} – {current_gait or '...'}")
                        continue

                    # ── Schicht 1: ID-basiertes Tracking (ByteTrack) ────────
                    track_ids = result.boxes.id
                    best_idx: int | None = None

                    def _horse_hist(j: int) -> np.ndarray | None:
                        raw = boxes[j].xyxy[0].tolist()
                        rx1, ry1 = int(raw[0]), int(raw[1])
                        rx2, ry2 = int(raw[2]), int(raw[3])
                        roi = result.orig_img[ry1:ry2, rx1:rx2]
                        if roi.size == 0:
                            return None
                        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                        h = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
                        cv2.normalize(h, h)
                        return h

                    if track_ids is not None:
                        id_list = track_ids.tolist()
                        horse_id_map = {j: int(id_list[j]) for j in horse_indices}

                        # Warm-up: Flächen + Histogramm PER ID akkumulieren, dann größte ID einfrieren.
                        # Wichtig: Histogramm erst NACH Lock aus der richtigen ID übernehmen –
                        # sonst fließen alle Pferde ins Referenz-Histogramm ein.
                        if focus_horse_id is None:
                            _warmup_hists: dict[int, np.ndarray] = getattr(self, '_warmup_hists_tmp', {})
                            for j, tid in horse_id_map.items():
                                area = float(
                                    (boxes[j].xyxy[0][2] - boxes[j].xyxy[0][0]) *
                                    (boxes[j].xyxy[0][3] - boxes[j].xyxy[0][1])
                                )
                                _warmup_areas[tid] = _warmup_areas.get(tid, 0.0) + area
                                h = _horse_hist(j)
                                if h is not None:
                                    _warmup_hists[tid] = h if tid not in _warmup_hists else (0.5 * _warmup_hists[tid] + 0.5 * h)
                            if i >= _FOCUS_LOCK_FRAME:
                                focus_horse_id = max(_warmup_areas, key=lambda k: _warmup_areas[k])
                                _focus_histogram = _warmup_hists.get(focus_horse_id)

                        if focus_horse_id is not None:
                            for j, tid in horse_id_map.items():
                                if tid == focus_horse_id:
                                    best_idx = j
                                    break

                    # ── Schicht 1b: Histogramm-Re-Identifikation bei ID-Neuvergabe ──────
                    # ByteTrack läuft, aber Fokus-ID nicht im Frame → Erscheinung vergleichen.
                    # Ratio-Test: bester Score muss deutlich besser sein als zweitbester.
                    # Re-ID erst nach _MIN_ABSENT_FRAMES Absenz-Frames (verhindert sofortigen
                    # Sprung wenn ein anderes Pferd kurz vorbeiläuft).
                    # Größen-Guard: Kandidat muss ≥_BBOX_SIZE_RATIO der Referenz-Bbox-Höhe.
                    if best_idx is None:
                        _focus_absent_count += 1
                    else:
                        _focus_absent_count = 0

                    if (best_idx is None and track_ids is not None
                            and focus_horse_id is not None and _focus_histogram is not None
                            and _focus_absent_count >= _MIN_ABSENT_FRAMES):
                        scores: list[tuple[float, int]] = []
                        for j in horse_indices:
                            # Größen-Guard: Kandidat zu klein → wahrscheinlich anderes Pferd im Hintergrund
                            if _focus_bbox_h_ref > 0:
                                cand_h = float(boxes[j].xyxy[0][3] - boxes[j].xyxy[0][1])
                                if cand_h < _focus_bbox_h_ref * _BBOX_SIZE_RATIO:
                                    continue
                            h = _horse_hist(j)
                            if h is not None:
                                corr = float(cv2.compareHist(_focus_histogram, h, cv2.HISTCMP_CORREL))
                                scores.append((corr, j))
                        scores.sort(reverse=True)
                        if scores and scores[0][0] >= _HIST_CORR_MIN:
                            ratio_ok = (len(scores) < 2
                                        or scores[1][0] <= 0
                                        or scores[0][0] / scores[1][0] >= _HIST_RATIO_MIN)
                            if ratio_ok:
                                best_j_hist = scores[0][1]
                                new_id = horse_id_map.get(best_j_hist)
                                if new_id is not None:
                                    if new_id == _pending_new_id:
                                        _pending_new_id_count += 1
                                        if _pending_new_id_count >= _PENDING_ID_CONFIRM:
                                            logger.debug("Focus ID confirmed: %d → %d after %d frames",
                                                         focus_horse_id, new_id, _pending_new_id_count)
                                            focus_horse_id = new_id
                                            _focus_absent_count = 0
                                            _pending_new_id = None
                                            _pending_new_id_count = 0
                                    else:
                                        _pending_new_id = new_id
                                        _pending_new_id_count = 1
                                best_idx = best_j_hist
                    elif best_idx is not None:
                        # Fokus-ID direkt im Frame → Pending-Zähler zurücksetzen
                        _pending_new_id = None
                        _pending_new_id_count = 0

                    # ── Schicht 2: IoU-Fallback – NUR wenn ByteTrack keine IDs liefert ─
                    # IoU-Fallback nur bei vollständigem Tracker-Ausfall (track_ids is None).
                    if best_idx is None and track_ids is None and last_known_box is not None:
                        best_iou = _IOU_THRESHOLD
                        for j in horse_indices:
                            raw = boxes[j].xyxy[0].tolist()
                            scaled_box = (int(raw[0]*scale), int(raw[1]*scale),
                                          int(raw[2]*scale), int(raw[3]*scale))
                            iou = _iou(scaled_box, last_known_box)
                            if iou > best_iou:
                                best_iou = iou
                                best_idx = j

                    # ── Schicht 3: Größte Box (nur während Warm-up) ──────────
                    if best_idx is None and focus_horse_id is None:
                        horse_areas = [
                            (boxes[j].xyxy[0][2] - boxes[j].xyxy[0][0]) *
                            (boxes[j].xyxy[0][3] - boxes[j].xyxy[0][1])
                            for j in horse_indices
                        ]
                        best_idx = horse_indices[int(max(range(len(horse_areas)), key=lambda k: horse_areas[k]))]

                    if best_idx is None:
                        writer.write(frame)
                        if i % 30 == 0:
                            pct = min(int(i / expected * 88), 88)
                            progress_callback(pct, f"Frame {i}/{expected} – {current_gait or '...'}")
                        continue

                    b = boxes[best_idx]
                    x1, y1, x2, y2 = [int(v * scale) for v in b.xyxy[0].tolist()]
                    last_known_box = (x1, y1, x2, y2)
                    # Histogramm + Referenz-Höhe nur aktualisieren wenn Fokus-ID direkt bestätigt
                    # (nicht während Pending-Phase, um Histogramm-Drift durch falsches Pferd zu verhindern)
                    focus_directly_confirmed = (
                        focus_horse_id is not None and _pending_new_id is None
                    )
                    if focus_directly_confirmed:
                        h_new = _horse_hist(best_idx)
                        if h_new is not None:
                            _focus_histogram = h_new if _focus_histogram is None else (0.85 * _focus_histogram + 0.15 * h_new)
                        raw_h = float(b.xyxy[0][3] - b.xyxy[0][1])
                        _focus_bbox_h_ref = raw_h if _focus_bbox_h_ref == 0.0 else (0.85 * _focus_bbox_h_ref + 0.15 * raw_h)
                    conf = float(b.conf[0])
                    w_bbox = x2 - x1
                    h_bbox = max(1, y2 - y1)
                    is_side_view = (w_bbox / h_bbox) >= 1.3
                    is_analyzable = (
                        is_side_view
                        and h_bbox / out_h >= 0.15          # nicht zu weit weg
                        and x1 > out_w * 0.03               # nicht links angeschnitten
                        and x2 < out_w * 0.97               # nicht rechts angeschnitten
                    )

                    facing = detect_facing(frame, x1, y1, x2, y2)
                    if facing:
                        facing_left_frames += 1
                    else:
                        facing_right_frames += 1
                    kpts = pose_est.estimate(frame, (x1, y1, x2, y2), facing)
                    gait_detector.update(kpts, (x1, y1, x2, y2), is_side_view=is_analyzable)
                    gait_result = gait_detector.detect()
                    if is_analyzable and gait_result.confidence > 0.40:
                        if gait_result.name == pending_gait:
                            pending_count += 1
                        else:
                            pending_gait = gait_result.name
                            pending_count = 1
                        if pending_count >= MIN_HOLD and pending_gait != current_gait:
                            current_gait = pending_gait
                        gait_counts[gait_result.name] = gait_counts.get(gait_result.name, 0) + 1
                    if db_writer and kpts:
                        actual_frame_nr = i * VID_STRIDE
                        timestamp_ms = actual_frame_nr * 1000.0 / fps
                        kp_names = pose_est.keypoint_names()
                        kp_data = [
                            {
                                "name": kp_names[idx],
                                "x": round(px / out_w, 4),
                                "y": round(py / out_h, 4),
                                "confidence": round(conf, 4),
                            }
                            for idx, (px, py, conf) in enumerate(kpts)
                        ]
                        try:
                            db_writer.write(actual_frame_nr, timestamp_ms, kp_data, current_gait,
                                           is_side_view=is_analyzable, write_keypoints=is_analyzable)
                        except Exception:
                            logger.exception("Keypoint-DB-Write fehlgeschlagen (frame %d)", actual_frame_nr)

                writer.write(frame)

                if i % 30 == 0:
                    pct = min(int(i / expected * 88), 88)
                    progress_callback(pct, f"Frame {i}/{expected} – {current_gait or '...'}")

        finally:
            writer.release()
            if db_writer:
                try:
                    db_writer.close()
                except Exception:
                    logger.exception("DB-Writer konnte nicht geschlossen werden")
        progress_callback(91, "Konvertiere zu H.264...")
        _transcode_h264(tmp_path, output_path)
        Path(tmp_path).unlink(missing_ok=True)
        # Dominante Gangart: >60% der erkannten Frames, sonst "Gemischt"
        if gait_counts:
            dominant = max(gait_counts, key=lambda g: gait_counts[g])
            total_counted = sum(gait_counts.values())
            detected = dominant if gait_counts[dominant] / total_counted > 0.60 else "Gemischt"
        else:
            detected = "Unbekannt"
        total_facing = facing_left_frames + facing_right_frames
        detected_angle: str | None = None
        if total_facing > 0:
            left_ratio = facing_left_frames / total_facing
            if left_ratio > 0.6:
                detected_angle = "seitlich_links"
            elif left_ratio < 0.4:
                detected_angle = "seitlich_rechts"
        # Sprint G3: Endgültige Geschwindigkeit aus dem letzten GaitDetector-Ergebnis lesen
        final_result = gait_detector.detect()
        speed_ms = final_result.speed_ms
        progress_callback(100, f"Fertig! Erkannte Gangart: {detected}")
        return detected, detected_angle, speed_ms, fps / VID_STRIDE


def _transcode_h264(src: str, dst: str) -> None:
    import imageio_ffmpeg
    import shutil
    r = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", src,
            "-vcodec", "libx264", "-preset", "fast", "-crf", "23",
            "-movflags", "+faststart", "-an", dst,
        ],
        capture_output=True,
    )
    if r.returncode != 0:
        shutil.copy2(src, dst)
