"""Typed row models for the SQLite database."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Match:
    id: int
    path: str
    name: str
    file_size: int
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    created_at: str
    status: str
    file_hash: str = ""


@dataclass
class AnalysisJob:
    id: int
    match_id: int
    status: str
    stage: str
    progress: float
    started_at: str
    finished_at: str | None
    error: str | None


@dataclass
class Event:
    id: int
    match_id: int
    job_id: int
    timestamp: float
    category: str
    confidence: float
    score: float
    source: str
    recognised_text: str
    ocr_confidence: float
    evidence_json: str
    manual: bool
    confirmed: bool


@dataclass
class Highlight:
    id: int
    match_id: int
    event_id: int | None
    start: float
    end: float
    duration: float
    score: float
    category: str
    keep: bool
    thumbnail: str


@dataclass
class Export:
    id: int
    clip_id: int
    path: str
    status: str
    created_at: str
    size_bytes: int
    layout: str
    error: str


def row_to(obj: Any, row: Any) -> Any:
    """Convert a sqlite3.Row into a dataclass instance."""
    if row is None:
        return None
    fields = {f: row[f] for f in obj.__dataclass_fields__ if f in row.keys()}
    return obj(**fields)
