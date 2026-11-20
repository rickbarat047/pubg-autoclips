"""Sample frames and produce visual-activity and scene-change signals."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2

from ...config import AppSettings
from ...core.task_queue import CancellationToken
from ...media.frame_extractor import FrameSample
from ...media.video_reader import VideoReader
from ...utils.logging import get_logger
from .motion_detector import motion_intensity, prepare
from .scene_detector import is_scene_change

log = get_logger("detection.vision")


@dataclass
class ActivitySample:
    timestamp: float
    motion: float
    scene_change: bool


@dataclass
class ActivityWindow:
    start: float
    end: float
    mean_motion: float
    peak_motion: float
    scene_changes: int


ProgressCb = Callable[[float, str], None]


class ActivityDetector:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def analyze(self, video_path: str, token: CancellationToken | None = None,
                progress: ProgressCb | None = None) -> list[ActivitySample]:
        cfg = self.settings.visual
        if not cfg.enabled:
            return []
        samples: list[ActivitySample] = []
        prev = None
        with VideoReader(video_path) as reader:
            total = max(1, int((reader.duration or 1) / cfg.sample_interval_sec))
            for idx, (t, frame) in enumerate(
                reader.sample(cfg.sample_interval_sec, token=token)
            ):
                if token:
                    token.check()
                motion = motion_intensity(prev, frame)
                scene = is_scene_change(prev, frame, cfg.scene_change_threshold)
                samples.append(ActivitySample(t, motion, scene))
                prev = prepare(frame)
                if progress:
                    progress(min(1.0, idx / total), f"Visual {t:.0f}s")
        if progress:
            progress(1.0, "Visual analysis complete")
        log.info("Visual analysis produced %d samples", len(samples))
        return samples

    def analyze_frame_files(self, frames: list[FrameSample],
                            token: CancellationToken | None = None,
                            progress: ProgressCb | None = None) -> list[ActivitySample]:
        """Analyse pre-extracted frames (no extra video decode)."""
        cfg = self.settings.visual
        if not cfg.enabled:
            return []
        samples: list[ActivitySample] = []
        prev = None
        total = max(1, len(frames))
        for idx, fs in enumerate(frames):
            if token:
                token.check()
            frame = cv2.imread(fs.path)
            if frame is None:
                continue
            motion = motion_intensity(prev, frame)
            scene = is_scene_change(prev, frame, cfg.scene_change_threshold)
            samples.append(ActivitySample(fs.timestamp, motion, scene))
            prev = prepare(frame)
            if progress and idx % 8 == 0:
                progress(idx / total, f"Visual {fs.timestamp:.0f}s")
        if progress:
            progress(1.0, "Visual analysis complete")
        log.info("Visual analysis produced %d samples from extracted frames", len(samples))
        return samples

    @staticmethod
    def to_windows(samples: list[ActivitySample], interval: float,
                   threshold: float = 0.45, merge_gap: float = 3.0) -> list[ActivityWindow]:
        group: list[ActivitySample] = []
        out: list[ActivityWindow] = []

        def flush(g: list[ActivitySample]) -> None:
            if not g:
                return
            out.append(ActivityWindow(
                start=g[0].timestamp,
                end=g[-1].timestamp + interval,
                mean_motion=sum(s.motion for s in g) / len(g),
                peak_motion=max(s.motion for s in g),
                scene_changes=sum(1 for s in g if s.scene_change),
            ))

        for s in samples:
            if s.motion >= threshold or s.scene_change:
                if group and s.timestamp - group[-1].timestamp > interval + merge_gap:
                    flush(group)
                    group = []
                group.append(s)
            elif group and s.timestamp - group[-1].timestamp > interval + merge_gap:
                flush(group)
                group = []
        flush(group)
        return out
