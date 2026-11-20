"""Run FFmpeg commands safely with captured output and meaningful errors."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ..core.exceptions import ExportError, MissingFfmpegError
from ..core.task_queue import CancellationToken
from ..media.probe import ffmpeg_path
from ..utils.logging import get_logger
from ..utils.paths import bundled_bin_dir

log = get_logger("rendering.ffmpeg")


@dataclass
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


def run(cmd: list[str], token: CancellationToken | None = None,
        timeout: float | None = None) -> CommandResult:
    """Execute a command as an argument list (never through a shell)."""
    log.debug("Running: %s", " ".join(f'"{a}"' if " " in a else a for a in cmd))
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        raise MissingFfmpegError(f"Executable not found: {cmd[0]}") from exc
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise ExportError("FFmpeg timed out while processing the video.")
    except Exception:
        proc.kill()
        raise
    if token and token.is_cancelled():
        proc.kill()
    return CommandResult(proc.returncode == 0, out or "", err or "", proc.returncode)


def encoder_names(ffmpeg: str | None = None) -> set[str]:
    """Return the set of available encoder names in this FFmpeg build."""
    exe = ffmpeg or ffmpeg_path() or str(bundled_bin_dir() / "ffmpeg.exe")
    try:
        res = run([exe, "-hide_banner", "-encoders"], timeout=20)
        names: set[str] = set()
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) >= 6 and parts[0][0] in "VAS":
                names.add(parts[1])
        return names
    except Exception:
        return set()


def detect_amf_support(ffmpeg: str | None = None) -> bool:
    """Check whether this FFmpeg build exposes an AMD AMF H.264 encoder."""
    return "h264_amf" in encoder_names(ffmpeg)


def choose_cpu_encoder(ffmpeg: str | None = None) -> str:
    """Pick a reliable H.264 CPU encoder available in this build."""
    names = encoder_names(ffmpeg)
    if "libx264" in names:
        return "libx264"
    if "libopenh264" in names:
        return "libopenh264"
    return "mpeg4"  # last-resort fallback (not H.264, but keeps export working)
