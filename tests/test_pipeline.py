"""End-to-end pipeline test on synthetic footage."""
from app.core.task_queue import CancellationToken


class FakeOcr:
    def __init__(self):
        self.n = 0

    def recognize(self, region):
        from app.detection.kill_feed.ocr_engine import OcrResult
        self.n += 1
        if self.n <= 3:
            return OcrResult("", 0, [])
        return OcrResult("TESTPLAYER killed BOT", 0.9, ["TESTPLAYER killed BOT"])


def test_pipeline_end_to_end(settings, db, synthetic_video):
    settings.ign = "TESTPLAYER"
    settings.kill_feed.enabled = True
    settings.kill_feed.sample_interval_sec = 0.5
    settings.kill_feed.min_observations = 2
    settings.kill_feed.duplicate_window_sec = 10
    settings.audio.enabled = False  # synthetic clip has no real audio
    settings.visual.enabled = True
    settings.visual.sample_interval_sec = 0.5
    settings.scoring.min_event_score = 0
    settings.clips.min_duration_sec = 5
    settings.clips.max_duration_sec = 15

    from app.detection.pipeline import AnalysisPipeline
    m = db.add_match(path=synthetic_video, name="synthetic.mp4", file_size=1,
                     duration=6, width=640, height=360, fps=15)
    j = db.create_job(m.id)
    pipeline = AnalysisPipeline(settings, db, ocr=FakeOcr())
    result = pipeline.run(synthetic_video, m.id, j.id, 6.0,
                          token=CancellationToken(), overall_cb=lambda *a: None)
    assert result.feed_events
    assert result.events
    assert len(db.list_events(m.id)) == len(result.events)
    highlights = db.list_highlights(m.id)
    assert len(highlights) == len(result.clips)
    for h in highlights:
        assert 0 <= h.start < h.end <= 6.1
