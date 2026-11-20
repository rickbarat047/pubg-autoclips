"""Event scoring tests."""
from app.config import AppSettings
from app.detection.scoring.clutch_detector import group_multi_kills
from app.detection.scoring.event_ranker import rank_events
from app.detection.scoring.event_scorer import (
    CATEGORY_KILL, CATEGORY_MULTI, EventScorer, ScoredEvent,
)


def _event(t, category=CATEGORY_KILL, confidence=0.9, score=50):
    return ScoredEvent(timestamp=t, category=category, score=score,
                       confidence=confidence, source="test", recognised_text="",
                       ocr_confidence=0.9)


def test_confirmed_kill_higher_than_uncertain():
    s = AppSettings()
    scorer = EventScorer(s)
    from app.detection.kill_feed.feed_detector import FeedEvent
    confirmed = FeedEvent(1.0, "confirmed", 0.95, "X killed Y", 0.9, 3, "sig")
    uncertain = FeedEvent(1.0, "uncertain", 0.3, "??", 0.4, 1, "sig2")
    a = scorer.score_feed_event(confirmed, [], [], [])
    b = scorer.score_feed_event(uncertain, [], [], [])
    assert a.score > b.score
    assert a.category == CATEGORY_KILL


def test_uncertainty_penalty_reduces_score():
    s = AppSettings()
    scorer = EventScorer(s)
    from app.detection.kill_feed.feed_detector import FeedEvent
    hi = scorer.score_feed_event(FeedEvent(1, "confirmed", 1.0, "t", 1, 3, "a"), [], [], [])
    lo = scorer.score_feed_event(FeedEvent(1, "confirmed", 0.4, "t", 0.5, 1, "b"), [], [], [])
    assert hi.score > lo.score
    assert lo.breakdown["uncertainty_penalty"] < hi.breakdown["uncertainty_penalty"]


def test_multi_kill_grouping():
    events = [_event(1), _event(3), _event(5)]
    grouped, n = group_multi_kills(events)
    assert n == 1
    assert len(grouped) == 1
    assert grouped[0].category in (CATEGORY_MULTI, "CLUTCH_CANDIDATE")


def test_no_multi_for_distant_kills():
    events = [_event(1), _event(100)]
    grouped, n = group_multi_kills(events)
    assert n == 0
    assert len(grouped) == 2


def test_rank_filters_and_dedups():
    events = [_event(1, score=50), _event(2, score=40), _event(50, score=10)]
    ranked = rank_events(events, min_score=20)
    assert len(ranked) == 1  # 1s and 2s are near-duplicates; 50s below threshold
