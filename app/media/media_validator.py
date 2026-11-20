"""Validate imported recordings and report actionable problems."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.exceptions import InvalidVideoError, UnsupportedCodecError
from .probe import MediaMetadata, MediaProbe

SUPPORTED_VIDEO_CODECS = {"h264", "hevc", "av1", "mpeg4", "vp9", "avc1"}
SUPPORTED_CONTAINERS = {".mp4", ".mkv", ".mov", ".m4v"}


@dataclass
class ValidationResult:
    valid: bool
    metadata: MediaMetadata | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class MediaValidator:
    def __init__(self, probe: MediaProbe | None = None) -> None:
        self.probe = probe or MediaProbe()

    def validate(self, path: str) -> ValidationResult:
        from pathlib import Path
        p = Path(path)
        errors: list[str] = []
        warnings: list[str] = []

        if not p.exists():
            return ValidationResult(False, None, [], [f"File not found: {path}"])
        if p.suffix.lower() not in SUPPORTED_CONTAINERS:
            errors.append(f"Unsupported container '{p.suffix}'. Use an MP4 recording.")
        if p.stat().st_size < 64_000:
            errors.append("File is too small to be a complete recording.")

        try:
            meta = self.probe.probe(p)
        except (InvalidVideoError, Exception) as exc:  # noqa: BLE001
            errors.append(str(exc))
            return ValidationResult(False, None, warnings, errors)

        if meta.duration <= 0:
            errors.append("Could not determine video duration.")
        if meta.width <= 0 or meta.height <= 0:
            errors.append("Could not determine video resolution.")
        if meta.fps <= 0:
            warnings.append("Frame rate could not be determined; assuming 30 FPS.")
        if meta.video_codec and meta.video_codec.lower() not in SUPPORTED_VIDEO_CODECS:
            warnings.append(
                f"Video codec '{meta.video_codec}' is uncommon; export may need transcoding."
            )
        if not meta.has_audio:
            warnings.append(
                "No audio stream detected. Audio-based detection will be skipped."
            )
        if meta.width and meta.height:
            if meta.width < 640 or meta.height < 360:
                warnings.append("Very low resolution; OCR accuracy may be reduced.")

        return ValidationResult(len(errors) == 0, meta, warnings, errors)
