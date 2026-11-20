"""Fast one-pass frame extraction via FFmpeg.

Instead of seeking with OpenCV for every sample (slow on long H.264 files),
this asks FFmpeg to decode the video once and write only the sampled frames as
JPEGs. For a 16-minute 1080p file this takes ~11 s instead of minutes.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.task_queue import CancellationToken
from ..utils.logging import get_logger
from .probe import ffmpeg_path

log = get_logger("media.frame_extractor")


@dataclass
class FrameSample:
    timestamp: float
    path: str


def extract_frames(video_path: str, interval_sec: float,
                   token: CancellationToken | None = None,
                   out_dir: Path | None = None,
                   ffmpeg_override: str = "") -> list[FrameSample]:
    """Decode the video once and extract one frame every ``interval_sec``."""
    exe = ffmpeg_path(ffmpeg_override)
    if not exe:
        raise RuntimeError("FFmpeg not available for frame extraction")
    out_dir = Path(out_dir) if out_dir else Path(__import__("tempfile").mkdtemp(prefix="pac_frames_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "f%06d.jpg")
    cmd = [
        exe, "-y", "-loglevel", "error", "-i", video_path,
        "-vf", f"fps=1/{max(0.1, interval_sec):g}",
        "-q:v", "5", "-frames:v", "5000", pattern,
    ]
    log.info("Extracting frames every %.1fs -> %s", interval_sec, out_dir)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        _, err = proc.communicate(timeout=3600)
    except Exception:
        proc.kill()
        proc.communicate()
        raise
    if proc.returncode != 0:
        raise RuntimeError(f"Frame extraction failed: {err.decode('utf-8', 'replace')[:400]}")

    samples: list[FrameSample] = []
    for i, p in enumerate(sorted(out_dir.glob("f*.jpg"))):
        if token:
            token.check()
        samples.append(FrameSample(timestamp=round(i * interval_sec, 3), path=str(p)))
    log.info("Extracted %d frames in one pass", len(samples))
    return samples


def cleanup_frames(samples: list[FrameSample]) -> None:
    if not samples:
        return
    directory = Path(samples[0].path).parent
    shutil.rmtree(directory, ignore_errors=True)
