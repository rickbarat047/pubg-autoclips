"""Regression: no automatic export; every clip (tool or manual) is removable."""
from types import SimpleNamespace


def test_analysis_done_never_auto_exports(qtbot, settings, db, monkeypatch):
    """Analysing a match must never save a clip automatically."""
    from app.ui.main_window import MainWindow

    ctx = SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                          shutdown=lambda: None)
    settings.auto_export = True  # even an explicitly-enabled stale setting
    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    m = db.add_match(path="x.mp4", name="x", duration=600.0)
    win.current_match_id = m.id

    called = []
    monkeypatch.setattr(win, "start_compilation", lambda *a, **k: called.append("comp"))
    monkeypatch.setattr(win, "_start_export", lambda *a, **k: called.append("export"))

    result = SimpleNamespace(events=[], clips=[], highlight_ids=[1], elapsed_sec=1.0)
    win._analysis_done(result)
    assert called == []  # nothing saved automatically


def test_tool_clip_is_removable(db, settings):
    """A tool-made segment can be discarded and stays discarded after reload."""
    from app.ui.compile_page import CompilePage
    from app.clips.compilation_builder import segment_signature

    ctx = SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)
    m = db.add_match(path="x.mp4", name="x", duration=600.0)
    job = db.create_job(m.id)
    ev = db.add_event(match_id=m.id, job_id=job.id, timestamp=100.0, category="KILL",
                      confidence=0.9, score=80.0, source="kill_feed_ocr")
    db.add_highlight(match_id=m.id, event_id=ev.id, start=95.0, end=115.0,
                     duration=20.0, score=80.0, category="KILL", keep=1)

    page = CompilePage(ctx)
    page.set_match(m.id)
    assert len(page.segments) >= 1
    seg = page.segments[0]
    sig = segment_signature(seg)

    # Discard the tool clip (the Remove button path persists this signature).
    db.add_discarded_segment(m.id, sig)
    page.set_match(m.id)
    assert all(segment_signature(s) != sig for s in page.segments)
