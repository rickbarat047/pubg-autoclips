"""Core bug fixes: settings persistence, export state, memory, portability."""
import subprocess


def test_apply_preset_preserves_manual_detection_values():
    """Changing preset must not revert manually-set Detection values on save."""
    from app.config import AppSettings

    s = AppSettings()
    s.kill_feed.sample_interval_sec = 1.7
    s.visual.sample_interval_sec = 1.3
    s.kill_feed.confidence_threshold = 0.62
    s.processing.preset = "balanced"

    # Saving calls apply_preset(current preset) — manual values must survive.
    s.apply_preset(s.processing.preset)

    assert s.kill_feed.sample_interval_sec == 1.7
    assert s.visual.sample_interval_sec == 1.3
    assert s.kill_feed.confidence_threshold == 0.62


def test_settings_reject_min_gt_max():
    """min>max duration/bounds must be rejected at construction."""
    from pydantic import ValidationError

    from app.config import ClipSettings, CompilationSettings

    try:
        ClipSettings(min_duration_sec=40, max_duration_sec=20)
    except ValidationError:
        pass
    else:
        raise AssertionError("ClipSettings accepted min>max")

    try:
        CompilationSettings(min_segment_sec=30, max_segment_sec=10)
    except ValidationError:
        pass
    else:
        raise AssertionError("CompilationSettings accepted min>max")


def test_ffprobe_uses_windows_creation_flags(monkeypatch):
    """ffprobe subprocess must pass Windows creation flags + DEVNULL stdin."""
    import app.media.probe as probe

    captured = {}

    class _Captured(Exception):
        pass

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        raise _Captured()

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    # Drive the static helper directly so we exercise the exact subprocess.run call.
    from pathlib import Path
    import pytest
    with pytest.raises(Exception):
        probe.MediaProbe._probe_ffprobe("ffprobe", Path("dummy.mp4"))
    assert "creationflags" in captured
    assert captured["creationflags"] & getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert captured.get("stdin") == subprocess.DEVNULL


def test_release_frames_frees_memory():
    """A helper must drop decoded frame references so RAM can be reclaimed."""
    from app.detection.pipeline import release_frames

    frames = [("1.0", object()), ("2.0", object())]
    release_frames(frames)
    assert frames == []


def test_mark_export_failed_and_unregister():
    """A failed export is marked in SQLite and its job is unregistered."""
    from app.core.job_manager import JobManager
    from app.database.db import DatabaseManager

    db = DatabaseManager(":memory:")
    jobs = JobManager(None)
    match = db.add_match(path="x.mp4", name="x", duration=10.0)
    export_id = db.add_export(match_id=match.id, path="out.mp4", status="pending").id
    token = object()
    jobs.register(export_id, "export", match.id, token)

    from app.rendering.export_manager import finalize_failed_export
    finalize_failed_export(db, jobs, export_id, "render exploded")

    row = db.get_export(export_id)
    assert row.status == "failed"
    assert "render exploded" in row.error
    assert not jobs.is_active(export_id)
