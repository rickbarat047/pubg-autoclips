"""Thumbnail generation worker."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from ..core.task_queue import CancellationToken
from ..media.thumbnail import make_thumbnail

log_module = __name__


@dataclass
class ThumbJob:
    video_path: str
    timestamp: float
    out_path: str
    key: str


class ThumbnailWorker(QObject):
    done = Signal(str, str)  # key, path

    def __init__(self, jobs: list[ThumbJob], token: CancellationToken | None = None) -> None:
        super().__init__()
        self.jobs = jobs
        self.token = token

    @Slot()
    def run(self) -> None:
        for job in self.jobs:
            if self.token and self.token.is_cancelled():
                break
            try:
                if make_thumbnail(job.video_path, job.timestamp, job.out_path):
                    self.done.emit(job.key, job.out_path)
            except Exception:
                pass
