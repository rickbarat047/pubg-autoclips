"""RMS energy and spike detection on audio chunks (pure numpy functions)."""
from __future__ import annotations

import numpy as np


def rms(samples: np.ndarray) -> float:
    if samples is None or samples.size == 0:
        return 0.0
    x = samples.astype(np.float64) / 32768.0
    return float(np.sqrt(np.mean(x * x)))


def peak(samples: np.ndarray) -> float:
    if samples is None or samples.size == 0:
        return 0.0
    return float(np.max(np.abs(samples.astype(np.float64))) / 32768.0)


def zscore_normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    std = float(np.std(values))
    if std < 1e-9:
        return np.zeros_like(values)
    return (values - float(np.mean(values))) / std


def detect_spikes(energies: np.ndarray, sensitivity: float = 0.5,
                  min_neighbors: int = 2) -> np.ndarray:
    """Return boolean mask of windows whose energy is a local spike.

    Lower ``sensitivity`` means more spikes are detected.
    """
    if energies.size == 0:
        return np.zeros(0, dtype=bool)
    z = zscore_normalize(energies)
    threshold = 2.8 - 1.8 * float(np.clip(sensitivity, 0, 1))
    mask = z > threshold
    # Require the spike to exceed neighbours to avoid plateaus.
    for i in range(energies.size):
        if not mask[i]:
            continue
        lo = max(0, i - min_neighbors)
        hi = min(energies.size, i + min_neighbors + 1)
        neighbors = np.delete(energies[lo:hi], i - lo)
        if neighbors.size and energies[i] < np.median(neighbors) * 1.15:
            mask[i] = False
    return mask


def spectral_flatness(samples: np.ndarray, sample_rate: int = 16000) -> float:
    """Wiener flatness (0=tonal, 1=noise-like); useful for gunshot texture."""
    if samples is None or samples.size < 64:
        return 0.0
    x = samples.astype(np.float64)
    if np.max(np.abs(x)) < 1:
        return 0.0
    spectrum = np.abs(np.fft.rfft(x * np.hanning(x.size))) + 1e-10
    geo = float(np.exp(np.mean(np.log(spectrum))))
    arith = float(np.mean(spectrum))
    return float(np.clip(geo / arith, 0.0, 1.0))
