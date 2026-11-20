"""Compilation worker — renders and verifies the final montage off the GUI thread."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from ..clips.compilation_builder import CompilationBuilder, Segment
from ..config import AppSettings
from ..core.task_queue import CancellationToken
from ..utils.logging import get_logger

log = get_logger("workers.compilation")


class CompilationWorker(QObject):
    started = Signal()
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(str, float, int)  # path, duration, segment_count
    failed = Signal(str)
    token: CancellationToken

    def __init__(self, source_path: str, segments: list[Segment],
                 output_path: str, settings: AppSettings,
                 token: CancellationToken, source_has_audio: bool = True,
                 video_duration: float = 0.0, preview: bool = False) -> None:
        super().__init__()
        self.source_path = source_path
        self.segments = segments
        self.output_path = output_path
        self.settings = settings
        self.token = token
        self.source_has_audio = source_has_audio
        self.video_duration = video_duration
        self.preview = preview

    @Slot()
    def run(self) -> None:
        self.started.emit()
        try:
            if self.token:
                self.token.check()
            builder = CompilationBuilder(self.settings)
            path = builder.build(
                self.source_path, self.segments, self.output_path,
                source_has_audio=self.source_has_audio,
                video_duration=self.video_duration,
                token=self.token,
                progress=lambda c, t, m: self.progress.emit(c, t, m),
                preview=self.preview,
            )
            from ..media.probe import MediaProbe
            duration = MediaProbe().probe(path).duration
            self.finished.emit(path, duration, len(self.segments))
        except Exception as exc:  # noqa: BLE001
            from ..core.task_queue import CancelledError
            if isinstance(exc, CancelledError):
                self.failed.emit("Compilation cancelled.")
            else:
                log.exception("Compilation worker failed")
                self.failed.emit(str(exc))
