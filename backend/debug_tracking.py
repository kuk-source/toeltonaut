"""Diagnose-Skript: ByteTrack-Verhalten frame-für-frame analysieren.

Aufruf (im Container oder lokal):
    python debug_tracking.py <video_path> [--stride 2] [--frames 300]

Zeigt pro Frame: wie viele Pferde erkannt, welche IDs, ob Fokus-ID hält.
"""
import argparse
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

HORSE_CLASS_ID = 17
_FOCUS_LOCK_FRAME = 5
_IOU_THRESHOLD = 0.30


def iou(a, b):
    xi1, yi1 = max(a[0], b[0]), max(a[1], b[1])
    xi2, yi2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Pfad zum Video")
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--frames", type=int, default=300, help="Max. Frames analysieren")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--conf", type=float, default=0.3)
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"Video nicht gefunden: {args.video}", file=sys.stderr)
        sys.exit(1)

    cap = cv2.VideoCapture(args.video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    print(f"Video: {args.video}  |  {total} Frames  |  {fps:.1f} fps  |  stride={args.stride}")
    print()

    model = YOLO(args.model)

    focus_horse_id = None
    last_known_box = None
    warmup_areas: dict[int, float] = {}
    prev_selected_id = None
    switches = 0
    frames_no_horse = 0
    frames_iou_fallback = 0
    frames_id_match = 0

    results = model.track(
        source=args.video,
        stream=True,
        classes=[HORSE_CLASS_ID],
        verbose=False,
        conf=args.conf,
        imgsz=640,
        device="cpu",
        vid_stride=args.stride,
        tracker="bytetrack.yaml",
        persist=True,
    )

    print(f"{'Frame':>6}  {'#Horses':>7}  {'IDs':>18}  {'track_ids?':>10}  {'selected_id':>11}  {'Methode'}")
    print("-" * 80)

    for i, result in enumerate(results):
        if i * args.stride > args.frames:
            break

        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            frames_no_horse += 1
            if i < 50 or i % 30 == 0:
                print(f"{i*args.stride:>6}  {'–':>7}  {'–':>18}  {'–':>10}  {'–':>11}  kein Pferd")
            continue

        cls_list = boxes.cls.tolist()
        horse_indices = [j for j, c in enumerate(cls_list) if int(c) == HORSE_CLASS_ID]

        if not horse_indices:
            frames_no_horse += 1
            continue

        track_ids_tensor = boxes.id
        has_ids = track_ids_tensor is not None
        id_list = track_ids_tensor.tolist() if has_ids else []
        horse_id_map = {j: int(id_list[j]) for j in horse_indices} if has_ids else {}
        all_ids = list(horse_id_map.values()) if has_ids else []

        best_idx = None
        method = "?"

        # Schicht 1: ID-Tracking
        if has_ids:
            if focus_horse_id is None:
                for j, tid in horse_id_map.items():
                    area = float(
                        (boxes[j].xyxy[0][2] - boxes[j].xyxy[0][0]) *
                        (boxes[j].xyxy[0][3] - boxes[j].xyxy[0][1])
                    )
                    warmup_areas[tid] = warmup_areas.get(tid, 0.0) + area
                if i >= _FOCUS_LOCK_FRAME and warmup_areas:
                    focus_horse_id = max(warmup_areas, key=lambda k: warmup_areas[k])
                    print(f"  >>> Fokus-ID eingefroren: {focus_horse_id}  (Warm-up-Flächen: {dict(sorted(warmup_areas.items()))})")

            if focus_horse_id is not None:
                for j, tid in horse_id_map.items():
                    if tid == focus_horse_id:
                        best_idx = j
                        method = "ID-Match"
                        frames_id_match += 1
                        break

        # Schicht 2: IoU-Fallback – nur wenn track_ids is None
        if best_idx is None and track_ids_tensor is None and last_known_box is not None:
            best_iou_val = _IOU_THRESHOLD
            for j in horse_indices:
                raw = boxes[j].xyxy[0].tolist()
                sbox = (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
                v = iou(sbox, last_known_box)
                if v > best_iou_val:
                    best_iou_val = v
                    best_idx = j
                    method = f"IoU={v:.2f}"
                    frames_iou_fallback += 1

        # Schicht 3: Größte Box (Warm-up)
        if best_idx is None and focus_horse_id is None:
            areas = [(boxes[j].xyxy[0][2] - boxes[j].xyxy[0][0]) *
                     (boxes[j].xyxy[0][3] - boxes[j].xyxy[0][1]) for j in horse_indices]
            best_idx = horse_indices[int(max(range(len(areas)), key=lambda k: areas[k]))]
            method = "Warm-up-Größe"

        selected_id = horse_id_map.get(best_idx, "?") if best_idx is not None and has_ids else ("skip" if best_idx is None else "no-ids")

        if best_idx is not None:
            raw = boxes[best_idx].xyxy[0].tolist()
            last_known_box = (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))

        # Wechsel erkennen
        switched = ""
        if prev_selected_id not in (None, "skip") and selected_id not in ("skip", "?", "no-ids"):
            if selected_id != prev_selected_id:
                switched = " ◄◄ WECHSEL"
                switches += 1
        if selected_id != "skip":
            prev_selected_id = selected_id

        # Ausgabe (jeden Frame oder nur interessante)
        if len(horse_indices) > 1 or switched or not has_ids or i < 30 or i % 60 == 0:
            ids_str = str(all_ids) if all_ids else "–"
            print(f"{i*args.stride:>6}  {len(horse_indices):>7}  {ids_str:>18}  {'Ja':>10}  {str(selected_id):>11}  {method}{switched}")

    print()
    print("=" * 80)
    print(f"Verarbeitete Frames:  {i+1}")
    print(f"Frames ohne Pferd:    {frames_no_horse}")
    print(f"Frames per ID-Match:  {frames_id_match}")
    print(f"Frames per IoU-Fall:  {frames_iou_fallback}")
    print(f"Pferd-Wechsel:        {switches}")
    print(f"Fokus-ID am Ende:     {focus_horse_id}")


if __name__ == "__main__":
    main()
