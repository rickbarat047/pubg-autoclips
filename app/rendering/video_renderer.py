"""VideoRenderer: single-clip rendering facade over ExportManager."""
from __future__ import annotations

from ..config import AppSettings
from ..core.task_queue import CancellationToken
from .export_manager import ExportManager, ExportRequest


class VideoRenderer:
    """Thin interface that can later be swapped for another renderer."""

    def __init__(self, settings: AppSettings, ffmpeg_override: str = "") -> None:
        self.manager = ExportManager(settings, ffmpeg_override)

    def render(self, request: ExportRequest,
               token: CancellationToken | None = None) -> str:
        return self.manager.render(request, token=token)

    def build_command(self, request: ExportRequest) -> list[str]:
        return self.manager.build_command(request)

    def validate(self, path: str) -> bool:
        return self.manager.validate(path)
