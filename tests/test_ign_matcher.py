"""Text normalisation and IGN matching tests."""
from app.detection.kill_feed.ign_matcher import (
    classify_feed_line, ign_match_score, is_match, looks_like_knock, normalize_text,
)


def test_normalize_text():
    assert "testplayer" in normalize_text("[TEST]PLAYER-42!")
    assert normalize_text("  Pro Gamer  ") == "progamer"


def test_ign_exact_and_contained():
    assert ign_match_score("TESTPLAYER", "TESTPLAYER") == 1.0
    assert ign_match_score("TESTPLAYER killed BOT", "TESTPLAYER") == 0.95
    assert is_match("TESTPLAYER knocked ENEMY", "TESTPLAYER")


def test_ign_confusion_tolerance():
    score = ign_match_score("TESTPL4YER", "TESTPLAYER")
    assert score >= 0.75


def test_unrelated_name():
    assert ign_match_score("SOMEBODYELSE killed BOT", "TESTPLAYER") < 0.6
    assert classify_feed_line("A killed B", "TESTPLAYER") == "unrelated"


def test_classification_levels():
    assert classify_feed_line("TESTPLAYER killed BOT", "TESTPLAYER") == "confirmed"
    assert classify_feed_line("TESTPL4YER killed BOT", "TESTPLAYER") in ("confirmed", "possible")


def test_knock_indicator():
    assert looks_like_knock("TESTPLAYER knocked ENEMY")
    assert not looks_like_knock("TESTPLAYER killed ENEMY")
