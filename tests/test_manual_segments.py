"""Manual clip ranges must survive restarts in SQLite.

Catches: a reviewer adds a missed knock on the Review & Export page, exports,
closes the app, reopens it — the added range is gone because nothing persisted
it. This test drives the migration and CRUD that keep it.
"""
from app.database.db import DatabaseManager


def test_manual_segment_roundtrip(db: DatabaseManager) -> None:
    match_id = db.add_match(path="x.mp4", name="x", duration=600).id

    seg_id = db.add_manual_segment(match_id, 120.5, 140.5, "missed knock")

    rows = db.list_manual_segments(match_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == seg_id
    assert row["match_id"] == match_id
    assert row["start"] == 120.5
    assert row["end"] == 140.5
    assert row["note"] == "missed knock"
    assert row["created_at"]

    db.update_manual_segment(seg_id, 121.0, 141.0)
    updated = db.list_manual_segments(match_id)[0]
    assert updated["start"] == 121.0
    assert updated["end"] == 141.0
    assert updated["note"] == "missed knock"

    db.delete_manual_segment(seg_id)
    assert db.list_manual_segments(match_id) == []


def test_manual_segments_are_scoped_to_match(db: DatabaseManager) -> None:
    first = db.add_match(path="a.mp4", name="a", duration=600).id
    second = db.add_match(path="b.mp4", name="b", duration=600).id
    db.add_manual_segment(first, 10.0, 20.0)
    db.add_manual_segment(second, 30.0, 40.0)
    assert [r["start"] for r in db.list_manual_segments(first)] == [10.0]
    assert [r["start"] for r in db.list_manual_segments(second)] == [30.0]
