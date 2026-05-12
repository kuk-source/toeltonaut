"""Factory: wählt Pose-Estimator anhand config.yaml aus.

Reihenfolge:
  1. model_version == "v0.2-mmpose" und pose_model gesetzt → MMPosePoseEstimator
     (bei ImportError oder RuntimeError automatischer Fallback auf v0.1)
  2. Alles andere → PropPoseEstimator (v0.1, kein Modell-Download)
"""
from __future__ import annotations

import logging

from .ai_config import get_ai_config
from .base_pose_estimator import BasePoseEstimator

_estimator: BasePoseEstimator | None = None

logger = logging.getLogger(__name__)


def get_pose_estimator() -> BasePoseEstimator:
    global _estimator
    if _estimator is not None:
        return _estimator

    cfg = get_ai_config()

    if cfg.model_version == "v0.2-mmpose" and cfg.pose_model:
        try:
            from .mmpose_estimator import MMPosePoseEstimator

            _estimator = MMPosePoseEstimator(
                model_path=cfg.pose_model,
                config_path=cfg.pose_config or "",
                device=cfg.device,
            )
            logger.info("MMPose hrnet_w32_horse10 geladen (v0.2).")
            return _estimator
        except Exception as exc:
            logger.warning(
                "MMPose nicht verfügbar (%s) – Fallback auf PropPoseEstimator (v0.1).", exc
            )

    from .prop_pose_estimator import PropPoseEstimator

    _estimator = PropPoseEstimator()
    logger.info("PropPoseEstimator (v0.1 proportionale Keypoints) aktiv.")
    return _estimator
