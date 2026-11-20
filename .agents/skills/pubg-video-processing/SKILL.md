---
name: pubg-video-processing
description: FFmpeg/FFprobe, video decoding, frame extraction, accurate clip extraction, vertical Shorts rendering, audio preservation and export verification for PUBG AutoClips. Use when changing clip boundaries, FFmpeg commands, vertical layouts, encoders or export validation.
---

# PUBG Video Processing (project-specific)

## Binaries and paths

- FFmpeg/FFprobe are resolved by `app/media/probe.py::find_binary`: explicit settings override,
  then PATH, then `<resource_base>/bin`.
- Development binaries live in `G:\PUBG AUTOCLIPS\bin` (BtbN win64 GPL **shared** build).
  Shared builds need all DLLs copied alongside the EXEs.
- This build has `libx264` **and** `h264_amf`. LGPL builds lack libx264 — `ExportManager`
  detects encoders and falls back `libx264 → libopenh264 → mpeg4`.
- Output folder default: `G:\PUBG AUTOCLIPS\exports`.

## Relevant modules

| Concern | Module |
|---|---|
| Metadata | `app/media/probe.py`, `app/media/media_validator.py` |
| One-pass frame extraction | `app/media/frame_extractor.py` |
| Timestamp seek / single frame | `app/media/video_reader.py`, `app/media/decoder.py` |
| Clip boundaries / merge / dedup | `app/clips/*.py` |
| FFmpeg process runner | `app/rendering/ffmpeg_runner.py` |
| Layout filter graphs | `app/rendering/vertical_layout.py` |
| Audio args | `app/rendering/audio_mixer.py` |
| Render + validation | `app/rendering/export_manager.py`, `app/rendering/video_renderer.py` |

## Frame extraction (keep this fast)

- Use FFmpeg `-vf fps=1/<interval> -q:v 5 <dir>/f%06d.jpg`, **one decode pass** for the whole file.
  Measured ~11 s for a 16.6 min 1080p recording (500 frames at 2 s interval).
- Never seek with `cv2.CAP_PROP_POS_FRAMES` per sample on long H.264 files: measured 0.12 s per
  seek, minutes of wasted time. OpenCV seeking is only the fallback when FFmpeg is missing.
- Timestamp of frame `i` is `i * interval`; clean up the temp directory after analysis.

## Clip boundaries

- `make_boundary(event, duration, pre, post, min, max)` — default pre 8 s, post 12 s,
  min 20 s, max 60 s. Clamp to `[0, duration]` and keep the event inside.
- Merge overlapping/adjacent clips with `merge_overlaps(gap)`; drop near-identical windows with
  `remove_duplicates(tolerance)`.
- Never emit clips shorter than the minimum unless the user manually requests it.

## Vertical rendering

- Default layout **blurred** (full gameplay centred over a blurred, darkened enlarged copy).
  This avoids cropping the kill feed and minimap. Alternative presets: `crop`, `pillarbox`.
- Filter chain for blurred layout:

  ```
  split=2[bg][fg];
  [bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,
      gblur=sigma=28,colorchannelmixer=rr=0.55:gg=0.55:bb=0.55[bgo];
  [fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgo];
  [bgo][fgo]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1[outv]
  ```

  The `[outv]` label is required or FFmpeg reports "Output with label 'outv' does not exist".
- Avoid the `eq` filter: BtbN LGPL/shared builds may not include it. Use `colorchannelmixer`.
- Encode: MP4, H.264 (`libx264`, CRF 21, preset `veryfast`), 1080x1920, 30 FPS, yuv420p,
  AAC 192 kbps 48 kHz, `+faststart`. Use `-ss` before `-i` and `-t` for the duration.
- Always pass commands as an argv list (never shell=True) so paths with spaces work.

## Audio preservation

- Map original audio with `-map 0:a:0?` and re-encode AAC; if no audio stream, use `-an`.
- Validate exported files with `MediaProbe`: width/height, duration > 0.5, h264/avc1 codec,
  and audio stream present when the source had one.
- Export records (path, status, size, layout) go to the `exports` SQLite table.

## Verification

- `pytest tests/test_export.py tests/test_media.py tests/test_clips.py`
- Expected real output: 1080x1920, 30 FPS, h264, AAC, playable MP4.
- Measured render: ~0.3–0.8 s for a 3 s source clip on the target machine.
