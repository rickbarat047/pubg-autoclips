"""Regression tests for timeline/manual-clip and preview/playback bugs."""
from types import SimpleNamespace

import pytest


def test_scrub_slider_maps_fraction_to_seconds(qtbot, monkeypatch):
    """Scrubbing to the middle must seek to half the duration, not 1000x past it."""
    from app.ui.editor.preview_panel import PreviewPanel

    panel = PreviewPanel()
    captured = []
    monkeypatch.setattr(panel, "seek", lambda secs: captured.append(secs))
    panel._duration_ms = 100_000  # a 100-second source
    panel.seek_slider.setValue(500)  # halfway
    panel._scrub_end()
    assert captured and captured[-1] == pytest.approx(50.0), captured


def test_set_segments_clears_stale_manual_ranges(qtbot):
    """Reloading segments must not leave old dragged ranges painted/stored."""
    from app.ui.editor.timeline_panel import TimelinePanel

    tl = TimelinePanel()
    tl._ranges.append((10.0, 30.0))
    tl.set_segments([], 600.0)
    assert tl._ranges == []


def test_loading_match_seeks_preview_to_first_clip(qtbot, ctx, monkeypatch):
    """Opening a match must show the first clip's frame, not match time 0."""
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    m = ctx.db.add_match(path="x.mp4", name="x", duration=600.0)
    ctx.db.add_highlight(match_id=m.id, start=100.0, end=120.0,
                         duration=20.0, score=80.0, category="KILL", keep=1)
    seeks = []
    monkeypatch.setattr(win.preview, "seek", lambda t: seeks.append(t))
    win.open_review(m.id)
    assert seeks and seeks[-1] == pytest.approx(100.0), seeks


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           shutdown=lambda: None)
