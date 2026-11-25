"""Build ONE continuous highlight compilation from a single PUBG match.

Pure planning helpers (segment selection, merging, ordering) are separated
from the FFmpeg rendering engine so they can be tested without media.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import AppSettings, RenderSettings
from ..core.exceptions import CancelledError, ExportError
from ..core.task_queue import CancellationToken
from ..database.models import Event, Highlight
from ..media.probe import MediaProbe, ffmpeg_path
from ..rendering.export_manager import ExportManager, ExportRequest, free_space_gb
from ..rendering.ffmpeg_runner import run
from ..utils.logging import get_logger
from ..utils.paths import app_cache_dir

log = get_logger("clips.compilation")

# Event categories that are always worth including when detected.
PRIORITY_CATEGORIES = {
    "KILL", "KNOCK", "KNOCK_CANDIDATE", "MULTI_KILL", "CLUTCH_CANDIDATE",
}


@dataclass
class Segment:
    """A selected, time-bounded piece of the original match."""

    start: float
    end: float
    category: str
    score: float
    confidence: float
    evidence: dict = field(default_factory=dict)
    event_ids: list[int] = field(default_factory=list)
    highlight_ids: list[int] = field(default_factory=list)
    source_labels: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0


def segment_signature(seg: "Segment") -> str:
    """Stable identity for a segment so a user's discard survives re-analysis.

    Tool-made segments are regenerated from highlights/events on every reload;
    a stable signature lets us remember which ones the user removed without
    changing the detector or the database schema of those tables. Manual
    segments already carry a ``manual_id`` and are handled separately.
    """
    evidence = seg.evidence or {}
    if evidence.get("manual_id") is not None:
        return f"manual:{evidence['manual_id']}"
    if seg.highlight_ids:
        return f"h:{seg.highlight_ids[0]}"
    if seg.event_ids:
        return f"e:{seg.event_ids[0]}"
    # Fallback for combat/unknown windows with neither: time bucket.
    return f"t:{seg.start:.1f}:{seg.end:.1f}"


def _event_center(event: Event | None, highlight: Highlight) -> float:
    """Best available timestamp of the actual event."""
    if event and event.timestamp > 0:
        return event.timestamp
    return (highlight.start + highlight.end) / 2.0


def segment_for_event(center: float, cfg, video_duration: float) -> tuple[float, float]:
    """Compute pre/post boundaries with min/max enforcement.

    The elimination and the action immediately before it are never trimmed:
    when reducing to the maximum length, post-event footage is removed first.
    """
    duration = max(0.0, video_duration)
    start = max(0.0, center - cfg.pre_event_sec)
    end = min(duration, center + cfg.post_event_sec)

    if end - start < cfg.min_segment_sec:
        missing = cfg.min_segment_sec - (end - start)
        start = max(0.0, start - missing / 2)
        end = min(duration, end + missing / 2)
        if end - start < cfg.min_segment_sec:
            if start <= 0.0:
                end = min(duration, cfg.min_segment_sec)
            else:
                start = max(0.0, end - cfg.min_segment_sec)

    if end - start > cfg.max_segment_sec:
        end = start + cfg.max_segment_sec
        # Keep at least 2 s after the elimination when possible.
        if end < center + 2.0:
            end = min(duration, center + 2.0)
            start = max(0.0, end - cfg.max_segment_sec)

    return round(max(0.0, start), 3), round(min(duration, max(start + 1.0, end)), 3)


def _event_supports(category: str, confidence: float, score: float, cfg) -> bool:
    """Reject random loud sounds / uninteresting visual-only windows."""
    if category in PRIORITY_CATEGORIES:
        return True
    if category == "KILL":
        return confidence >= 0.6
    # COMBAT / UNKNOWN / audio-only / visual-only need strong support.
    return (confidence >= cfg.min_support_confidence
            and score >= cfg.min_support_score)


def merge_segments(segments: list[Segment], gap: float) -> list[Segment]:
    """Merge overlapping or near-adjacent segments into single encounters."""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: s.start)
    merged: list[Segment] = [ordered[0]]
    for seg in ordered[1:]:
        last = merged[-1]
        if seg.start <= last.end + gap:
            last.end = max(last.end, seg.end)
            if seg.score > last.score:
                last.category = seg.category
                last.score = seg.score
            last.confidence = max(last.confidence, seg.confidence)
            # Evidence and ids are unioned so nothing is lost.
            for key in ("event_ids", "highlight_ids", "source_labels"):
                target = getattr(last, key)
                for value in getattr(seg, key):
                    if value not in target:
                        target.append(value)
            last.evidence.setdefault("merged", []).append({
                "start": seg.start, "end": seg.end, "category": seg.category,
            })
        else:
            merged.append(seg)
    return merged


def remove_redundant(segments: list[Segment], tolerance: float = 1.0) -> list[Segment]:
    """Drop segments that duplicate an already-kept window."""
    kept: list[Segment] = []
    for seg in segments:
        if any(abs(seg.start - k.start) <= tolerance and
               abs(seg.end - k.end) <= tolerance for k in kept):
            continue
        kept.append(seg)
    return kept


def select_segments(highlights: list[Highlight], events: list[Event],
                    settings: AppSettings, video_duration: float) -> list[Segment]:
    """Select and plan compilation segments from analysis results.

    Confirmed eliminations and multi-kills are always prioritised. Weak
    audio/visual-only candidates are excluded. The result is chronological by
    default; ``order_by_score`` provides the optional alternative ordering.
    """
    cfg = settings.compilation
    events_by_id = {e.id: e for e in events}

    # Highlight-derived segments (respecting the user's keep/discard choice).
    # Coverage is measured from the segments we ACTUALLY keep — not from raw
    # highlight windows, which may be filtered out or discarded. Otherwise a
    # confirmed kill inside a weak highlight can be lost entirely.
    segments: list[Segment] = []
    for h in highlights:
        if not h.keep:
            continue  # explicit user removal
        ev = events_by_id.get(h.event_id) if h.event_id else None
        category = h.category
        confidence = ev.confidence if ev else (0.9 if category == "KILL" else 0.5)
        if not _event_supports(category, confidence, h.score, cfg):
            continue
        center = _event_center(ev, h)
        start, end = segment_for_event(center, cfg, video_duration)
        segments.append(Segment(
            start=start, end=end, category=category, score=h.score,
            confidence=confidence,
            evidence={"event_id": ev.id if ev else None,
                      "recognised_text": ev.recognised_text if ev else "",
                      "highlight_id": h.id},
            event_ids=[ev.id] if ev else [], highlight_ids=[h.id],
            source_labels=[h.category],
        ))

    # Ensure every high-confidence event (especially confirmed kills) is
    # represented even if the individual-clip ranking dropped it.
    covered = [(s.start, s.end) for s in segments]
    priority_events = sorted(
        [e for e in events if e.category in PRIORITY_CATEGORIES
         and _event_supports(e.category, e.confidence, e.score, cfg)],
        key=lambda e: (e.category != "KILL", e.timestamp),
    )
    for ev in priority_events:
        if any(s <= ev.timestamp <= e for s, e in covered):
            continue
        start, end = segment_for_event(ev.timestamp, cfg, video_duration)
        segments.append(Segment(
            start=start, end=end, category=ev.category, score=ev.score,
            confidence=ev.confidence,
            evidence={"event_id": ev.id, "recognised_text": ev.recognised_text,
                      "source": ev.source},
            event_ids=[ev.id], highlight_ids=[],
            source_labels=[ev.category],
        ))
        covered.append((start, end))

    # Fallback: a strong combat window with several audio spikes can be a
    # knock/engagement the feed OCR failed to read. Include a few of these so
    # knock moments are not lost purely because of poor OCR.
    combat_fallbacks = [
        e for e in events
        if e.category in ("COMBAT", "UNKNOWN")
        and e.score >= 18.0
        and not any(s.start <= e.timestamp <= s.end for s in segments)
    ]
    for ev in sorted(combat_fallbacks, key=lambda e: -e.score)[:3]:
        start, end = segment_for_event(ev.timestamp, cfg, video_duration)
        segments.append(Segment(
            start=start, end=end, category="COMBAT", score=ev.score,
            confidence=ev.confidence,
            evidence={"event_id": ev.id, "source": ev.source,
                      "note": "combat fallback — OCR did not identify this moment"},
            event_ids=[ev.id], source_labels=["COMBAT"],
        ))

    segments = remove_redundant(merge_segments(segments, cfg.merge_gap_sec))
    # When the configured maximum is smaller than the number of candidates,
    # confirmed kills must survive the cut before weaker moments.
    if len(segments) > cfg.max_segments:
        segments.sort(key=lambda s: (s.category not in PRIORITY_CATEGORIES,
                                     -s.score, s.start))
        segments = segments[:cfg.max_segments]
    if cfg.order_by_score:
        segments.sort(key=lambda s: (-s.score, s.start))
    else:
        segments.sort(key=lambda s: s.start)
    return segments


def total_duration(segments: list[Segment]) -> float:
    return round(sum(s.duration for s in segments), 3)


def category_counts(segments: list[Segment]) -> dict[str, int]:
    counts = {
        "confirmed_kills": 0,
        "multi_kills": 0,
        "clutch_candidates": 0,
        "knocks": 0,
        "other": 0,
    }
    for seg in segments:
        if seg.category == "KILL":
            counts["confirmed_kills"] += 1
        elif seg.category in ("KNOCK", "KNOCK_CANDIDATE"):
            counts["knocks"] += 1
        elif seg.category == "MULTI_KILL":
            counts["multi_kills"] += 1
        elif seg.category == "CLUTCH_CANDIDATE":
            counts["clutch_candidates"] += 1
        else:
            counts["other"] += 1
    return counts


def kill_coverage(segments: list[Segment], events: list[Event]) -> tuple[int, int]:
    """Return (confirmed kills included in segments, total confirmed kills)."""
    kills = [e for e in events if e.category == "KILL" and e.confidence >= 0.6]
    included_ids = {eid for s in segments for eid in s.event_ids}
    covered = 0
    for ev in kills:
        if ev.id in included_ids or any(s.start <= ev.timestamp <= s.end
                                        for s in segments):
            covered += 1
    return covered, len(kills)


def validate_segments(segments: list[Segment], video_duration: float) -> None:
    if not segments:
        raise ExportError("No highlights were selected for the compilation.")
    for i, seg in enumerate(segments):
        if seg.start < 0 or seg.end > video_duration + 0.5:
            raise ExportError(f"Segment {i + 1} has out-of-range timestamps.")
        if seg.end - seg.start < 0.5:
            raise ExportError(f"Segment {i + 1} is too short to render.")


class CompilationBuilder:
    """Render segments and concatenate them into one final MP4."""

    def __init__(self, settings: AppSettings, ffmpeg_override: str = "") -> None:
        self.settings = settings
        self.ffmpeg = ffmpeg_path(ffmpeg_override)
        self.manager = ExportManager(settings, ffmpeg_override)

    def build(self, source_path: str, segments: list[Segment], output_path: str,
              source_has_audio: bool = True, video_duration: float = 0.0,
              token: CancellationToken | None = None,
              progress=None, preview: bool = False) -> str:
        if not self.ffmpeg:
            raise ExportError("FFmpeg was not found. Configure it in Settings.")
        validate_segments(segments, video_duration or sum(s.end for s in segments) + 10)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if free_space_gb(str(out)) < 0.5:
            raise ExportError("Not enough free disk space for the compilation.")

        # Preview uses a tiny, fast profile but identical encoding parameters
        # across segments, so the concatenation workflow is exercised too.
        render_settings = self.settings.render
        manager = self.manager
        if preview:
            preview_render = render_settings.model_copy(update={
                "width": 360, "height": 640, "crf": 28,
                "preset": "ultrafast", "hardware_encoding": False,
            })
            preview_settings = self.settings.model_copy(update={"render": preview_render})
            manager = ExportManager(preview_settings)
            render_settings = preview_render

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        tmp_dir = app_cache_dir() / "compilations" / stamp
        tmp_dir.mkdir(parents=True, exist_ok=True)
        log.info("Building compilation of %d segments -> %s (%s)",
                 len(segments), out.name, "preview" if preview else "final")

        try:
            segment_files: list[Path] = []
            for i, seg in enumerate(segments, 1):
                if token:
                    token.check()
                if progress:
                    progress(i, len(segments) + 1,
                             f"Rendering segment {i}/{len(segments)}")
                seg_path = tmp_dir / f"segment_{i:04d}.mp4"
                manager.render(ExportRequest(
                    video_path=source_path, start=seg.start, end=seg.end,
                    output_path=str(seg_path),
                    layout=render_settings.layout,
                    source_has_audio=source_has_audio,
                    audio_fade_sec=self.settings.compilation.audio_fade_sec,
                ), token=token)
                segment_files.append(seg_path)

            if token:
                token.check()
            if progress:
                progress(len(segments) + 1, len(segments) + 1,
                         "Concatenating segments")
            self._concat(segment_files, out, source_has_audio, token)

            if not self._verify(out, source_has_audio, render_settings,
                                total_duration(segments)):
                raise ExportError("Final compilation failed integrity verification.")

            # Only remove temporary segments after successful verification.
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.info("Compilation complete: %s (%d segments)", out.name, len(segments))
            return str(out)
        except Exception:
            # Keep temporary segments for diagnostics on failure.
            log.exception("Compilation failed; temporary files kept at %s", tmp_dir)
            raise

    def _concat(self, files: list[Path], out: Path, has_audio: bool,
                token: CancellationToken | None) -> None:
        """Try stream-copy concat, then fall back to normalised re-encode."""
        list_file = files[0].parent / "concat.txt"
        lines = []
        for f in files:
            safe = str(f).replace("\\", "/").replace("'", "'\\''")
            lines.append(f"file '{safe}'")
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        copy_cmd = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", "-f", "mp4", str(out),
        ]
        result = run(copy_cmd, token=token)
        if result.ok and out.exists() and out.stat().st_size > 10_000:
            log.info("Stream-copy concatenation succeeded")
            return

        log.warning("Stream-copy concat failed (%s); re-encoding fallback",
                    result.stderr.strip()[-300:])
        if out.exists():
            out.unlink()
        cmd = [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        for f in files:
            cmd += ["-i", str(f)]
        # Build concat filter labels for video (and audio when present).
        v_in = "".join(f"[{i}:v]" for i in range(len(files)))
        if has_audio:
            a_in = "".join(f"[{i}:a]" for i in range(len(files)))
            graph = f"{v_in}{a_in}concat=n={len(files)}:v=1:a=1[v][a]"
        else:
            graph = f"{v_in}concat=n={len(files)}:v=1:a=0[v]"
        cmd += ["-filter_complex", graph, "-map", "[v]"]
        if has_audio:
            cmd += ["-map", "[a]", "-c:a", "aac",
                    "-b:a", f"{self.settings.render.audio_bitrate_kbps}k"]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-r", str(self.settings.render.fps), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-f", "mp4", str(out),
        ]
        result = run(cmd, token=token)
        if not result.ok:
            detail = result.stderr.strip()[-800:] or "unknown error"
            raise ExportError(f"Compilation concatenation failed: {detail}")

    def _verify(self, path: Path, has_audio: bool, render_settings: RenderSettings,
                expected_duration: float) -> bool:
        if not path.exists() or path.stat().st_size < 10_000:
            return False
        try:
            meta = MediaProbe().probe(str(path))
        except Exception:  # noqa: BLE001
            return False
        if meta.width != render_settings.width or meta.height != render_settings.height:
            log.error("Compilation resolution mismatch: %sx%s", meta.width, meta.height)
            return False
        if meta.video_codec.lower() not in ("h264", "avc1"):
            return False
        if has_audio and not meta.has_audio:
            return False
        if expected_duration > 0 and abs(meta.duration - expected_duration) > max(2.0, expected_duration * 0.08):
            log.error("Compilation duration mismatch: %.1f vs expected %.1f",
                      meta.duration, expected_duration)
            return False
        # Full decode check — catches broken timestamps / truncated files.
        decode = run([self.ffmpeg, "-v", "error", "-i", str(path),
                      "-f", "null", "-"], timeout=300)
        return decode.ok
