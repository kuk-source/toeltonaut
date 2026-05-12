"""Lädt KI-Konfiguration aus backend/config.yaml.

Zirkuläre Imports vermeiden: Diese Datei darf NICHT config.py importieren.
"""
from __future__ import annotations

from pathlib import Path

import yaml  # PyYAML

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_ai_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class AIConfig:
    def __init__(self) -> None:
        cfg = load_ai_config()
        ai = cfg.get("ai", {})
        self.model_version: str = ai.get("model_version", "v0.1")
        self.model_path: str = ai.get("model_path", "yolov8n.pt")
        self.pose_model: str | None = ai.get("pose_model")
        self.pose_config: str | None = ai.get("pose_config")
        self.device: str = ai.get("device", "cpu")
        self.yolo_conf: float = ai.get("yolo_conf", 0.3)
        self.yolo_imgsz: int = ai.get("yolo_imgsz", 640)
        self.vid_stride: int = ai.get("vid_stride", 2)
        self.max_output_width: int = ai.get("max_output_width", 1920)
        upload = cfg.get("upload", {})
        self.upload_ttl_hours: int = int(upload.get("ttl_hours", 0))


_ai_config: AIConfig | None = None


def get_ai_config() -> AIConfig:
    global _ai_config
    if _ai_config is None:
        _ai_config = AIConfig()
    return _ai_config
