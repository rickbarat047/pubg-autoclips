"""Inspector + timeline panel regression tests (single-window editor)."""
import pytest


def test_timeline_drag_maps_pixels_to_seconds(qtbot):
    """A drag across the timeline must map pixel x to match time, not raw px."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from app.ui.editor.timeline_panel import TimelinePanel

    panel = TimelinePanel()
    panel.setFixedWidth(1000)
    panel.set_segments([], 600.0)
    panel.show()
    qtbot.waitExposed(panel)
    QTest.mousePress(panel, Qt.LeftButton, pos=QPoint(500, 60))
    QTest.mouseMove(panel, pos=QPoint(598, 60))
    QTest.mouseRelease(panel, Qt.LeftButton, pos=QPoint(598, 60))
    assert len(panel._ranges) == 1
    start, end = panel._ranges[-1]
    assert 295 <= start <= 305
    assert 355 <= end <= 365


def test_playhead_follows_click(qtbot):
    """Clicking the track moves the playhead to the clicked time."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from app.ui.editor.timeline_panel import TimelinePanel

    panel = TimelinePanel()
    panel.setFixedWidth(1000)
    panel.set_segments([], 600.0)
    panel.show()
    qtbot.waitExposed(panel)
    with qtbot.waitSignal(panel.playhead_changed, timeout=2000) as sig:
        QTest.mouseClick(panel, Qt.LeftButton, pos=QPoint(500, 60))
    assert 295 <= sig.args[0] <= 305


def test_inspector_edits_emit_bounds(qtbot):
    """Editing a segment's start/end emits bounds_changed with the new values."""
    from app.clips.compilation_builder import Segment
    from app.ui.editor.inspector_panel import InspectorPanel

    panel = InspectorPanel()
    qtbot.addWidget(panel)
    seg = Segment(start=100.0, end=120.0, category="KILL", score=80.0, confidence=0.9)
    seg.evidence = {"manual_id": 7}
    panel.set_segment(seg)
    with qtbot.waitSignal(panel.bounds_changed, timeout=2000) as sig:
        panel.start_sb.setValue(105.0)
    assert sig.args[0] == 7
    assert abs(sig.args[1] - 105.0) < 0.01


def test_add_at_playhead_returns_20s_range(qtbot):
    """add_at_playhead returns a 20-second range clamped to the duration."""
    from app.ui.editor.timeline_panel import TimelinePanel

    panel = TimelinePanel()
    panel.set_segments([], 600.0)
    panel.set_playhead(300.0)
    start, end = panel.add_at_playhead()
    assert abs(start - 300.0) < 0.01
    assert abs(end - 320.0) < 0.01
    # clamped at end
    panel.set_playhead(595.0)
    start, end = panel.add_at_playhead()
    assert end <= 600.0
