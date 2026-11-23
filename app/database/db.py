"""DatabaseManager: thread-safe SQLite access with full CRUD helpers."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..core.exceptions import DatabaseError
from ..utils.logging import get_logger
from ..utils.paths import database_path
from . import migrations
from .models import AnalysisJob, Event, Export, Highlight, Match, row_to

log = get_logger("database")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DatabaseManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        migrations.migrate(self._connect())

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=30,
                                   check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ---------- settings ----------
    def get_settings(self, key: str, default=None):
        row = self._connect().execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value"]) if row else default

    def set_settings(self, key: str, value) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    # ---------- matches ----------
    def add_match(self, **kwargs) -> Match:
        kwargs.setdefault("created_at", utcnow())
        cols = ", ".join(kwargs)
        marks = ", ".join("?" for _ in kwargs)
        try:
            with self.transaction() as conn:
                cur = conn.execute(
                    f"INSERT INTO matches ({cols}) VALUES ({marks})",
                    tuple(kwargs.values()),
                )
                mid = cur.lastrowid
            return self.get_match(mid)
        except sqlite3.IntegrityError as exc:
            raise DatabaseError("This recording has already been imported.",
                                "Duplicate imports are detected by file path.") from exc

    def get_match(self, match_id: int) -> Match | None:
        row = self._connect().execute(
            "SELECT * FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        return row_to(Match, row)

    def get_match_by_path(self, path: str) -> Match | None:
        row = self._connect().execute(
            "SELECT * FROM matches WHERE path = ?", (str(path),)
        ).fetchone()
        return row_to(Match, row)

    def list_matches(self, limit: int = 100) -> list[Match]:
        rows = self._connect().execute(
            "SELECT * FROM matches ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [row_to(Match, r) for r in rows]

    def update_match_status(self, match_id: int, status: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE matches SET status=? WHERE id=?", (status, match_id))

    def delete_match(self, match_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM matches WHERE id=?", (match_id,))

    # ---------- analysis jobs ----------
    def create_job(self, match_id: int) -> AnalysisJob:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO analysis_jobs(match_id,status,stage,progress,started_at) "
                "VALUES(?,?,?,?,?)",
                (match_id, "pending", "queued", 0.0, utcnow()),
            )
            jid = cur.lastrowid
        return self.get_job(jid)

    def get_job(self, job_id: int) -> AnalysisJob | None:
        row = self._connect().execute(
            "SELECT * FROM analysis_jobs WHERE id=?", (job_id,)
        ).fetchone()
        return row_to(AnalysisJob, row)

    def get_latest_job(self, match_id: int) -> AnalysisJob | None:
        row = self._connect().execute(
            "SELECT * FROM analysis_jobs WHERE match_id=? ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()
        return row_to(AnalysisJob, row)

    def update_job(self, job_id: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE analysis_jobs SET {sets} WHERE id=?",
                (*fields.values(), job_id),
            )

    def list_jobs(self, match_id: int | None = None) -> list[AnalysisJob]:
        if match_id is None:
            rows = self._connect().execute(
                "SELECT * FROM analysis_jobs ORDER BY id DESC LIMIT 100"
            ).fetchall()
        else:
            rows = self._connect().execute(
                "SELECT * FROM analysis_jobs WHERE match_id=? ORDER BY id DESC",
                (match_id,),
            ).fetchall()
        return [row_to(AnalysisJob, r) for r in rows]

    # ---------- events ----------
    def add_event(self, **kwargs) -> Event:
        kwargs.setdefault("evidence_json", "{}")
        cols = ", ".join(kwargs)
        marks = ", ".join("?" for _ in kwargs)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO events ({cols}) VALUES ({marks})",
                tuple(kwargs.values()),
            )
            eid = cur.lastrowid
        return self.get_event(eid)

    def get_event(self, event_id: int) -> Event | None:
        row = self._connect().execute(
            "SELECT * FROM events WHERE id=?", (event_id,)
        ).fetchone()
        return row_to(Event, row)

    def list_events(self, match_id: int, job_id: int | None = None) -> list[Event]:
        if job_id is None:
            rows = self._connect().execute(
                "SELECT * FROM events WHERE match_id=? ORDER BY timestamp", (match_id,)
            ).fetchall()
        else:
            rows = self._connect().execute(
                "SELECT * FROM events WHERE match_id=? AND job_id=? ORDER BY timestamp",
                (match_id, job_id),
            ).fetchall()
        return [row_to(Event, r) for r in rows]

    def update_event(self, event_id: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.transaction() as conn:
            conn.execute(f"UPDATE events SET {sets} WHERE id=?",
                         (*fields.values(), event_id))

    def delete_events_for_job(self, job_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM events WHERE job_id=?", (job_id,))

    def delete_events_for_match(self, match_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM events WHERE match_id=?", (match_id,))

    # ---------- highlights ----------
    def add_highlight(self, **kwargs) -> Highlight:
        cols = ", ".join(kwargs)
        marks = ", ".join("?" for _ in kwargs)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO highlights ({cols}) VALUES ({marks})",
                tuple(kwargs.values()),
            )
            hid = cur.lastrowid
        return self.get_highlight(hid)

    def get_highlight(self, hid: int) -> Highlight | None:
        row = self._connect().execute(
            "SELECT * FROM highlights WHERE id=?", (hid,)
        ).fetchone()
        return row_to(Highlight, row)

    def list_highlights(self, match_id: int | None = None) -> list[Highlight]:
        if match_id is None:
            rows = self._connect().execute(
                "SELECT * FROM highlights ORDER BY score DESC"
            ).fetchall()
        else:
            rows = self._connect().execute(
                "SELECT * FROM highlights WHERE match_id=? ORDER BY score DESC",
                (match_id,),
            ).fetchall()
        return [row_to(Highlight, r) for r in rows]

    def update_highlight(self, hid: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.transaction() as conn:
            conn.execute(f"UPDATE highlights SET {sets} WHERE id=?",
                         (*fields.values(), hid))

    def delete_highlights_for_match(self, match_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM highlights WHERE match_id=?", (match_id,))

    # ---------- manual clip ranges (added by the user during review) ----------
    def add_manual_segment(self, match_id: int, start: float, end: float,
                           note: str = "") -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO manual_segments "
                "(match_id, start, end, note, created_at) VALUES (?,?,?,?,?)",
                (match_id, float(start), float(end), note, utcnow()),
            )
            return int(cur.lastrowid)

    def list_manual_segments(self, match_id: int) -> list[dict]:
        with self.transaction() as conn:
            rows = conn.execute(
                "SELECT id, match_id, start, end, note, created_at "
                "FROM manual_segments WHERE match_id=? ORDER BY start",
                (match_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_manual_segment(self, segment_id: int, start: float,
                              end: float) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE manual_segments SET start=?, end=? WHERE id=?",
                (float(start), float(end), segment_id),
            )

    def delete_manual_segment(self, segment_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM manual_segments WHERE id=?", (segment_id,))

    # ---------- exports ----------
    def add_export(self, **kwargs) -> Export:
        kwargs.setdefault("created_at", utcnow())
        cols = ", ".join(kwargs)
        marks = ", ".join("?" for _ in kwargs)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO exports ({cols}) VALUES ({marks})",
                tuple(kwargs.values()),
            )
            eid = cur.lastrowid
        return self.get_export(eid)

    def get_export(self, eid: int) -> Export | None:
        row = self._connect().execute(
            "SELECT * FROM exports WHERE id=?", (eid,)
        ).fetchone()
        return row_to(Export, row)

    def list_exports(self, limit: int = 100) -> list[Export]:
        rows = self._connect().execute(
            "SELECT * FROM exports ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [row_to(Export, r) for r in rows]

    def update_export(self, eid: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.transaction() as conn:
            conn.execute(f"UPDATE exports SET {sets} WHERE id=?",
                         (*fields.values(), eid))

    # ---------- stats ----------
    def stats(self) -> dict[str, int]:
        c = self._connect()
        return {
            "matches": c.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
            "highlights": c.execute("SELECT COUNT(*) FROM highlights").fetchone()[0],
            "exports": c.execute(
                "SELECT COUNT(*) FROM exports WHERE status='done'"
            ).fetchone()[0],
        }

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
