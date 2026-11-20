"""Lightweight thread-safe publish/subscribe event bus."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[Callable[[Event], None], str | None]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, name: str, callback: Callable[[Event], None],
                  token: str | None = None) -> None:
        with self._lock:
            self._subscribers[name].append((callback, token))

    def unsubscribe(self, name: str, callback: Callable[[Event], None] | None = None,
                    token: str | None = None) -> None:
        with self._lock:
            items = self._subscribers.get(name, [])
            self._subscribers[name] = [
                (cb, tok) for (cb, tok) in items
                if not ((callback is None or cb == callback) and
                        (token is None or tok == token))
            ]

    def publish(self, name: str, **payload: Any) -> None:
        ev = Event(name=name, payload=payload)
        with self._lock:
            targets = list(self._subscribers.get(name, []))
            targets += list(self._subscribers.get("*", []))
        for cb, _ in targets:
            try:
                cb(ev)
            except Exception:
                # A faulty subscriber must never break the publisher.
                from ..utils.logging import get_logger
                get_logger("event_bus").exception("Subscriber failed for event %s", name)

    def clear(self, token: str | None = None) -> None:
        with self._lock:
            if token is None:
                self._subscribers.clear()
            else:
                for name in list(self._subscribers):
                    self._subscribers[name] = [
                        (cb, tok) for cb, tok in self._subscribers[name] if tok != token
                    ]
