"""Regression: the UI must actually start the analysis worker and produce clips."""
from app.detection.kill_feed.ocr_engine import OcrEngine, OcrResult


def test_ui_analysis_creates_clips(qtbot, monkeypatch, settings, db, synthetic_video):
    import app.bootstrap as bootstrap

    settings.kill_feed.min_observations = 1
    settings.kill_feed.duplicate_window_sec = 10
    settings.scoring.min_event_score = 0
    settings.clips.min_duration_sec = 5
    settings.clips.max_duration_sec = 15
    settings.auto_export = False

    monkeypatch.setattr(bootstrap, "AppSettings", type("S", (), {"load": staticmethod(lambda: settings)}))
    monkeypatch.setattr(bootstrap, "DatabaseManager", lambda *a, **k: db)
    monkeypatch.setattr(
        OcrEngine, "recognize",
        lambda self, region: OcrResult("TESTPLAYER killed BOT", 0.9,
                                       ["TESTPLAYER killed BOT"]),
    )

    ctx = bootstrap.AppContext()
    from app.ui.main_window import MainWindow
    window = MainWindow(ctx)
    m = db.add_match(path=synthetic_video, name="synthetic.mp4", file_size=1,
                     duration=6, width=640, height=360, fps=15)
    window.start_analysis(m.id, synthetic_video, 6.0)

    # The worker used to be a local variable and was garbage-collected before
    # QThread started it, leaving the job stuck at "starting" with no clips.
    qtbot.waitUntil(lambda: (db.get_latest_job(m.id) or type("J", (), {"status": ""})()).status == "done",
                    timeout=90000)
    qtbot.waitUntil(lambda: len(db.list_highlights(m.id)) > 0, timeout=30000)
    job = db.get_latest_job(m.id)
    assert job.status == "done"
    assert len(db.list_events(m.id)) >= 1
    assert len(db.list_highlights(m.id)) >= 1
