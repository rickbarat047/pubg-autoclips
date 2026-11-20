"""Kill-feed duplicate suppression and confirmation tests with a fake OCR."""
from app.config import AppSettings
from app.detection.kill_feed.feed_detector import KillFeedDetector
from app.detection.kill_feed.ocr_engine import OcrResult


class FakeOcr:
    def __init__(self, script):
        self.script = script
        self.i = 0

    def recognize(self, region):
        text, conf = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return OcrResult(text, conf, [text] if text else [])


def test_multi_observation_and_duplicate_suppression(settings, synthetic_video):
    settings.ign = "TESTPLAYER"
    settings.kill_feed.sample_interval_sec = 0.5
    settings.kill_feed.min_observations = 2
    settings.kill_feed.duplicate_window_sec = 10.0
    # Persistent identical feed line for the whole (6s) video.
    script = [("TESTPLAYER killed BOT1", 0.9)] * 30
    det = KillFeedDetector(settings, FakeOcr(script))
    events = det.detect(synthetic_video)
    # Requires 2 observations, then suppresses the persistent duplicate.
    assert len(events) == 1
    assert events[0].observations >= 2
    assert events[0].category == "confirmed"


def test_changing_hud_text_does_not_block_confirmation(settings, synthetic_video):
    """Regression: alive-counter/compass digits change every sample, so using
    the whole OCR line as a dedup key produced ZERO events on real footage."""
    settings.ign = "rickbarat"
    settings.kill_feed.sample_interval_sec = 1.0
    settings.kill_feed.min_observations = 2
    settings.kill_feed.duplicate_window_sec = 10.0
    script = [
        ("85 ALIVE 210 compass 33[NTRS]rickbarat killed ENEMY", 0.9),
        ("84 ALIVE 195 compass 33[NTRS]rickbarat killed ENEMY2", 0.9),
        ("83 ALIVE 180 compass 33[NTRS]rickbarat killed ENEMY3", 0.9),
    ] + [("", 0.0)] * 10
    events = KillFeedDetector(settings, FakeOcr(script)).detect(synthetic_video)
    assert len(events) == 1
    assert events[0].category == "confirmed"


def test_knock_classification(settings, synthetic_video):
    settings.ign = "TESTPLAYER"
    settings.kill_feed.sample_interval_sec = 0.5
    settings.kill_feed.min_observations = 1
    ocr = FakeOcr([("TESTPLAYER knocked BOT", 0.9)] * 20)
    events = KillFeedDetector(settings, ocr).detect(synthetic_video)
    assert events
    assert events[0].category in ("knock", "confirmed")
