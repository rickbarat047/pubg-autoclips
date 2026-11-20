"""Audio arguments that preserve the original gameplay audio."""
from __future__ import annotations

from ..config import RenderSettings


def audio_args(settings: RenderSettings, has_audio: bool = True) -> list[str]:
    """Return FFmpeg flags for copying/re-encoding original audio."""
    if not has_audio:
        return ["-an"]
    return [
        "-c:a", "aac",
        "-b:a", f"{settings.audio_bitrate_kbps}k",
        "-ar", "48000",
    ]
