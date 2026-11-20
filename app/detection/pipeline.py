"""AnalysisPipeline: orchestrate all detection engines and persist results."""
from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import cv2

from ..clips.clip_selector import ClipCandidate, ClipSelector
from ..config import AppSettings
from ..core.task_queue import CancellationToken
from ..database.db import DatabaseManager
from ..media.frame_extractor import cleanup_frames, extract_frames
from ..media.probe import ffmpeg_path
from ..utils.logging import get_logger
from .audio.audio_analyzer import AudioAnalyzer
from .audio.combat_detector import CombatWindow, group_combat_windows
from .kill_feed.feed_detector import FeedEvent, KillFeedDetector
from .kill_feed.ocr_engine import OcrEngine
from .scoring.clutch_detector import group_multi_kills
from .scoring.event_ranker import rank_events
from .scoring.event_scorer import EventScorer, ScoredEvent
from .vision.activity_detector import ActivityDetector, ActivityWindow

log = get_logger("detection.pipeline")

OverallCb = Callable[[float, str, str], None]  # (fraction, stage, message)


@dataclass
class AnalysisResult:
    events: list[ScoredEvent] = field(default_factory=list)
    clips: list[ClipCandidate] = field(default_factory=list)
    feed_events: list[FeedEvent] = field(default_factory=list)
    combat_windows: list[CombatWindow] = field(default_factory=list)
    activity_windows: list[ActivityWindow] = field(default_factory=list)
    multi_kill_groups: int = 0
    highlight_ids: list[int] = field(default_factory=list)
    elapsed_sec: float = 0.0


class AnalysisPipeline:
    def __init__(self, settings: AppSettings, db: DatabaseManager,
                 ocr: OcrEngine | None = None) -> None:
        self.settings = settings
        self.db = db
        self.ocr = ocr or OcrEngine()
        self.feed = KillFeedDetector(settings, self.ocr)
        self.audio = AudioAnalyzer(settings)
        self.visual = ActivityDetector(settings)
        self.scorer = EventScorer(settings)
        self.selector = ClipSelector(settings)

    def run(self, video_path: str, match_id: int, job_id: int,
            duration: float, token: CancellationToken | None = None,
            overall_cb: OverallCb | None = None) -> AnalysisResult:
        import time
        started = time.time()
        result = AnalysisResult()
        w = [0.10, 0.15, 0.50, 0.05, 0.20]  # extract, audio, ocr+visual, scoring, clips
        offset = [0.0, w[0], w[0] + w[1], sum(w[:3]), sum(w[:4])]

        def stage_progress(i: int, fraction: float, message: str = "") -> None:
            if overall_cb:
                overall_cb(offset[i] + w[i] * max(0.0, min(1.0, fraction)),
                           STAGES[i], message)

        def check() -> None:
            if token:
                token.check()

        # Adaptive interval: cap total samples so long recordings stay fast.
        configured = self.settings.kill_feed.sample_interval_sec
        if not self.settings.visual.enabled:
            interval = configured
        else:
            interval = max(configured, self.settings.visual.sample_interval_sec)
        interval = max(interval, duration / 900.0)
        interval = round(interval, 3)
        log.info("Analysis sample interval: %.2fs for %.0fs video", interval, duration)

        # Stage 0 + audio run concurrently.
        check()
        audio_future = None
        with ThreadPoolExecutor(max_workers=1) as pool:
            if self.settings.audio.enabled and ffmpeg_path(self.settings.ffmpeg_path):
                audio_future = pool.submit(
                    self.audio.analyze, video_path, duration, token,
                    lambda f, m: None)
            audio_windows: list = []
            samples: list = []
            frames: list[tuple[float, object]] = []
            frame_samples = []
            if ffmpeg_path():
                try:
                    frame_samples = extract_frames(
                        video_path, interval, token=token,
                        ffmpeg_override=self.settings.ffmpeg_path)
                    stage_progress(0, 1.0, f"{len(frame_samples)} frames extracted")
                    # Load frames into memory (one at a time, bounded by count).
                    for fs in frame_samples:
                        check()
                        img = cv2.imread(fs.path)
                        if img is not None:
                            frames.append((fs.timestamp, img))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Fast extraction failed (%s); using seek fallback", exc)
                    frame_samples = []
            if frame_samples:
                check()
                samples = self.visual.analyze_frame_files(
                    frame_samples, token=token,
                    progress=lambda f, m: stage_progress(2, f * 0.2, m))
                result.feed_events = self.feed.detect_from_frames(
                    frames, token=token,
                    progress=lambda f, m: stage_progress(2, 0.2 + f * 0.8, m))
            else:
                # Fallback: original OpenCV seeking path.
                stage_progress(0, 1.0, "Using seek-based analysis")
                result.feed_events = self.feed.detect(
                    video_path, token=token,
                    progress=lambda f, m: stage_progress(2, 0.2 + f * 0.8, m))
                if self.settings.visual.enabled:
                    from .vision.activity_detector import ActivitySample
                    raw = self.visual.analyze(
                        video_path, token=token,
                        progress=lambda f, m: stage_progress(2, f * 0.2, m))
                    samples = raw
            if audio_future:
                try:
                    audio_windows = audio_future.result(timeout=600)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Audio analysis failed: %s", exc)
            stage_progress(1, 1.0, "Audio analysis complete")

        result.combat_windows = group_combat_windows(audio_windows)
        result.activity_windows = ActivityDetector.to_windows(samples, interval)

        # Stage 3: scoring
        check()
        scored: list[ScoredEvent] = [
            self.scorer.score_feed_event(e, audio_windows,
                                         result.combat_windows, samples)
            for e in result.feed_events
        ]
        for cw in result.combat_windows:
            if cw.peak_intensity >= 0.55 and len(scored) < 40:
                scored.append(self.scorer.score_audio_only(cw))
        scored, groups = group_multi_kills(scored)
        result.multi_kill_groups = groups
        min_score = self.settings.scoring.min_event_score * 0.5
        result.events = rank_events(scored, min_score=min_score, max_events=60)
        self._persist_events(match_id, job_id, result.events)
        stage_progress(3, 1.0)

        # Stage 4: clip selection
        check()
        result.clips = self.selector.select(result.events, duration)
        result.highlight_ids = self._persist_highlights(match_id, result.clips)
        stage_progress(4, 1.0)
        if frame_samples:
            cleanup_frames(frame_samples)
        result.elapsed_sec = round(time.time() - started, 1)
        if overall_cb:
            overall_cb(1.0, "done", f"Analysis complete in {result.elapsed_sec:.0f}s")
        log.info("Pipeline finished in %.1fs: %d events, %d clips",
                 result.elapsed_sec, len(result.events), len(result.clips))
        return result

    def _persist_events(self, match_id: int, job_id: int,
                        events: list[ScoredEvent]) -> None:
        import json
        self.db.delete_events_for_job(job_id)
        for e in events:
            self.db.add_event(
                match_id=match_id, job_id=job_id, timestamp=e.timestamp,
                category=e.category, confidence=e.confidence, score=e.score,
                source=e.source, recognised_text=e.recognised_text,
                ocr_confidence=e.ocr_confidence,
                evidence_json=json.dumps(e.evidence, ensure_ascii=False),
                manual=0, confirmed=int(e.category == "KILL" and e.confidence >= 0.6),
            )

    def _persist_highlights(self, match_id: int, clips: list[ClipCandidate]) -> list[int]:
        self.db.delete_highlights_for_match(match_id)
        ids: list[int] = []
        for c in clips:
            h = self.db.add_highlight(
                match_id=match_id, event_id=None, start=c.start, end=c.end,
                duration=round(c.end - c.start, 3), score=c.score,
                category=c.category, keep=1, thumbnail="",
            )
            ids.append(h.id)
        return ids


STAGES = ["Frames", "Audio", "OCR + Visual", "Scoring", "Clips"]
