"""Frame access helpers: sequential sampling and timestamp seeking."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

from ..core.task_queue import CancellationToken


class VideoReader:
    """Thin wrapper around cv2.VideoCapture with safe seeking."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            raise OSError(f"Could not open video: {self.path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.duration = self.frame_count / self.fps if self.fps else 0.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def seek(self, timestamp: float) -> bool:
        frame_no = max(0, int(timestamp * self.fps))
        return self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)

    def read(self) -> np.ndarray | None:
        ok, frame = self.cap.read()
        return frame if ok else None

    def read_at(self, timestamp: float) -> np.ndarray | None:
        self.seek(timestamp)
        return self.read()

    def sample(self, interval_sec: float,
               token: CancellationToken | None = None,
               start: float = 0.0, end: float | None = None) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (timestamp, frame) pairs at a fixed interval (no full decode)."""
        stop = self.duration if end is None else min(end, self.duration)
        t = start
        while t < stop:
            if token:
                token.check()
            frame = self.read_at(t)
            if frame is None:
                break
            yield t, frame
            t += interval_sec

    def close(self) -> None:
        if self.cap.isOpened():
            self.cap.release()

    def __enter__(self) -> "VideoReader":
        return self

    def __exit__(self, *args) -> None:
        self.close()
