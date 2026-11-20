# PUBG AutoClips — Completion Report

## 1. Features implemented

- **Foundation**: Python 3.11 64-bit, PySide6 UI, Pydantic-validated settings,
  platformdirs storage, rotating file logs, hardware info module.
- **Database**: SQLite with migrations, settings/matches/jobs/events/highlights/
  exports tables, thread-safe `DatabaseManager`, full CRUD, persistence across
  restarts.
- **Onboarding**: IGN entry, screenshot/video-frame kill-feed calibration with
  draggable rectangle, live preview, OCR test, output-folder selection. Region
  stored as normalised coordinates; recalibratable from Settings.
- **Import**: Drag-and-drop and file browser, FFprobe metadata (duration,
  resolution, FPS, codecs, audio stream), validation with actionable warnings,
  duplicate-import detection.
- **Analysis pipeline** (background QThread, never blocks GUI):
  - Kill-feed OCR (RapidOCR/ONNX Runtime, CPU) with preprocessing, normalised
    text matching against IGN, multi-observation confirmation, time-window
    duplicate suppression, confidence/recognised text persisted, knock
    indicators when feed text exposes them.
  - Streaming audio analysis (RMS, spikes, spectral flatness) via FFmpeg PCM
    chunks — never loads the full track into RAM.
  - OpenCV motion + scene-change analysis at configurable sampling intervals.
  - Weighted, explainable event scoring with per-signal evidence breakdown.
  - Multi-kill / clutch-*candidate* grouping (no fabricated 1vX labels).
  - Clip selection with pre/post-roll, 20–60 s bounds, overlap merging and
    duplicate removal.
  - Pause/resume and cancel via cancellation tokens.
- **UI**: Premium dark-charcoal/electric-lime theme, sidebar navigation,
  dashboard with live DB statistics, import page, analysis progress page,
  highlight gallery with thumbnails/filters/keep-discard, clip editor with
  timeline scrubbing and approximate vertical preview, comprehensive settings,
  About page.
- **Rendering/export**: FFmpeg vertical layouts (blurred background default,
  crop, pillarbox, original-aspect), 1080×1920/30 FPS/H.264/AAC, original
  gameplay audio preserved, path-with-spaces safe, encoder capability detection
  (libx264 → libopenh264 → mpeg4 fallback; AMF only when available), output
  validation, exports recorded in DB.
- **Single Highlight Compilation (default)**: one match → one MP4. Smart
  pre/post boundaries (10/5 s, 10–30 s segments), overlap/short-gap merging,
  confirmed-kill prioritisation, chronological ordering (optional by score),
  short audio fades, stream-copy concat with re-encode fallback, full output
  verification and temp cleanup. Separate individual clips remain an optional
  mode. Dedicated Export page with stats, timeline, editable segments, preview,
  Open Folder and Play Video actions.
- **Services named in the spec**: `ProjectManager`, `JobManager`, `TaskQueue`,
  `EventBus`, `DatabaseManager`, `MediaProbe`, `AnalysisPipeline`,
  `HighlightScoringEngine` (alias of `EventScorer`), `ClipSelector`,
  `VideoRenderer`, `ExportManager`.
- **Packaging scripts**: `scripts/setup_windows.ps1`, `scripts/build_windows.ps1`
  with FFmpeg licence notice generation.

## 2. Features not implemented

- Verified kill-vs-knock classification from OCR alone (deliberately avoided —
  feed text rarely distinguishes them reliably).
- Verified clutch (1v2/1v3/1v4) labels — only "CLUTCH_CANDIDATE" is produced,
  with an explicit evidence note that player-count data is unavailable.
- HUD reading (alive count, HP, weapon) or any neural detector beyond OCR.
- GPU inference for OCR (CPU ONNX only, by design for the target hardware).
- `FUNNY_CANDIDATE` and `LONG_RANGE_CANDIDATE` automatic detection (categories
  exist in the model but no detector produces them).
- Resume-after-interrupt of a partially completed analysis (events are written
  on completion; cancelled runs are marked cancelled but must be restarted).
- Clean-machine verification of the frozen executable.

## 3. Dependencies installed

Python 3.11.9 (64-bit); pip packages: PySide6 6.12.0 (+ Addons/Essentials/
WebEngine/Pdf), NumPy 2.4.6, SciPy 1.17.1, opencv-python 4.14.0.94,
rapidocr_onnxruntime 1.4.4, onnxruntime 1.32.0, soundfile 0.14.0,
Pydantic 2.14.4, platformdirs 4.14.7, PyInstaller 6.22.3, pytest 8.4.2,
pytest-qt 4.5.0, pytest-cov 5.0.0.
FFmpeg/FFprobe: BtbN n9.0 win64 GPL shared build (includes libx264 + h264_amf)
installed to `bin/`.

## 4. Tests executed and results

- `python -m pytest -q` → **58 passed** (including 7-kill coverage, compilation planning,
  chronological ordering, overlap merging, duplicate removal, pre/post
  boundaries, FFmpeg concatenation, audio preservation, output resolution,
  integrity, temp cleanup, failed-export recovery, FFprobe metadata, validation,
  IGN normalisation/matching, OCR duplicate suppression with fake OCR, event
  scoring, grouping/ranking, clip boundaries/merging/deduplication, SQLite
  persistence, cancellation tokens, end-to-end pipeline on synthetic footage,
  FFmpeg vertical render + validation + audio preservation).
- GUI smoke tests: offscreen construction of all 7 pages, onboarding wizard and
  calibration dialog; real Windows launch with auto-quit — all succeeded.
- Real RapidOCR smoke test: read `"TESTPLAYER killed BOT"` from a synthetic
  frame with confidence 1.0.
- Real end-to-end OCR test on synthetic kill-feed video: 1 confirmed event at
  0.5 s.
- Real export verification: 1080×1920, 30 FPS, h264, AAC, 3.0 s output validated.

No PUBG-specific accuracy claim is made — no real PUBG footage was available.

## 5. Performance observations

- **Real 16.6-minute 1080p match: ~87 s end-to-end** (was 30+ minutes before
  optimisation). 500 frames extracted in ~11 s, OCR ~68 s, audio ~3 s in a
  parallel thread. Produced 4 kill-feed events and 3 candidate clips.
- RapidOCR cold initialisation ≈ 2.7 s (lazy, off the GUI thread).
- Vertical export of a 3 s 1728×1080 source to 1080×1920 H.264 ≈ 0.3–0.8 s with
  `veryfast`.
- One-pass FFmpeg frame extraction + shared frames for OCR and visual; adaptive
  sampling caps any recording at ~900 samples.
- Audio decoded in 1-second PCM chunks; memory does not scale with length.

## 6. Known bugs and limitations

- OCR accuracy depends on HUD layout, text size and compression; calibration and
  threshold tuning are required for each recording setup.
- Persistent kill-feed rows can still occasionally cause a missed or duplicate
  event when text is heavily corrupted; multi-observation confirmation reduces
  but does not eliminate this.
- The vertical preview in the editor is an approximate QImage composition, not
  a frame-accurate FFmpeg render.
- The "crop" vertical preset intentionally fills the frame and may cut the kill
  feed/minimap; blurred (default) and pillarbox avoid this.
- PyInstaller distribution bundles FFmpeg DLLs in `bin/`; GPL licence terms of
  the bundled build must be honoured when redistributing.
- Frozen build launches on this Windows 11 machine (verified), but has **not**
  been validated on a clean Windows installation without Python installed.
- One-folder distribution is ~789 MB (PySide6 WebEngine + FFmpeg DLLs); a
  smaller build can be produced by excluding unused PySide6 modules.

## 7. Exact launch command

```powershell
cd "G:\PUBG AUTOCLIPS"
.\.venv\Scripts\python.exe -m app.main
```
(Development here: `python -m app.main` from the project root.)

## 8. Exact Windows build command

```powershell
cd "G:\PUBG AUTOCLIPS"
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```
Output: `dist\PUBGAutoClips\PUBGAutoClips.exe` (built successfully; frozen app
launch verified on this machine — process stayed alive for 12 s with GUI).

## 9. Location of exported videos

Default: `G:\PUBG AUTOCLIPS\exports`
(overridable via onboarding or **Settings → Output folder**). Each export is a
separate file named `<match>_clip_<start>s_<id>.mp4`. Export records (path,
status, size) are stored in the SQLite database under
`%LOCALAPPDATA%\PUBG AutoClips`.
