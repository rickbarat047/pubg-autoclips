"""Clip boundary, merge and duplicate tests."""
from app.clips.clip_boundaries import clamp_boundary, make_boundary
from app.clips.clip_merger import merge_overlaps
from app.clips.duplicate_remover import remove_duplicates


def test_boundary_basic():
    b = make_boundary(100, 600, 8, 12, 20, 60)
    assert b.start <= 92 and b.end >= 112
    assert 20 <= b.duration <= 60


def test_boundary_clamped_to_video():
    b = make_boundary(2, 10, 8, 12, 20, 60)
    assert b.start >= 0
    assert b.end <= 10


def test_boundary_min_duration():
    b = make_boundary(5, 100, 0, 2, 20, 60)
    assert b.duration >= 19.5


def test_merge_overlapping():
    clips = [make_boundary(10, 600, 0, 10, 20, 60),
             make_boundary(15, 600, 0, 10, 20, 60)]
    merged = merge_overlaps(clips)
    assert len(merged) == 1


def test_no_merge_when_far():
    clips = [make_boundary(10, 600, 0, 10, 20, 60),
             make_boundary(200, 600, 0, 10, 20, 60)]
    assert len(merge_overlaps(clips)) == 2


def test_duplicates_removed():
    a = make_boundary(50, 600, 0, 10, 20, 60)
    b = make_boundary(50.5, 600, 0, 10, 20, 60)
    assert len(remove_duplicates([a, b])) == 1


def test_clamp():
    c = clamp_boundary(-5, 1000, 600)
    assert c.start == 0 and c.end == 600
