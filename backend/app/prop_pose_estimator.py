"""v0.1 – Proportionaler Pose-Estimator: Keypoints aus Bounding Box berechnet."""
from __future__ import annotations

import numpy as np

from .base_pose_estimator import BasePoseEstimator
from .pose_estimator import KEYPOINTS, estimate_keypoints


class PropPoseEstimator(BasePoseEstimator):
    """v0.1: Proportionale Keypoints aus Bounding Box – kein ML, kein Modell-Download."""

    NUM_KEYPOINTS = 31
    KEYPOINT_NAMES = [name for name, _, _ in KEYPOINTS]

    def estimate(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        facing_left: bool = True,
    ) -> list[tuple[int, int, float]]:
        return [(x, y, 1.0) for x, y in estimate_keypoints(bbox, facing_left)]

    def keypoint_names(self) -> list[str]:
        return self.KEYPOINT_NAMES
