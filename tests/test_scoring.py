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


def test_knock_event_gets_own_category_and_survives_ranking():
    from app.detection.kill_feed.feed_detector import FeedEvent
    from app.detection.scoring.event_scorer import (
        CATEGORY_KNOCK, CATEGORY_KNOCK_CANDIDATE, EventScorer,
    )
    from app.detection.scoring.event_ranker import rank_events
    s = AppSettings()
    scorer = EventScorer(s)
    knock = scorer.score_feed_event(
        FeedEvent(10, "knock", 0.9, "rickbarat knocked X", 0.9, 3, "k"), [], [], [])
    candidate = scorer.score_feed_event(
        FeedEvent(20, "knock_candidate", 0.7, "rickbaratX X", 0.8, 2, "c"), [], [], [])
    assert knock.category == CATEGORY_KNOCK
    assert candidate.category == CATEGORY_KNOCK_CANDIDATE
    ranked = rank_events([knock, candidate], min_score=12.5)
    assert len(ranked) == 2


def test_ranking_keeps_kills_two_seconds_apart():
    a = _event(100, score=60)
    b = _event(102, score=60)
    assert len(rank_events([a, b], min_score=0)) == 2


def test_multi_kill_grouping_preserves_every_kill():
    events = [_event(10), _event(12), _event(14)]
    grouped, n = group_multi_kills(events)
    assert n == 1
    assert len(grouped) == 3  # no kill may be removed


def test_multi_kill_grouping():
    events = [_event(1), _event(3), _event(5)]
    grouped, n = group_multi_kills(events)
    assert n == 1
    assert len(grouped) == 3  # every individual kill is still present
    assert any(e.category in (CATEGORY_MULTI, "CLUTCH_CANDIDATE") for e in grouped)


def test_no_multi_for_distant_kills():
    events = [_event(1), _event(100)]
    grouped, n = group_multi_kills(events)
    assert n == 0
    assert len(grouped) == 2


def test_rank_filters_and_dedups():
    events = [_event(1, score=50), _event(2, score=40), _event(50, score=10)]
    ranked = rank_events(events, min_score=20)
    assert len(ranked) == 2  # distinct nearby kills survive; 50s is below threshold
