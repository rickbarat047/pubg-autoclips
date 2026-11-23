"""Review & Export page: drag math and persistence of manual clip ranges."""
from types import SimpleNamespace

from app.ui.compile_page import CompilationTimeline, CompilePage


def test_drag_clamps_and_rejects_tiny_ranges():
    assert CompilationTimeline.range_from_drag(590, 610, 600) == (590.0, 600.0)
    assert CompilationTimeline.range_from_drag(100, 100.2, 600) is None
    # Reversed (right-to-left) drags are normalised, not rejected: users drag
    # timelines in both directions and silent rejection feels broken.
    assert CompilationTimeline.range_from_drag(110, 100, 600) == (100.0, 110.0)


def test_manual_segments_are_appended_and_labelled(db, settings, qtbot):
    match = db.add_match(path="x.mp4", name="x", duration=600.0)
    db.add_manual_segment(match.id, 300.0, 320.0, "missed knock")
    ctx = SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)

    page = CompilePage(ctx)
    page.set_match(match.id)

    manual = [s for s in page.segments if s.category == "MANUAL"]
    assert len(manual) == 1
    assert "Added by you" in manual[0].source_labels
    assert manual[0].start == 300.0
    assert manual[0].end == 320.0
