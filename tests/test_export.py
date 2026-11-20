"""FFmpeg rendering and export validation tests (require ffmpeg on PATH/bin)."""
import pytest

from app.config import AppSettings
from app.media.probe import ffmpeg_path
from app.rendering.export_manager import ExportManager, ExportRequest, free_space_gb

pytestmark = pytest.mark.skipif(ffmpeg_path() is None,
                                reason="ffmpeg not installed in this environment")


def test_build_command(settings, synthetic_video):
    em = ExportManager(settings)
    req = ExportRequest(synthetic_video, 1.0, 3.0,
                        str(settings.output_folder + "/out.mp4"), source_has_audio=False)
    cmd = em.build_command(req)
    assert cmd[0] == em.ffmpeg
    assert "-filter_complex" in cmd
    assert "1080:1920" in " ".join(cmd)
    assert "libx264" in cmd


def test_render_and_validate(settings, synthetic_video):
    em = ExportManager(settings)
    out = f"{settings.output_folder}/vertical.mp4"
    req = ExportRequest(synthetic_video, 0.5, 2.5, out, source_has_audio=False)
    from pathlib import Path
    path = em.render(req)
    assert Path(path).resolve() == Path(out).resolve()
    assert em.validate(path)


def test_free_space():
    assert free_space_gb(".") > 0


def test_run_uses_devnull_stdin(monkeypatch):
    """Windowed apps have no valid console stdin; FFmpeg must not inherit it."""
    import subprocess
    from app.rendering.ffmpeg_runner import run
    captured: dict = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured.update(kwargs)
            self.returncode = 0

        def communicate(self, timeout=None):
            return "", ""

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    result = run(["ffmpeg", "-version"])
    assert result.ok
    assert captured.get("stdin") == subprocess.DEVNULL
    assert captured.get("creationflags") & subprocess.CREATE_NEW_PROCESS_GROUP


def test_audio_preserved(tmp_path, settings):
    """Export must keep the original gameplay audio stream."""
    import subprocess
    from app.media.probe import MediaProbe
    ffmpeg = ffmpeg_path()
    src = str(tmp_path / "with_audio.mp4")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=green:s=640x360:r=15:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", src,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    out = str(settings.output_folder + "/audio_clip.mp4")
    em = ExportManager(settings)
    path = em.render(ExportRequest(src, 0.5, 2.0, out, source_has_audio=True))
    meta = MediaProbe().probe(path)
    assert meta.has_audio, "exported clip lost its audio stream"
    assert meta.audio_codec.lower() == "aac"
