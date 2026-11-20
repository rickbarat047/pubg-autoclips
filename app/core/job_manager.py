"""JobManager tracks in-flight jobs and their cancellation tokens."""
from __future__ import annotations

import threading
from dataclasses import dataclass

from .event_bus import EventBus
from .task_queue import CancellationToken


@dataclass
class ActiveJob:
    id: int
    kind: str  # 'analysis' | 'export'
    match_id: int
    token: CancellationToken


class JobManager:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._active: dict[int, ActiveJob] = {}
        self._lock = threading.RLock()

    def register(self, job_id: int, kind: str, match_id: int,
                 token: CancellationToken) -> None:
        with self._lock:
            self._active[job_id] = ActiveJob(job_id, kind, match_id, token)

    def unregister(self, job_id: int) -> None:
        with self._lock:
            self._active.pop(job_id, None)

    def token(self, job_id: int) -> CancellationToken | None:
        with self._lock:
            job = self._active.get(job_id)
            return job.token if job else None

    def cancel(self, job_id: int) -> bool:
        token = self.token(job_id)
        if token:
            token.cancel()
            return True
        return False

    def pause(self, job_id: int) -> bool:
        token = self.token(job_id)
        if token:
            token.pause()
            return True
        return False

    def resume(self, job_id: int) -> bool:
        token = self.token(job_id)
        if token:
            token.resume()
            return True
        return False

    def is_active(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._active
