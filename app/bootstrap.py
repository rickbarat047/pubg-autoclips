"""Application dependency container / bootstrap."""
from __future__ import annotations

from .config import AppSettings
from .core.event_bus import EventBus
from .core.job_manager import JobManager
from .database.db import DatabaseManager
from .utils.logging import get_logger
from .utils.paths import ensure_dirs

log = get_logger("bootstrap")


class AppContext:
    """Holds shared services and settings for the whole application."""

    def __init__(self) -> None:
        ensure_dirs()
        self.settings = AppSettings.load()
        self.db = DatabaseManager()
        self.bus = EventBus()
        self.jobs = JobManager(self.bus)
        self._threads: list = []
        log.info("Application context initialised")

    def save_settings(self) -> None:
        self.settings.save()
        self.bus.publish("settings_changed")

    def register_thread(self, thread) -> None:
        self._threads.append(thread)

    def shutdown(self) -> None:
        for t in list(self._threads):
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(3000)
            except Exception:
                pass
        self.db.close()
        log.info("Application context shut down")
