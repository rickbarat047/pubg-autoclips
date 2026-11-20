"""SQLite persistence tests."""
from app.database.db import DatabaseManager


def test_add_and_get_match(db):
    m = db.add_match(path="C:/videos/a.mp4", name="a.mp4", file_size=100,
                     duration=60, width=640, height=360, fps=30,
                     video_codec="h264", audio_codec="aac", status="imported")
    assert m.id > 0
    assert db.get_match(m.id).name == "a.mp4"
    assert db.get_match_by_path("C:/videos/a.mp4").id == m.id


def test_duplicate_import_detected(db):
    db.add_match(path="C:/videos/a.mp4", name="a.mp4", file_size=100, duration=1,
                 width=1, height=1, fps=1)
    from app.core.exceptions import DatabaseError
    try:
        db.add_match(path="C:/videos/a.mp4", name="a.mp4", file_size=100, duration=1,
                     width=1, height=1, fps=1)
        assert False, "expected duplicate error"
    except DatabaseError:
        pass


def test_jobs_events_highlights_exports(db):
    m = db.add_match(path="x.mp4", name="x.mp4", file_size=1, duration=10,
                     width=1, height=1, fps=1)
    j = db.create_job(m.id)
    db.update_job(j.id, status="running", stage="OCR", progress=0.5)
    assert db.get_job(j.id).status == "running"
    e = db.add_event(match_id=m.id, job_id=j.id, timestamp=1.5, category="KILL",
                     confidence=0.9, score=40, source="test", recognised_text="X",
                     ocr_confidence=0.9, manual=0, confirmed=1)
    assert len(db.list_events(m.id)) == 1
    h = db.add_highlight(match_id=m.id, event_id=e.id, start=0, end=20,
                         duration=20, score=40, category="KILL", keep=1, thumbnail="")
    assert db.get_highlight(h.id).keep == 1
    ex = db.add_export(clip_id=h.id, path="out.mp4", status="pending", layout="blurred")
    db.update_export(ex.id, status="done", size_bytes=1000)
    assert db.get_export(ex.id).status == "done"
    assert db.stats()["exports"] == 1


def test_settings_persistence(db):
    db.set_settings("ign", "PlayerX")
    assert db.get_settings("ign") == "PlayerX"


def test_persistence_across_reopen(tmp_path):
    path = tmp_path / "persist.sqlite3"
    db1 = DatabaseManager(path)
    db1.set_settings("ign", "PersistentPlayer")
    db1.add_match(path="p.mp4", name="p.mp4", file_size=1, duration=2,
                  width=1, height=1, fps=1)
    db1.close()
    db2 = DatabaseManager(path)
    assert db2.get_settings("ign") == "PersistentPlayer"
    assert len(db2.list_matches()) == 1
    db2.close()
