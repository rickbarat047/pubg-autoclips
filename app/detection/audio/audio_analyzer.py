"""Streaming local audio analysis using FFmpeg PCM output."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.stats import zscore

from ...config import AppSettings
from ...core.task_queue import CancellationToken
from ...media.probe import ffmpeg_path
from ...utils.logging import get_logger
from .energy_detector import detect_spikes, rms, spectral_flatness

log = get_logger("detection.audio")

SAMPLE_RATE = 16000
CHUNK_SEC = 1.0


@dataclass
class AudioWindow:
    timestamp: float
    duration: float
    energy: float
    z_energy: float
    flatness: float
    is_spike: bool
    intensity: float  # 0..1 combined combat-likeness


ProgressCb = Callable[[float, str], None]


class AudioAnalyzer:
    """Decode audio in small PCM chunks; never load the whole track into RAM."""

    def __init__(self, settings: AppSettings, ffmpeg_override: str = "") -> None:
        self.settings = settings
        self.ffmpeg = ffmpeg_path(ffmpeg_override)
        self.rate = SAMPLE_RATE

    def analyze(self, video_path: str, duration: float,
                token: CancellationToken | None = None,
                progress: ProgressCb | None = None) -> list[AudioWindow]:
        cfg = self.settings.audio
        if not cfg.enabled or not self.ffmpeg:
            log.info("Audio analysis skipped (disabled or ffmpeg missing)")
            return []
        cmd = [
            self.ffmpeg, "-v", "error", "-i", video_path,
            "-vn", "-ac", "1", "-ar", str(self.rate),
            "-f", "s16le", "-acodec", "pcm_s16le", "-",
        ]
        bytes_per_chunk = int(self.rate * CHUNK_SEC) * 2
        energies: list[float] = []
        flats: list[float] = []
        timestamps: list[float] = []
        buf = bytearray()
        idx = 0
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, bufsize=bytes_per_chunk * 4)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not start ffmpeg for audio: %s", exc)
            return []

        try:
            assert proc.stdout is not None
            while True:
                if token:
                    token.check()
                piece = proc.stdout.read(bytes_per_chunk)
                if not piece:
                    break
                buf.extend(piece)
                while len(buf) >= bytes_per_chunk:
                    raw = bytes(buf[:bytes_per_chunk])
                    del buf[:bytes_per_chunk]
                    samples = np.frombuffer(raw, dtype="<i2")
                    t = idx * CHUNK_SEC
                    energies.append(rms(samples))
                    flats.append(spectral_flatness(samples, self.rate))
                    timestamps.append(t)
                    idx += 1
                    if progress and duration > 0:
                        progress(min(1.0, t / duration), f"Audio {t:.0f}s")
            proc.stdout.close()
            proc.wait(timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("Audio decoding interrupted: %s", exc)
            proc.kill()
        finally:
            if buf:
                samples = np.frombuffer(bytes(buf), dtype="<i2")
                if samples.size:
                    energies.append(rms(samples))
                    flats.append(spectral_flatness(samples, self.rate))
                    timestamps.append(idx * CHUNK_SEC)

        if not energies:
            return []
        e = np.asarray(energies, dtype=np.float64)
        z = zscore(e) if e.size > 1 else np.zeros_like(e)
        z = np.nan_to_num(z)
        spikes = detect_spikes(e, sensitivity=cfg.sensitivity)
        flat = np.asarray(flats, dtype=np.float64)
        # Intensity: normalised energy blended with noise-like spectral texture.
        e_norm = np.clip(e / (np.percentile(e, 95) + 1e-9), 0, 1)
        f_norm = np.clip(flat / 0.6, 0, 1)
        intensity = np.clip(0.7 * e_norm + 0.3 * f_norm, 0, 1)

        windows = [
            AudioWindow(
                timestamp=float(timestamps[i]), duration=CHUNK_SEC,
                energy=float(e[i]), z_energy=float(z[i]),
                flatness=float(flat[i]), is_spike=bool(spikes[i]),
                intensity=float(intensity[i]),
            )
            for i in range(len(energies))
        ]
        if progress:
            progress(1.0, "Audio analysis complete")
        log.info("Audio analysis produced %d windows (%d spikes)",
                 len(windows), int(spikes.sum()))
        return windows
