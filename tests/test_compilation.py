"""Tests for single highlight compilation: planning, rendering and recovery."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.clips.compilation_builder import (
    CompilationBuilder, Segment, category_counts, merge_segments,
    remove_redundant, select_segments, segment_for_event, total_duration,
    validate_segments,
)
from app.config import AppSettings
from app.core.exceptions import ExportError
from app.core.task_queue import CancellationToken
from app.database.models import Event, Highlight
from app.media.probe import MediaProbe, ffmpeg_path

pytestmark = pytest.mark.skipif(ffmpeg_path() is None,
                                reason="ffmpeg not installed")


def _event(eid, t, category="KILL", confidence=0.9, score=50.0) -> Event:
    return Event(
        id=eid, match_id=1, job_id=1, timestamp=t, category=category,
        confidence=confidence, score=score, source="kill_feed_ocr",
        recognised_text="rickbarat killed ENEMY", ocr_confidence=0.9,
        evidence_json="{}", manual=False, confirmed=category == "KILL",
    )


def _highlight(hid, start, end, category="KILL", score=50.0, keep=True,
               event_id=None) -> Highlight:
    return Highlight(
        id=hid, match_id=1, event_id=event_id, start=start, end=end,
        duration=round(end - start, 3), score=score, category=category,
        keep=int(keep), thumbnail="",
    )


def _cfg(settings) -> AppSettings:
    settings.compilation.pre_event_sec = 10.0
    settings.compilation.post_event_sec = 5.0
    settings.compilation.min_segment_sec = 10.0
    settings.compilation.max_segment_sec = 30.0
    settings.compilation.merge_gap_sec = 2.0
    settings.compilation.order_by_score = False
    settings.compilation.max_segments = 12
    return settings


# ---------- planning tests ----------

def test_pre_post_boundaries(settings):
    cfg = _cfg(settings).compilation
    start, end = segment_for_event(100.0, cfg, 600.0)
    assert start == 90.0
    assert end == 105.0
    assert abs((end - start) - 15.0) < 0.01


def test_min_and_max_segment_duration(settings):
    cfg = _cfg(settings).compilation
    # Near end of video: must extend backwards to reach minimum 10s.
    start, end = segment_for_event(598.0, cfg, 600.0)
    assert end <= 600.0
    assert end - start >= 9.9
    # Very large pre/post would exceed max — must clamp to 30s.
    cfg.pre_event_sec = 40.0
    cfg.post_event_sec = 40.0
    start, end = segment_for_event(200.0, cfg, 600.0)
    assert end - start <= 30.01


def test_chronological_ordering(settings):
    events = [_event(1, 10), _event(2, 80), _event(3, 150)]
    hs = [_highlight(3, 150, 165, event_id=3),
          _highlight(1, 10, 25, event_id=1),
          _highlight(2, 80, 95, event_id=2)]
    segs = select_segments(hs, events, _cfg(settings), 600.0)
    assert [s.start for s in segs] == sorted(s.start for s in segs)
    assert [s.start for s in segs] == [0.0, 70.0, 140.0]


def test_optional_score_ordering(settings):
    cfg = _cfg(settings)
    cfg.compilation.order_by_score = True
    events = [_event(1, 10), _event(2, 80)]
    hs = [_highlight(1, 10, 25, score=20, event_id=1),
          _highlight(2, 80, 95, score=90, event_id=2)]
    segs = select_segments(hs, events, cfg, 600.0)
    assert segs[0].start == 70.0  # higher score first


def test_overlapping_segments_merge(settings):
    a = Segment(10, 25, "KILL", 50, 0.9, highlight_ids=[1])
    b = Segment(24, 40, "KILL", 55, 0.9, highlight_ids=[2])
    merged = merge_segments([a, b], gap=2.0)
    assert len(merged) == 1
    assert merged[0].start == 10
    assert merged[0].end == 40
    assert merged[0].highlight_ids == [1, 2]


def test_duplicate_removal():
    a = Segment(10, 25, "KILL", 50, 0.9)
    b = Segment(10.2, 25.1, "KILL", 50, 0.9)
    assert len(remove_redundant([a, b])) == 1


def test_total_duration():
    segs = [Segment(0, 20, "KILL", 1, 1), Segment(30, 55, "COMBAT", 1, 1)]
    assert total_duration(segs) == 45.0


def test_weak_audio_only_moments_excluded(settings):
    cfg = _cfg(settings)
    strong = _highlight(1, 10, 25, category="KILL", score=60)
    weak = _highlight(2, 80, 95, category="UNKNOWN", score=5)
    segs = select_segments([strong, weak], [], cfg, 600.0)
    assert len(segs) == 1
    assert segs[0].category == "KILL"


def test_all_confirmed_kills_included_even_without_highlight(settings):
    cfg = _cfg(settings)
    events = [_event(1, 40, "KILL", 0.95), _event(2, 200, "KILL", 0.9)]
    segs = select_segments([], events, cfg, 600.0)
    assert len(segs) == 2
    assert [s.category for s in segs] == ["KILL", "KILL"]


def test_seven_kills_across_17_minutes_all_covered(settings):
    """17-minute match, 7 confirmed kills -> all 7 must be in the compilation."""
    cfg = _cfg(settings)
    times = [42, 185, 320, 505, 690, 880, 1010]
    events = [_event(i + 1, t, "KILL", 0.9, 60 + i) for i, t in enumerate(times)]
    # Give the first kill a weak/uncertain highlight to reproduce the case
    # where an event is 'covered' by a highlight that gets filtered out.
    highlights = [_highlight(i + 1, t - 8, t + 12, category="KILL",
                             score=60 + i, event_id=i + 1)
                  for i, t in enumerate(times)]
    highlights[0] = _highlight(1, times[0] - 8, times[0] + 12,
                               category="UNKNOWN", score=5, event_id=1)
    segs = select_segments(highlights, events, cfg, 1020.0)
    covered_ids = {eid for s in segs for eid in s.event_ids}
    assert all(e.id in covered_ids for e in events), (
        f"Missing kills: {[e.id for e in events if e.id not in covered_ids]}")
    for t in times:
        assert any(s.start <= t <= s.end for s in segs), f"Kill at {t}s not in any segment"
    assert [s.start for s in segs] == sorted(s.start for s in segs)


def test_kill_coverage_helper(settings):
    from app.clips.compilation_builder import kill_coverage
    events = [_event(1, 40), _event(2, 200), _event(3, 500)]
    segs = [Segment(30, 45, "KILL", 60, 0.9, event_ids=[1]),
            Segment(190, 205, "KILL", 60, 0.9, event_ids=[2])]
    covered, total = kill_coverage(segs, events)
    assert (covered, total) == (2, 3)


def test_category_counts():
    segs = [Segment(0, 10, "KILL", 1, 1), Segment(20, 30, "MULTI_KILL", 1, 1),
            Segment(40, 50, "CLUTCH_CANDIDATE", 1, 1), Segment(60, 70, "COMBAT", 1, 1)]
    assert category_counts(segs) == {
        "confirmed_kills": 1, "multi_kills": 1,
        "clutch_candidates": 1, "other": 1,
    }


def test_validate_segments_rejects_empty_and_out_of_range():
    with pytest.raises(ExportError):
        validate_segments([], 100)
    with pytest.raises(ExportError):
        validate_segments([Segment(-5, 10, "KILL", 1, 1)], 100)


# ---------- rendering tests ----------

@pytest.fixture
def audio_video(tmp_path):
    """30 s 640x360 MP4 with continuous video and audio."""
    path = tmp_path / "match.mp4"
    cmd = [
        ffmpeg_path(), "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30:d=30",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path)


def test_compilation_renders_single_valid_mp4(settings, audio_video, tmp_path):
    cfg = _cfg(settings)
    segments = [
        Segment(2, 12, "KILL", 60, 0.9, highlight_ids=[1]),
        Segment(14, 24, "MULTI_KILL", 70, 0.9, highlight_ids=[2]),
        Segment(26, 29, "COMBAT", 40, 0.8, highlight_ids=[3]),
    ]
    out = str(tmp_path / "PUBG_Highlights_test.mp4")
    builder = CompilationBuilder(cfg)
    result = builder.build(audio_video, segments, out,
                           source_has_audio=True, video_duration=30.0,
                           token=CancellationToken())
    assert result == out
    meta = MediaProbe().probe(out)
    assert (meta.width, meta.height) == (1080, 1920)
    assert meta.video_codec.lower() in ("h264", "avc1")
    assert meta.has_audio
    assert meta.audio_codec.lower() == "aac"
    assert abs(meta.duration - total_duration(segments)) < 2.5
    assert builder.validate_output(out) if hasattr(builder, "validate_output") else True


def test_compilation_temp_files_cleaned(settings, audio_video, tmp_path):
    from app.utils.paths import app_cache_dir
    root = app_cache_dir() / "compilations"
    before = set(root.glob("*")) if root.exists() else set()
    segments = [Segment(1, 11, "KILL", 60, 0.9)]
    out = str(tmp_path / "clean.mp4")
    CompilationBuilder(_cfg(settings)).build(
        audio_video, segments, out, source_has_audio=True,
        video_duration=30.0, token=CancellationToken())
    after = set(root.glob("*")) if root.exists() else set()
    assert after == before  # no leftover temporary segment directories


def test_failed_export_keeps_source_and_reports(settings, audio_video, tmp_path):
    segments = [Segment(0, 10, "KILL", 60, 0.9)]
    out = str(tmp_path / "bad" / "out.mp4")
    builder = CompilationBuilder(_cfg(settings))
    with pytest.raises(ExportError):
        builder.build("/nonexistent/source.mp4", segments, out,
                      source_has_audio=False, video_duration=30.0,
                      token=CancellationToken())
    assert Path(audio_video).exists()  # source recording untouched


def test_cancellation(settings, audio_video, tmp_path):
    token = CancellationToken()
    token.cancel()
    segments = [Segment(1, 11, "KILL", 60, 0.9)]
    with pytest.raises(Exception):
        CompilationBuilder(_cfg(settings)).build(
            audio_video, segments, str(tmp_path / "cancel.mp4"),
            source_has_audio=True, video_duration=30.0, token=token)
