"""Cancellation tokens and a small background task queue.

The Qt workers (see app/workers) use :class:`CancellationToken` directly.
:class:`TaskQueue` is a generic, framework-agnostic executor used for short
background tasks such as thumbnail generation.
"""
from __future__ import annotations

import threading
import queue
from dataclasses import dataclass, field
from typing import Any, Callable


class CancelledError(Exception):
    pass


class CancellationToken:
    """Thread-safe flag supporting cancel, pause and resume."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def pause(self) -> None:
        with self._lock:
            if not self._cancel.is_set():
                self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def check(self) -> None:
        """Raise :class:`CancelledError` if cancellation was requested."""
        if self._cancel.is_set():
            raise CancelledError("Operation cancelled")
        # Block while paused, waking periodically to notice cancellation.
        while self._pause.is_set():
            if self._cancel.is_set():
                raise CancelledError("Operation cancelled")
            self._pause.wait(0.1)


@dataclass
class Task:
    func: Callable[..., Any]
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    on_done: Callable[[Any], None] | None = None
    on_error: Callable[[Exception], None] | None = None
    name: str = "task"


class TaskQueue:
    """Single-worker FIFO queue for lightweight background jobs."""

    def __init__(self, name: str = "TaskQueue") -> None:
        self._q: queue.Queue[Task | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    def submit(self, task: Task) -> None:
        self._q.put(task)

    def _run(self) -> None:
        from ..utils.logging import get_logger
        log = get_logger("task_queue")
        while True:
            task = self._q.get()
            if task is None:
                break
            try:
                result = task.func(*task.args, **task.kwargs)
                if task.on_done:
                    task.on_done(result)
            except Exception as exc:  # noqa: BLE001
                log.exception("Task %s failed", task.name)
                if task.on_error:
                    try:
                        task.on_error(exc)
                    except Exception:
                        pass

    def shutdown(self) -> None:
        self._q.put(None)
        self._thread.join(timeout=5)
