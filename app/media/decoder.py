"""Stateless frame-decoding helpers."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def frame_at(path: str | Path, timestamp: float) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(timestamp * fps)))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def downscale(frame: np.ndarray, max_dim: int = 960) -> np.ndarray:
    h, w = frame.shape[:2]
    if max(w, h) <= max_dim:
        return frame
    scale = max_dim / max(w, h)
    return cv2.resize(frame, (int(w * scale), int(h * scale)),
                      interpolation=cv2.INTER_AREA)
