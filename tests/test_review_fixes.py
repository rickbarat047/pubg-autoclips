"""Regression tests for whole-branch review findings on the Review & Export page."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from app.ui.compile_page import CompilationTimeline, CompilePage, SegmentRow
from app.ui.dashboard import DashboardPage
from app.ui.video_player_dialog import VideoPlayerDialog


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)


def test_drag_maps_pixels_to_timeline_seconds(qtbot):
    """Dragging at the visual midpoint of a 10-min match must add ~05:00, not x=500 s."""
    timeline = CompilationTimeline()
    qtbot.addWidget(timeline)
    timeline.setFixedWidth(1000)
    timeline.setMinimumHeight(96)
    timeline.set_data([], 600.0)
    timeline.show()
    qtbot.waitExposed(timeline)

    with qtbot.waitSignal(timeline.segment_drag_created, timeout=2000) as sig:
        QTest.mousePress(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(500, 42))
        QTest.mouseMove(timeline, QPoint(598, 42))
        QTest.mouseRelease(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(598, 42))

    start, end = sig.args
    assert 295.0 <= start <= 305.0
    assert 355.0 <= end <= 365.0


def test_sub_half_second_drag_is_rejected():
    """The drag guard must agree with validate_segments (>=0.5 s) so export cannot fail."""
    assert CompilationTimeline.range_from_drag(100.0, 100.3, 600.0) is None
    assert CompilationTimeline.range_from_drag(100.0, 100.6, 600.0) is not None


def test_manual_segments_are_sorted_by_start(db, settings, qtbot):
    """Manually added ranges must appear in chronological order, not append order."""
    match = db.add_match(path="x.mp4", name="x", duration=600.0)
    db.add_manual_segment(match.id, 500.0, 520.0, "later")
    db.add_manual_segment(match.id, 200.0, 220.0, "earlier")
    page = CompilePage(SimpleNamespace(settings=settings, db=db, bus=None, jobs=None))
    qtbot.addWidget(page)
    page.set_match(match.id)
    starts = [s.start for s in page.segments]
    assert starts == sorted(starts)


def test_manual_spinbox_edits_persist(db, settings, qtbot):
    """Editing a manual range's start/end must update SQLite, not just memory."""
    match = db.add_match(path="x.mp4", name="x", duration=600.0)
    manual_id = db.add_manual_segment(match.id, 200.0, 220.0, "edit me")
    page = CompilePage(SimpleNamespace(settings=settings, db=db, bus=None, jobs=None))
    qtbot.addWidget(page)
    page.set_match(match.id)
    row = next(r for r in page.findChildren(SegmentRow)
               if r.segment.evidence.get("manual_id") == manual_id)
    row.start_sb.setValue(205.0)
    stored = db.list_manual_segments(match.id)
    assert stored[0]["start"] == pytest.approx(205.0)


def test_marker_click_seeks_player(db, settings, synthetic_video, qtbot, monkeypatch):
    """Clicking a timeline marker must seek the inline player to that segment."""
    match = db.add_match(path=str(synthetic_video), name="x", duration=6.0)
    db.add_manual_segment(match.id, 2.0, 4.0, "marker")
    page = CompilePage(SimpleNamespace(settings=settings, db=db, bus=None, jobs=None))
    qtbot.addWidget(page)
    page.set_match(match.id)
    assert page._player is not None
    calls = []
    monkeypatch.setattr(page._player, "seek", lambda seconds: calls.append(seconds))
    page.timeline.segment_selected.emit(0)
    assert calls and calls[0] == pytest.approx(page.segments[0].start)


def test_player_has_seek_api(synthetic_video, qtbot):
    """The player must expose seek(seconds) so the review page can drive it."""
    player = VideoPlayerDialog(str(synthetic_video))
    qtbot.addWidget(player)
    assert hasattr(player, "seek")
    player.seek(2.0)
    qtbot.waitUntil(lambda: abs(player.position() - 2.0) < 0.3, timeout=3000)


def test_dashboard_exposes_highlights_without_sidebar(qtbot, ctx):
    """With Highlights off the sidebar, the Dashboard must offer a way to the gallery."""
    page = DashboardPage(ctx)
    qtbot.addWidget(page)
    button = next(b for b in page.findChildren(QPushButton)
                  if b.text().strip() == "All highlights")
    with qtbot.waitSignal(page.highlights_requested):
        button.click()
