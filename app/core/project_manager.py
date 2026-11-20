"""ProjectManager: high-level operations over matches, jobs and results."""
from __future__ import annotations

from pathlib import Path

from ..database.db import DatabaseManager
from ..database.models import AnalysisJob, Event, Highlight, Match
from ..media.media_validator import MediaValidator, ValidationResult
from ..media.probe import MediaMetadata
from .exceptions import DatabaseError


class ProjectManager:
    """Facade used by the UI for all project-level operations."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.validator = MediaValidator()

    def validate(self, path: str | Path) -> ValidationResult:
        return self.validator.validate(str(path))

    def probe(self, path: str | Path) -> MediaMetadata:
        return self.validator.probe.probe(path)

    def import_match(self, path: str | Path) -> Match:
        """Import a recording, reusing an existing row for the same path."""
        meta = self.probe(path)
        existing = self.db.get_match_by_path(str(path))
        if existing:
            return existing
        return self.db.add_match(
            path=str(path), name=meta.name, file_size=meta.file_size,
            duration=meta.duration, width=meta.width, height=meta.height,
            fps=meta.fps, video_codec=meta.video_codec,
            audio_codec=meta.audio_codec, status="imported", file_hash="",
        )

    def matches(self, limit: int = 100) -> list[Match]:
        return self.db.list_matches(limit)

    def get_match(self, match_id: int) -> Match | None:
        return self.db.get_match(match_id)

    def create_job(self, match_id: int) -> AnalysisJob:
        return self.db.create_job(match_id)

    def events(self, match_id: int) -> list[Event]:
        return self.db.list_events(match_id)

    def highlights(self, match_id: int | None = None) -> list[Highlight]:
        return self.db.list_highlights(match_id)

    def delete_match(self, match_id: int) -> None:
        self.db.delete_match(match_id)

    def stats(self) -> dict[str, int]:
        return self.db.stats()
