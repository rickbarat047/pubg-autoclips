"""Build FFmpeg filter graphs for vertical short-form layouts."""
from __future__ import annotations

from ..config import RenderSettings


def build_video_filter(settings: RenderSettings) -> str:
    """Return the video filter chain producing the target vertical canvas."""
    w, h = settings.width, settings.height
    if settings.layout == "crop":
        # Fills the frame but crops aggressively; documented trade-off.
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1")
    if settings.layout in ("pillarbox", "original"):
        # Original source aspect ratio with neutral background fill — no
        # cropping of kill feed, minimap or HUD.
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    # default: blurred background
    return (
        f"split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},gblur=sigma=28,colorchannelmixer=rr=0.55:gg=0.55:bb=0.55[bgo];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgo];"
        f"[bgo][fgo]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1[outv]"
    )


def video_encoder(settings: RenderSettings) -> str:
    return settings.hw_encoder if settings.hardware_encoding else "libx264"
