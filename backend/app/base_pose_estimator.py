"""Abstrakte Basisklasse für alle Pose-Estimator-Implementierungen."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BasePoseEstimator(ABC):
    NUM_KEYPOINTS: int
    KEYPOINT_NAMES: list[str]

    @abstractmethod
    def estimate(
        self,
        frame: np.ndarray,  # BGR
        bbox: tuple[int, int, int, int],
        facing_left: bool = True,
    ) -> list[tuple[int, int, float]]:
        """Gibt Liste von (x, y, confidence) zurück, eine pro Keypoint."""

    @abstractmethod
    def keypoint_names(self) -> list[str]:
        """Namen der Keypoints in Reihenfolge."""
