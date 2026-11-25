"""MediaProbe: extract metadata with FFprobe, with an OpenCV fallback."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.exceptions import InvalidVideoError, MissingFfmpegError
from ..utils.logging import get_logger
from ..utils.paths import bundled_bin_dir

log = get_logger("media.probe")


@dataclass
class MediaMetadata:
    path: str
    name: str
    file_size: int
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    nb_frames: int
    bitrate: int
    has_audio: bool

    def as_dict(self) -> dict:
        return {
            "path": self.path, "name": self.name, "file_size": self.file_size,
            "duration": self.duration, "width": self.width, "height": self.height,
            "fps": self.fps, "video_codec": self.video_codec,
            "audio_codec": self.audio_codec, "nb_frames": self.nb_frames,
            "bitrate": self.bitrate, "has_audio": self.has_audio,
        }


def find_binary(name: str, override: str = "") -> str | None:
    """Locate ffmpeg/ffprobe: explicit override, PATH, then bundled bin/."""
    candidates = []
    if override:
        candidates.append(override)
    candidates.append(shutil.which(name))
    candidates.append(str(bundled_bin_dir() / (name + ".exe")))
    candidates.append(str(bundled_bin_dir() / name))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def ffprobe_path(override: str = "") -> str | None:
    return find_binary("ffprobe", override)


def ffmpeg_path(override: str = "") -> str | None:
    return find_binary("ffmpeg", override)


def require_ffprobe(override: str = "") -> str:
    path = ffprobe_path(override)
    if not path:
        raise MissingFfmpegError()
    return path


class MediaProbe:
    def __init__(self, ffprobe_override: str = "") -> None:
        self.ffprobe_override = ffprobe_override

    def probe(self, path: str | Path) -> MediaMetadata:
        path = Path(path)
        if not path.is_file():
            raise InvalidVideoError(f"File not found: {path}")
        ffprobe = ffprobe_path(self.ffprobe_override)
        if ffprobe:
            try:
                return self._probe_ffprobe(ffprobe, path)
            except Exception as exc:  # noqa: BLE001
                log.warning("FFprobe failed for %s: %s — falling back to OpenCV",
                            path, exc)
        return self._probe_opencv(path)

    @staticmethod
    def _probe_ffprobe(ffprobe: str, path: Path) -> MediaMetadata:
        cmd = [
            ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ]
        # Windows: suppress the console window and give the child its own
        # process group so probing never flashes a window or inherits the
        # console control signals (same flags used by the FFmpeg runners).
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL, creationflags=flags)
        if proc.returncode != 0:
            raise InvalidVideoError(
                f"FFprobe could not read the file: {proc.stderr.strip()[:300]}"
            )
        data = json.loads(proc.stdout)
        video = next((s for s in data.get("streams", [])
                      if s.get("codec_type") == "video"), None)
        if video is None:
            raise InvalidVideoError("No video stream found in the file.")
        audio = next((s for s in data.get("streams", [])
                      if s.get("codec_type") == "audio"), None)

        def to_float(v, default=0.0):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        duration = to_float(data.get("format", {}).get("duration")) or to_float(
            video.get("duration"))
        fps_raw = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
        try:
            num, den = fps_raw.split("/")
            fps = float(num) / float(den) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        audio_codec = (audio.get("codec_name", "") if audio else "")
        return MediaMetadata(
            path=str(path), name=path.name, file_size=path.stat().st_size,
            duration=duration, width=width, height=height, fps=fps,
            video_codec=video.get("codec_name", ""), audio_codec=audio_codec,
            nb_frames=int(to_float(video.get("nb_frames"))),
            bitrate=int(to_float(data.get("format", {}).get("bit_rate"))),
            has_audio=audio is not None,
        )

    @staticmethod
    def _probe_opencv(path: Path) -> MediaMetadata:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise InvalidVideoError("OpenCV could not open this video file.")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        duration = frames / fps if fps else 0.0
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip()
        cap.release()
        return MediaMetadata(
            path=str(path), name=path.name, file_size=path.stat().st_size,
            duration=duration, width=width, height=height, fps=fps,
            video_codec=codec, audio_codec="", nb_frames=int(frames),
            bitrate=0, has_audio=False,
        )
