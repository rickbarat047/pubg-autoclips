"""FFprobe metadata extraction and media validation tests."""
from app.media.media_validator import MediaValidator
from app.media.probe import MediaProbe, ffmpeg_path, ffprobe_path


def test_probe_metadata(synthetic_video):
    meta = MediaProbe().probe(synthetic_video)
    assert meta.width == 640
    assert meta.height == 360
    assert meta.duration > 5.0
    assert meta.fps > 0
    assert meta.file_size > 1000


def test_validate_valid_video(synthetic_video):
    result = MediaValidator().validate(synthetic_video)
    assert result.valid, result.errors
    assert result.metadata is not None


def test_validate_missing_file():
    result = MediaValidator().validate("C:/definitely/not/here.mp4")
    assert not result.valid
    assert result.errors


def test_binary_discovery():
    # Both may be None in a bare dev environment; just ensure no exception.
    assert ffmpeg_path() is None or isinstance(ffmpeg_path(), str)
    assert ffprobe_path() is None or isinstance(ffprobe_path(), str)
