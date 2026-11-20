"""Audio energy and worker cancellation tests."""
import numpy as np

from app.core.task_queue import CancellationToken, CancelledError
from app.detection.audio.energy_detector import detect_spikes, rms, spectral_flatness


def test_rms():
    assert rms(np.zeros(100, dtype=np.int16)) == 0.0
    assert rms(np.full(100, 32767, dtype=np.int16)) > 0.9


def test_spike_detection():
    energies = np.array([0.1, 0.1, 0.1, 2.0, 0.1, 0.1, 0.1, 0.1])
    mask = detect_spikes(energies, sensitivity=0.8)
    assert mask[3]


def test_spectral_flatness_range():
    x = np.random.default_rng(1).normal(0, 1000, 1024)
    f = spectral_flatness(x)
    assert 0 <= f <= 1


def test_token_cancel():
    t = CancellationToken()
    assert not t.is_cancelled()
    t.cancel()
    assert t.is_cancelled()
    try:
        t.check()
        assert False
    except CancelledError:
        pass


def test_token_pause_resume():
    t = CancellationToken()
    t.pause()
    assert t.is_paused()
    t.resume()
    assert not t.is_paused()
