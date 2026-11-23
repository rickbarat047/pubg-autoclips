"""Settings migration: review-before-export becomes the default."""
import json

from app.config import AppSettings


def test_explicit_auto_export_true_is_preserved(tmp_path):
    """A user who already enabled auto-export must keep that choice."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": 5, "auto_export": True}), encoding="utf-8")

    settings = AppSettings.load(path)

    assert settings.auto_export is True
    assert settings.version == 6


def test_default_auto_export_is_off():
    """New users review their clips before anything is exported."""
    assert AppSettings().auto_export is False
