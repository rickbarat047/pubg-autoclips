"""Shared test fixtures and synthetic media generators."""
from __future__ import annotations

import numpy as np
import pytest

from app.config import AppSettings


@pytest.fixture
def settings(tmp_path) -> AppSettings:
    s = AppSettings()
    s.ign = "TESTPLAYER"
    s.output_folder = str(tmp_path / "exports")
    s.onboarding_complete = True
    return s


@pytest.fixture
def db(tmp_path):
    from app.database.db import DatabaseManager
    return DatabaseManager(tmp_path / "test.sqlite3")


@pytest.fixture
def synthetic_video(tmp_path):
    """Create a 6-second 640x360 MP4 with moving shapes and a sine tone."""
    import cv2
    path = tmp_path / "synthetic.mp4"
    w, h, fps, secs = 640, 360, 15, 6
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    rng = np.random.default_rng(42)
    for i in range(fps * secs):
        frame = np.full((h, w, 3), 30, dtype=np.uint8)
        # moving bright rectangle -> motion signal
        x = (i * 12) % (w - 80)
        cv2.rectangle(frame, (x, 100), (x + 60, 160), (200, 255, 60), -1)
        # noise band to vary texture
        frame[200:240] = rng.integers(20, 90, (40, w, 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return str(path)


@pytest.fixture
def quiet_settings(settings) -> AppSettings:
    settings.visual.enabled = False
    settings.audio.enabled = False
    settings.kill_feed.enabled = False
    return settings
