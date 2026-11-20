"""SQLite schema migrations, applied in order and tracked in schema_version."""
from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        file_size INTEGER NOT NULL DEFAULT 0,
        duration REAL NOT NULL DEFAULT 0,
        width INTEGER NOT NULL DEFAULT 0,
        height INTEGER NOT NULL DEFAULT 0,
        fps REAL NOT NULL DEFAULT 0,
        video_codec TEXT NOT NULL DEFAULT '',
        audio_codec TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'imported',
        file_hash TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS analysis_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending',
        stage TEXT NOT NULL DEFAULT '',
        progress REAL NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        error TEXT
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        job_id INTEGER NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        timestamp REAL NOT NULL,
        category TEXT NOT NULL DEFAULT 'UNKNOWN',
        confidence REAL NOT NULL DEFAULT 0,
        score REAL NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT '',
        recognised_text TEXT NOT NULL DEFAULT '',
        ocr_confidence REAL NOT NULL DEFAULT 0,
        evidence_json TEXT NOT NULL DEFAULT '{}',
        manual INTEGER NOT NULL DEFAULT 0,
        confirmed INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id);
    CREATE TABLE IF NOT EXISTS highlights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
        start REAL NOT NULL,
        end REAL NOT NULL,
        duration REAL NOT NULL,
        score REAL NOT NULL DEFAULT 0,
        category TEXT NOT NULL DEFAULT 'UNKNOWN',
        keep INTEGER NOT NULL DEFAULT 1,
        thumbnail TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_highlights_match ON highlights(match_id);
    CREATE TABLE IF NOT EXISTS exports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clip_id INTEGER NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
        path TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        layout TEXT NOT NULL DEFAULT 'blurred',
        error TEXT NOT NULL DEFAULT ''
    );
    """),
    (2, """
    -- Rebuild exports so compilation records (one per match, not per clip)
    -- can be stored alongside legacy individual-clip exports.
    CREATE TABLE IF NOT EXISTS exports_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clip_id INTEGER REFERENCES highlights(id) ON DELETE SET NULL,
        match_id INTEGER REFERENCES matches(id) ON DELETE SET NULL,
        export_type TEXT NOT NULL DEFAULT 'clip',
        path TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        duration REAL NOT NULL DEFAULT 0,
        segment_count INTEGER NOT NULL DEFAULT 0,
        layout TEXT NOT NULL DEFAULT 'blurred',
        error TEXT NOT NULL DEFAULT ''
    );
    INSERT INTO exports_new
        (id, clip_id, path, status, created_at, size_bytes, layout, error,
         export_type)
    SELECT id, clip_id, path, status, created_at, size_bytes, layout, error,
           'clip'
    FROM exports;
    DROP TABLE exports;
    ALTER TABLE exports_new RENAME TO exports;
    CREATE INDEX IF NOT EXISTS idx_exports_match ON exports(match_id);
    CREATE INDEX IF NOT EXISTS idx_exports_type ON exports(export_type);
    """),
]


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        conn.commit()
        return 0
    return int(row[0])


def migrate(conn: sqlite3.Connection) -> None:
    version = current_version(conn)
    for target, sql in MIGRATIONS:
        if target > version:
            conn.executescript(sql)
            conn.execute("UPDATE schema_version SET version = ?", (target,))
            conn.commit()
            version = target
