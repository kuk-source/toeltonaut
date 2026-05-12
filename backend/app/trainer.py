"""Fine-tuning: MMPose HRNet-W32 Head auf nutzereigenen Keypoints.

Strategie: Nur model.head (HeatmapHead, ~726 Parameter) wird trainiert –
alle Backbone-Schichten bleiben eingefroren. Auf CPU in ~30–60 Min für
300 annotierte Frames + 50 Epochen realistisch.

Aufruf aus main.py via start_training_thread() in daemon-Thread.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── In-Memory State (analog zu jobs: dict[str, JobState] in main.py) ─────────

@dataclass
class TrainingState:
    job_id: int
    status: str = "queued"   # queued | running | done | error
    epoch: int = 0
    total_epochs: int = 50
    loss: float = 0.0
    message: str = ""
    output_model_path: str = ""

_states: dict[int, TrainingState] = {}
_lock = threading.Lock()


# ── Dataset ───────────────────────────────────────────────────────────────────

class HorseKeypointDataset:
    """Mini-Dataset aus dem Bulk-COCO-ZIP (Töltonaut-Export-Format)."""

    _MEAN = np.array([123.675, 116.28,  103.53], dtype=np.float32)
    _STD  = np.array([58.395,  57.12,   57.375], dtype=np.float32)
    NUM_KP = 22

    def __init__(self, coco_json_path: str, root_dir: str, input_size: tuple[int, int] = (256, 256)):
        with open(coco_json_path) as f:
            coco = json.load(f)
        ann_by_img: dict[int, dict] = {a["image_id"]: a for a in coco["annotations"]}
        self.samples: list[dict] = []
        for img in coco["images"]:
            ann = ann_by_img.get(img["id"])
            if ann is None:
                continue
            self.samples.append({
                "path":      str(Path(root_dir) / img["file_name"]),
                "width":     img["width"],
                "height":    img["height"],
                "bbox":      ann["bbox"],        # [x, y, w, h] in Pixel
                "keypoints": ann["keypoints"],   # flat [x, y, v] × 22
            })
        self.root_dir = root_dir
        self.input_size = input_size

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        import torch
        s = self.samples[idx]
        img_bgr = cv2.imread(s["path"])
        if img_bgr is None:
            img_bgr = np.zeros((s["height"], s["width"], 3), dtype=np.uint8)
        img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

        # Crop mit 15 % Padding
        bx, by, bw, bh = s["bbox"]
        pad = 0.15
        x1 = max(0, int(bx - bw * pad))
        y1 = max(0, int(by - bh * pad))
        x2 = min(s["width"],  int(bx + bw * (1 + pad)))
        y2 = min(s["height"], int(by + bh * (1 + pad)))
        if x2 <= x1 or y2 <= y1:
            x1, y1, x2, y2 = 0, 0, s["width"], s["height"]
        crop = img[y1:y2, x1:x2]
        crop_w, crop_h = x2 - x1, y2 - y1

        resized = cv2.resize(crop, self.input_size).astype(np.float32)
        tensor_img = np.transpose((resized - self._MEAN) / self._STD, (2, 0, 1))  # CHW

        # Heatmap-Target (64×64, MSRA-Gaussian, sigma=2)
        H, W = 64, 64
        kps = np.array(s["keypoints"], dtype=np.float32).reshape(self.NUM_KP, 3)
        heatmaps = np.zeros((self.NUM_KP, H, W), dtype=np.float32)
        weights  = np.zeros(self.NUM_KP, dtype=np.float32)
        for i, (kx, ky, vis) in enumerate(kps):
            if vis == 0:
                continue
            rx = (kx - x1) / max(1, crop_w) * W
            ry = (ky - y1) / max(1, crop_h) * H
            heatmaps[i] = _gaussian(H, W, rx, ry, sigma=2.0)
            weights[i]  = 1.0

        return (
            torch.from_numpy(tensor_img),
            torch.from_numpy(heatmaps),
            torch.from_numpy(weights),
        )


def _gaussian(H: int, W: int, cx: float, cy: float, sigma: float) -> np.ndarray:
    x = np.arange(W, dtype=np.float32)
    y = np.arange(H, dtype=np.float32)[:, np.newaxis]
    return np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma ** 2))


# ── Freeze-Logik ──────────────────────────────────────────────────────────────

def _freeze_backbone(model) -> int:  # type: ignore[type-arg]
    """Friert alles ein bis auf model.head. Gibt Anzahl trainierter Parameter zurück."""
    for param in model.parameters():
        param.requires_grad = False
    head = getattr(model, "head", None)
    if head is not None:
        for param in head.parameters():
            param.requires_grad = True
    else:
        logger.warning("model.head nicht gefunden – fine-tuning ganzes Modell")
        for param in model.parameters():
            param.requires_grad = True
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# ── Training ──────────────────────────────────────────────────────────────────

def run_finetuning(
    job_id: int,
    zip_path: str,
    base_checkpoint: str,
    base_config: str,
    output_model_path: str,
    epochs: int = 50,
    lr: float = 1e-4,
    batch_size: int = 4,
) -> dict:
    """Führt Fine-tuning durch. Gibt metrics-Dict zurück."""
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader

    def _cb(ep: int, loss: float, msg: str = "running") -> None:
        with _lock:
            st = _states.get(job_id)
            if st:
                st.epoch  = ep
                st.loss   = loss
                st.status = msg if msg != "running" else st.status

    _cb(0, 0.0)

    # ZIP entpacken
    tmpdir = tempfile.mkdtemp(prefix="tlt_train_")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmpdir)
        coco_json = str(Path(tmpdir) / "annotations" / "coco.json")

        # Dataset + Loader
        ds = HorseKeypointDataset(coco_json, tmpdir)
        if len(ds) == 0:
            raise RuntimeError(
                "Keine Trainingsdaten – bitte Keypoints im Annotationstool korrigieren "
                "und Videos mit Trainingsfreigabe versehen."
            )
        loader = DataLoader(
            ds,
            batch_size=min(batch_size, len(ds)),
            shuffle=True,
            num_workers=0,
        )
        logger.info("Training: %d Samples, %d Epochen, lr=%.1e", len(ds), epochs, lr)

        # MMPose-Modell laden
        try:
            from mmpose.apis import init_model  # type: ignore
        except ImportError as exc:
            raise RuntimeError("MMPose nicht installiert.") from exc

        model = init_model(base_config, base_checkpoint, device="cpu")
        trainable = _freeze_backbone(model)
        logger.info("Trainierbare Parameter: %d / %d gesamt",
                    trainable, sum(p.numel() for p in model.parameters()))

        optimizer = optim.Adam(
            filter(lambda p: p.requires_grad, model.parameters()),
            lr=lr,
        )
        loss_fn = nn.MSELoss(reduction="none")

        # MLflow (optional)
        mlflow_run_id: str | None = None
        mlflow_ctx = None
        try:
            import mlflow  # type: ignore
            mlflow.set_tracking_uri("/app/mlruns")
            mlflow_ctx = mlflow.start_run()
            mlflow_run = mlflow_ctx.__enter__()
            mlflow.log_params({"epochs": epochs, "lr": lr, "samples": len(ds), "frozen": "backbone"})
            mlflow_run_id = mlflow_run.info.run_id
        except Exception:
            mlflow_ctx = None

        # Backbone im eval-Modus – BatchNorm-Statistiken eingefroren
        model.backbone.eval()
        head = getattr(model, "head", None)
        if head is not None:
            head.train()

        avg_loss = 0.0
        best_loss = float("inf")
        no_improve = 0
        last_epoch = 0

        for epoch in range(1, epochs + 1):
            epoch_loss = 0.0
            for imgs, targets, weights in loader:
                optimizer.zero_grad()
                with torch.no_grad():
                    feats = model.backbone(imgs)

                # Head-Forward: verschiedene MMPose-Versionen liefern unterschiedliche Typen
                if isinstance(feats, torch.Tensor):
                    feats = [feats]
                raw = head(feats) if head is not None else model(imgs)
                preds = raw[0] if isinstance(raw, (tuple, list)) else raw

                loss = (loss_fn(preds, targets) * weights[:, :, None, None]).mean()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / max(1, len(loader))
            last_epoch = epoch

            try:
                if mlflow_ctx:
                    import mlflow as _mlf  # type: ignore
                    _mlf.log_metric("train_loss", avg_loss, step=epoch)
            except Exception:
                pass

            _cb(epoch, avg_loss)

            # Early Stopping: 5 Epochen ohne Verbesserung (frühestens ab Epoche 10)
            if avg_loss < best_loss - 1e-6:
                best_loss = avg_loss
                no_improve = 0
            else:
                no_improve += 1
            if no_improve >= 5 and epoch >= 10:
                logger.info("Early Stopping: Epoche %d, loss=%.5f", epoch, avg_loss)
                break

        # Checkpoint speichern
        Path(output_model_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), output_model_path)
        logger.info("Checkpoint gespeichert: %s", output_model_path)

        if mlflow_ctx:
            try:
                import mlflow as _mlf  # type: ignore
                _mlf.log_artifact(output_model_path)
                _mlf.log_metrics({"final_loss": avg_loss, "epochs_run": last_epoch})
                mlflow_ctx.__exit__(None, None, None)
            except Exception:
                pass

        return {
            "mlflow_run_id": mlflow_run_id,
            "train_loss":    round(avg_loss, 6),
            "epochs_run":    last_epoch,
            "num_samples":   len(ds),
        }

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Thread-Einstiegspunkt ─────────────────────────────────────────────────────

def start_training_thread(
    job_id: int,
    zip_path: str,
    base_checkpoint: str,
    base_config: str,
    output_model_path: str,
    db_url: str,
) -> None:
    """Daemon-Thread-Einstiegspunkt. Schreibt Ergebnis via psycopg3 in DB."""
    try:
        result = run_finetuning(
            job_id=job_id,
            zip_path=zip_path,
            base_checkpoint=base_checkpoint,
            base_config=base_config,
            output_model_path=output_model_path,
        )
        with _lock:
            st = _states.get(job_id)
            if st:
                st.status  = "done"
                st.message = (
                    f"Fertig! Loss={result['train_loss']:.5f}, "
                    f"{result['epochs_run']} Epochen, "
                    f"{result['num_samples']} Samples"
                )

        # DB aktualisieren (sync psycopg3, kein asyncio im Thread)
        import psycopg  # type: ignore
        db_url_sync = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        metrics_json = json.dumps({k: v for k, v in result.items() if k != "mlflow_run_id"})
        with psycopg.connect(db_url_sync, autocommit=True) as conn:
            conn.execute(
                "UPDATE training_jobs SET mlflow_run_id=%s, metrics=%s WHERE id=%s",
                (result.get("mlflow_run_id"), metrics_json, job_id),
            )

    except Exception as exc:
        logger.exception("Fine-tuning Job %d fehlgeschlagen", job_id)
        with _lock:
            st = _states.get(job_id)
            if st:
                st.status  = "error"
                st.message = str(exc)
    finally:
        # ZIP-Tempfile aufräumen
        try:
            Path(zip_path).unlink(missing_ok=True)
        except OSError:
            pass
