"""Build and run per-clip vertical render commands, validate outputs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import AppSettings
from ..core.exceptions import ExportError, InsufficientStorageError
from ..core.task_queue import CancellationToken
from ..media.probe import MediaProbe, ffmpeg_path
from ..utils.logging import get_logger
from .audio_mixer import audio_args
from .ffmpeg_runner import choose_cpu_encoder, detect_amf_support, run
from .vertical_layout import build_video_filter, video_encoder

log = get_logger("rendering.export")


@dataclass
class ExportRequest:
    video_path: str
    start: float
    end: float
    output_path: str
    layout: str | None = None
    source_has_audio: bool = True
    # Short fade-in/out prevents audible clicks at concatenation boundaries.
    audio_fade_sec: float = 0.0


def audio_fade_filter(duration: float, fade: float) -> str:
    """Build an FFmpeg afade chain for a segment of the given duration."""
    fade = max(0.0, min(fade, max(0.0, duration) / 3.0))
    if fade <= 0:
        return "anull"
    out_start = max(0.0, duration - fade)
    return (f"afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:st={out_start:.3f}:d={fade:.3f}")


def free_space_gb(path: str) -> float:
    try:
        drive = os.path.splitdrive(os.path.abspath(path))[0] or os.path.abspath(path)
        return shutil_disk_usage(drive)
    except Exception:
        return 999.0


def shutil_disk_usage(path: str) -> float:
    import shutil
    usage = shutil.disk_usage(path)
    return usage.free / 1e9


class ExportManager:
    def __init__(self, settings: AppSettings, ffmpeg_override: str = "") -> None:
        self.settings = settings
        self.ffmpeg = ffmpeg_path(ffmpeg_override)

    def build_command(self, req: ExportRequest) -> list[str]:
        if not self.ffmpeg:
            raise ExportError("FFmpeg was not found. Configure it in Settings.")
        r = self.settings.render
        layout = req.layout or r.layout
        settings = r.model_copy(update={"layout": layout})
        duration = max(0.5, req.end - req.start)
        vf = build_video_filter(settings)
        cmd = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{req.start:.3f}", "-i", req.video_path,
            "-t", f"{duration:.3f}",
        ]
        fade = audio_fade_filter(duration, req.audio_fade_sec)
        if settings.layout == "blurred":
            filter_complex = vf
            if req.source_has_audio and fade != "anull":
                filter_complex += f";[0:a:0]{fade}[aout]"
            cmd += ["-filter_complex", filter_complex, "-map", "[outv]"]
        else:
            cmd += ["-vf", vf]
            if req.source_has_audio and fade != "anull":
                cmd += ["-af", fade]
        if req.source_has_audio:
            cmd += ["-map", "[aout]" if (settings.layout == "blurred"
                                         and fade != "anull") else "0:a:0?"]
            cmd += audio_args(settings, True)
        else:
            cmd += ["-an"]

        if settings.hardware_encoding and detect_amf_support(self.ffmpeg):
            encoder = "h264_amf"
        else:
            encoder = choose_cpu_encoder(self.ffmpeg)
        if encoder == "h264_amf":
            cmd += ["-c:v", encoder, "-quality", "balanced",
                    "-rc", "vbr", "-b:v", "8M"]
        elif encoder == "libopenh264":
            # OpenH264 (LGPL) has no CRF/preset controls.
            cmd += ["-c:v", encoder, "-b:v", "8M"]
        elif encoder == "libx264":
            cmd += ["-c:v", encoder, "-preset", settings.preset,
                    "-crf", str(settings.crf)]
        else:
            cmd += ["-c:v", encoder, "-q:v", "3"]
        cmd += [
            "-r", str(settings.fps),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-f", "mp4",
            req.output_path,
        ]
        return cmd

    def render(self, req: ExportRequest, token: CancellationToken | None = None) -> str:
        if free_space_gb(req.output_path) < 0.5:
            raise InsufficientStorageError()
        out = Path(req.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command(req)
        log.info("Rendering clip -> %s", out.name)
        result = run(cmd, token=token)
        if not result.ok:
            if token and token.is_cancelled():
                from ..core.exceptions import CancelledError
                raise CancelledError()
            detail = result.stderr.strip()[-1200:]
            if not detail:
                code = result.returncode
                hint = (" (process terminated by a Windows control event — "
                        "check that FFmpeg can run without a console)"
                        if code < 0 or code > 0x7FFFFFFF else "")
                detail = f"No stderr output from FFmpeg.{hint}"
            raise ExportError(f"FFmpeg failed (exit {result.returncode}, "
                              f"0x{result.returncode & 0xFFFFFFFF:08X}):\n{detail}")
        if not out.exists() or out.stat().st_size < 10_000:
            raise ExportError("FFmpeg produced an empty or missing output file.")
        return str(out)

    def validate(self, path: str) -> bool:
        """Validate exported video: dimensions, codec, duration, audio stream."""
        probe = MediaProbe()
        try:
            meta = probe.probe(path)
        except Exception:  # noqa: BLE001
            return False
        r = self.settings.render
        ok = (meta.width == r.width and meta.height == r.height
              and meta.duration > 0.5 and meta.video_codec.lower() in ("h264", "avc1"))
        if not ok:
            log.warning("Export validation failed for %s: %s", path, meta.as_dict())
        return ok
