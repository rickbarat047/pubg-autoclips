"""Integration: visible editor shell receives real data after analysis/review."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           shutdown=lambda: None)


def test_open_review_populates_visible_shell(qtbot, ctx, monkeypatch):
    """The visible panels must be filled, not just hidden legacy pages."""
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    m = ctx.db.add_match(path="x.mp4", name="x", duration=600.0)
    h = ctx.db.add_highlight(match_id=m.id, start=100.0, end=120.0,
                             duration=20.0, score=80.0, category="KILL", keep=1)

    win.open_review(m.id)

    # Timeline has the real match duration so drag-to-add maps correctly.
    assert abs(win.timeline.duration - 600.0) < 0.01
    # Assets lists match + highlight.
    assert win.assets.media_list.count() >= 1
    assert win.assets.clip_list.count() >= 1
    # Preview has a source and bounds from the first highlight.
    assert win.preview.source_path == m.path


def test_clip_selected_loads_preview_and_inspector(qtbot, ctx, monkeypatch):
    """Clicking an asset clip loads the centre preview + inspector (no dialog)."""
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    m = ctx.db.add_match(path="x.mp4", name="x", duration=600.0)
    h = ctx.db.add_highlight(match_id=m.id, start=100.0, end=120.0,
                             duration=20.0, score=80.0, category="KILL", keep=1)
    win.open_review(m.id)

    called = {}
    monkeypatch.setattr(win.preview, "set_source",
                        lambda p: called.setdefault("source", p))
    monkeypatch.setattr(win.preview, "set_bounds",
                        lambda s, e=None: called.setdefault("bounds", (s, e)))
    win.assets.clip_selected.emit(h.id)

    assert called.get("source") == m.path
    assert called.get("bounds", (None,))[0] == pytest.approx(100.0)
