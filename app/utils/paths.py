"""Application path resolution using platformdirs.

All persistent data (config, database, logs, caches, models) lives in a
per-user application data directory.  Nothing is written next to the
executable unless the user explicitly chooses an output folder.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir, user_cache_dir

APP_NAME = "PUBG AutoClips"
APP_AUTHOR = "PUBG AutoClips"

# Portable default folder for exported vertical clips: the user's Videos
# library.  No machine-specific drive letter — this works on any Windows
# account and on any drive.  Users can override it in Settings/Onboarding; a
# saved choice in settings.json always takes precedence over this default.
DEFAULT_OUTPUT_FOLDER = str(Path.home() / "Videos" / "PUBG AutoClips" / "exports")


def default_output_folder() -> str:
    return DEFAULT_OUTPUT_FOLDER


def app_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def app_log_dir() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def app_cache_dir() -> Path:
    return Path(user_cache_dir(APP_NAME, APP_AUTHOR))


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def database_path() -> Path:
    return app_data_dir() / "pubg_autoclips.sqlite3"


def resource_base() -> Path:
    """Base directory for bundled resources (source tree or PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def model_dir() -> Path:
    override = os.environ.get("PUBG_AC_MODEL_DIR")
    if override:
        return Path(override)
    bundled = resource_base() / "models"
    if bundled.exists():
        return bundled
    return app_data_dir() / "models"


def ocr_models_dir() -> Path:
    local = resource_base() / "models" / "ocr"
    if local.exists():
        return local
    return app_data_dir() / "models" / "ocr"


def bundled_bin_dir() -> Path:
    """Directory that may contain bundled ffmpeg/ffprobe binaries."""
    return resource_base() / "bin"


def temp_dir() -> Path:
    d = app_cache_dir() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def thumbnails_dir() -> Path:
    d = app_cache_dir() / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_dirs() -> None:
    for p in (app_data_dir(), app_log_dir(), app_cache_dir(), temp_dir(),
              thumbnails_dir(), model_dir(), ocr_models_dir()):
        p.mkdir(parents=True, exist_ok=True)
