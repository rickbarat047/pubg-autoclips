"""Export worker — renders clips one at a time off the GUI thread."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from ..config import AppSettings
from ..core.task_queue import CancellationToken
from ..rendering.export_manager import ExportManager, ExportRequest
from ..utils.logging import get_logger

log = get_logger("workers.export")


@dataclass
class ExportJob:
    request: ExportRequest
    highlight_id: int
    export_id: int


class ExportWorker(QObject):
    started = Signal()
    progress = Signal(int, int, str)  # current, total, message
    one_done = Signal(int, str)  # export_id, output path
    finished = Signal(int, int)  # succeeded, failed
    error = Signal(str)
    token: CancellationToken

    def __init__(self, jobs: list[ExportJob], settings: AppSettings,
                 manager: ExportManager, token: CancellationToken) -> None:
        super().__init__()
        self.jobs = jobs
        self.settings = settings
        self.manager = manager
        self.token = token

    @Slot()
    def run(self) -> None:
        self.started.emit()
        succeeded = failed = 0
        for idx, job in enumerate(self.jobs, 1):
            try:
                if self.token:
                    self.token.check()
                self.progress.emit(idx, len(self.jobs),
                                   f"Rendering clip {idx}/{len(self.jobs)}")
                path = self.manager.render(job.request, token=self.token)
                valid = self.manager.validate(path)
                if not valid:
                    log.warning("Exported clip failed validation: %s", path)
                self.one_done.emit(job.export_id, path)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                from ..core.task_queue import CancelledError
                if isinstance(exc, CancelledError):
                    break
                log.exception("Export failed for clip %d", job.highlight_id)
                self.error.emit(f"Clip {idx} failed: {exc}")
                failed += 1
        self.finished.emit(succeeded, failed)
