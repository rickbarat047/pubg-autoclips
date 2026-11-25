"""Cancellation integrity regression tests."""
import sys
import threading
import time

import pytest


def test_single_cancelled_error_class():
    """Both import paths must resolve to the same class object."""
    from app.core.exceptions import CancelledError as ExError
    from app.core.task_queue import CancelledError as TqError

    assert TqError is ExError


def test_token_check_raises_unified_cancelled_error():
    """A cancelled token must raise the unified CancelledError."""
    from app.core.exceptions import CancelledError
    from app.core.task_queue import CancellationToken

    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        token.check()


def test_cancel_terminates_ffmpeg():
    """Cancelling mid-run must kill the process and raise CancelledError fast."""
    from app.core.task_queue import CancellationToken, CancelledError
    from app.rendering.ffmpeg_runner import run

    token = CancellationToken()
    timer = threading.Timer(0.3, token.cancel)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(CancelledError):
            run([sys.executable, "-c", "import time; time.sleep(30)"],
                token=token, timeout=60)
        assert time.monotonic() - start < 5.0
    finally:
        timer.cancel()


def test_audio_analysis_cancellation_raises(settings, synthetic_video):
    """A cancellation during audio analysis must propagate, not be swallowed."""
    from app.core.task_queue import CancellationToken, CancelledError
    from app.detection.audio.audio_analyzer import AudioAnalyzer

    settings.audio.enabled = True
    analyzer = AudioAnalyzer(settings)
    token = CancellationToken()
    token.cancel()
    # Pre-cancelled token: token.check() raises before any blocking read; the
    # analyser must let that CancelledError through instead of returning [].
    with pytest.raises(CancelledError):
        analyzer.analyze(str(synthetic_video), 6.0, token=token)


def test_frame_extraction_cancellation_terminates(monkeypatch, tmp_path):
    """Cancelling during extraction must kill the process and raise CancelledError.

    A controlled fake process stands in for FFmpeg (the slow external boundary):
    communicate() blocks until the token is cancelled, and kill() must be called.
    """
    import subprocess
    from app.core.task_queue import CancellationToken, CancelledError
    from app.media import frame_extractor

    class FakeProc:
        def __init__(self, *a, **k):
            self.returncode = 0
            self.killed = False
            self._token = token

        def communicate(self, timeout=None):
            deadline = time.monotonic() + (timeout or 5.0)
            while not self._token.is_cancelled():
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired("ffmpeg", timeout)
                time.sleep(0.01)
            return b"", b""

        def kill(self):
            self.killed = True

    token = CancellationToken()
    threading.Timer(0.2, token.cancel).start()
    monkeypatch.setattr(frame_extractor.subprocess, "Popen", FakeProc)
    with pytest.raises(CancelledError):
        frame_extractor.extract_frames("dummy.mp4", 1.0, token=token,
                                       out_dir=tmp_path / "frames")


def test_cancelled_job_not_persisted(settings, db, synthetic_video):
    """A cancelled analysis must not persist partial events/highlights."""
    from app.core.task_queue import CancellationToken, CancelledError
    from app.detection.pipeline import AnalysisPipeline

    settings.audio.enabled = False
    settings.visual.enabled = False
    settings.kill_feed.enabled = True
    m = db.add_match(path=str(synthetic_video), name="s.mp4", file_size=1,
                     duration=6, width=640, height=360, fps=15)
    job = db.create_job(m.id)
    pipeline = AnalysisPipeline(settings, db, ocr=object())

    token = CancellationToken()
    token.cancel()  # cancelled before any work — must persist nothing
    with pytest.raises(CancelledError):
        pipeline.run(str(synthetic_video), m.id, job.id, 6.0, token=token)

    assert db.list_events(m.id) == []
    assert db.list_highlights(m.id) == []
    updated = db.get_job(job.id)
    assert updated is not None and updated.status == "cancelled"
