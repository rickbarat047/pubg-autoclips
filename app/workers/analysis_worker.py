"""Analysis worker — runs the full pipeline off the GUI thread."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot

from ..config import AppSettings
from ..core.task_queue import CancellationToken
from ..database.db import DatabaseManager
from ..detection.pipeline import AnalysisPipeline, AnalysisResult
from ..utils.logging import get_logger

log = get_logger("workers.analysis")


class AnalysisWorker(QObject):
    started = Signal()
    progress = Signal(float, str, str)  # fraction, stage, message
    finished = Signal(object)
    error = Signal(str, str)
    token: CancellationToken

    def __init__(self, video_path: str, match_id: int, job_id: int,
                 duration: float, settings: AppSettings, db: DatabaseManager,
                 token: CancellationToken) -> None:
        super().__init__()
        self.video_path = video_path
        self.match_id = match_id
        self.job_id = job_id
        self.duration = duration
        self.settings = settings
        self.db = db
        self.token = token

    @Slot()
    def run(self) -> None:
        self.started.emit()
        try:
            pipeline = AnalysisPipeline(self.settings, self.db)
            result: AnalysisResult = pipeline.run(
                self.video_path, self.match_id, self.job_id, self.duration,
                token=self.token,
                overall_cb=lambda f, s, m: self.progress.emit(f, s, m),
            )
            self.db.update_job(
                self.job_id, status="done", stage="done", progress=1.0,
                finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self.db.update_match_status(self.match_id, "analysed")
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            from ..core.task_queue import CancelledError
            log.exception("Analysis worker failed")
            status = "cancelled" if isinstance(exc, CancelledError) else "failed"
            self.db.update_job(self.job_id, status=status,
                               error=str(exc)[:500])
            self.error.emit(status, str(exc))
