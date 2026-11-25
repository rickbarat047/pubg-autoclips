# PUBG AutoClips â€” Completion Report

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
    chunks â€” never loads the full track into RAM.
  - OpenCV motion + scene-change analysis at configurable sampling intervals.
  - Weighted, explainable event scoring with per-signal evidence breakdown.
  - Multi-kill / clutch-*candidate* grouping (no fabricated 1vX labels).
  - Clip selection with pre/post-roll, 20â€“60 s bounds, overlap merging and
    duplicate removal.
  - Pause/resume and cancel via cancellation tokens.
- **UI**: Single-window editor workspace â€” one premium dark-charcoal/lime
  window matching the reference design: top bar (brand, clip search, Import /
  Settings / About / Calibrate, lime EXPORT), left Assets panel (Media/Clips
  tabs with background-worker thumbnails and search), centre Preview with real
  playback + timecode, right Inspector (editable clip start/end, Add/Split/
  Remove), bottom full-match Timeline (ruler, coloured clip track, draggable
  lime playhead, drag-to-add manual ranges). A result card (Play / Open Folder /
  Back) appears after export. Settings/About/Calibration open as dialogs. All
  colours derive from a central token module; every visible button is wired to
  a real function. The former multi-page sidebar workflow is gone from the
  visible UI (page modules remain as hidden workflow helpers).
- **Rendering/export**: FFmpeg vertical layouts (blurred background default,
  crop, pillarbox, original-aspect), 1080Ã—1920/30 FPS/H.264/AAC, original
  gameplay audio preserved, path-with-spaces safe, encoder capability detection
  (libx264 â†’ libopenh264 â†’ mpeg4 fallback; AMF only when available), output
  validation, exports recorded in DB.
- **Single Highlight Compilation (default)**: one match â†’ one MP4. Smart
  pre/post boundaries (10/5 s, 10â€“30 s segments), overlap/short-gap merging,
  confirmed-kill prioritisation, chronological ordering (optional by score),
  short audio fades, stream-copy concat with re-encode fallback, full output
  verification and temp cleanup. Separate individual clips remain an optional
  mode. Review & Export page with stats, full-match player, timeline,
  editable segments, drag-to-add manual ranges, preview, Open Folder and Play
  Video actions. Exported Clips page lists finished videos with Play and
  Open Folder.
- **Services named in the spec**: `ProjectManager`, `JobManager`, `TaskQueue`,
  `EventBus`, `DatabaseManager`, `MediaProbe`, `AnalysisPipeline`,
  `HighlightScoringEngine` (alias of `EventScorer`), `ClipSelector`,
  `VideoRenderer`, `ExportManager`.
- **Packaging scripts**: `scripts/setup_windows.ps1`, `scripts/build_windows.ps1`
  with FFmpeg licence notice generation.

## 2. Features not implemented

- Verified kill-vs-knock classification from OCR alone (deliberately avoided â€”
  feed text rarely distinguishes them reliably).
- Verified clutch (1v2/1v3/1v4) labels â€” only "CLUTCH_CANDIDATE" is produced,
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

- `python -m pytest -q` â†’ **132 passed** (including 7-kill coverage, compilation planning,
  chronological ordering, overlap merging, duplicate removal, pre/post
  boundaries, FFmpeg concatenation, audio preservation, output resolution,
  integrity, temp cleanup, failed-export recovery, FFprobe metadata, validation,
  IGN normalisation/matching, OCR duplicate suppression with fake OCR, event
  scoring, grouping/ranking, clip boundaries/merging/deduplication, SQLite
  persistence, cancellation tokens, end-to-end pipeline on synthetic footage,
  FFmpeg vertical render + validation + audio preservation, 9 missed-knock
  regression tests, and the single-window editor suite: design tokens, cancellation
  integrity, core bug fixes, editor shell, assets panel, preview panel, inspector/
  timeline with pixelâ†’time drag mapping, export workflow/dialogs, shared-widget
  fixes and colour sweep).
- GUI smoke tests: offscreen construction of the single-window editor shell and
  all five regions, hidden workflow pages, onboarding wizard and calibration
  dialog; real Windows launch with auto-quit â€” all succeeded.
- Known test-process note: after all tests report passing, the Windows pytest
  process can exit with a native code (0xC0000409/0xC0000005) during DLL
  teardown (Qt-multimedia + ONNX Runtime + NumPy). This happens after the suite
  completes with no Python frame and does not reflect a test or product failure.
- Real RapidOCR smoke test: read `"TESTPLAYER killed BOT"` from a synthetic
  frame with confidence 1.0.
- Real end-to-end OCR test on synthetic kill-feed video: 1 confirmed event at
  0.5 s.
- Real export verification: 1080Ã—1920, 30 FPS, h264, AAC, 3.0 s output validated.

- **Real-footage verification (2026-11-24)**: re-analysed the 26.6-minute real
  PUBG recording with the fixes: kill-feed events increased 13 â†’ 16, new events
  at ~866/872/952/958 s, per-row OCR confidence 0.65â€“0.85. End-to-end compilation
  of 10 segments covered 11/11 feed events; output verified 1080Ã—1920, 30 FPS,
  H.264/AAC, 167 s, 5010 frames, 121 MB with a clean full decode (0 errors).
- **Manual-range verification (2026-11-24)**: a missed-moment range added on the
  Review & Export page (700â€“720 s) was persisted in SQLite across a fresh DB
  connection, appeared in the segment list labelled "Added by you", and was
  included in an 11-segment compilation. Output verified 1080Ã—1920, 30 FPS,
  H.264/AAC, 187 s, 5610 frames with a clean full decode (0 errors).
- **Single-editor workflow verification (2026-11-25)**: the editor's timeline
  drag-to-add path persisted a manual 700â€“720 s range, `CompilePage.set_match`
  loaded it as a labelled MANUAL segment, and the compilation builder produced
  an 11-segment MP4 in 92 s. Verified 1080Ã—1920, 30 FPS, H.264/AAC, 187 s,
  5610 frames with a clean full decode; manual row and temp files cleaned up.

No PUBG-specific accuracy claim is made: kill vs knock is distinguished by feed
icons rather than text, so events are reported with confidence and evidence
rather than as verified knock labels.

## 5. Performance observations

- **Real 26.6-minute 1080p match with full OCR: ~544 s end-to-end** (799 sampled
  frames under default Balanced 2 s settings). Earlier ~87 s measurements used
  a now-removed fast path that skipped most OCR. This is the honest cost of
  reading every feed row; the Accurate preset (1 s) will be slower.
- RapidOCR cold initialisation â‰ˆ 2.7 s (lazy, off the GUI thread).
- Vertical export of a 3 s 1728Ã—1080 source to 1080Ã—1920 H.264 â‰ˆ 0.3â€“0.8 s with
  `veryfast`.
- One-pass FFmpeg frame extraction + shared frames for OCR and visual; adaptive
  sampling uses the finer of the OCR/visual intervals and caps any recording at
  ~1800 samples.
- End-to-end compilation of 10 segments (10Ã— FFmpeg render + stream-copy concat)
  completed in ~85 s for a 167 s output.
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
- DPI scaling (100/125/150%) was not exercised on a real display; layout uses
  Qt stretch/minimum sizes and a scrollable report area but per-DPI visual
  verification remains outstanding.
- The Windows pytest process can exit with a native code during DLL teardown
  after the suite fully passes (no Python frame); all 132 tests pass every run.

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
launch verified on this machine â€” process stayed alive for 12 s with GUI).

## 9. Location of exported videos

Default: `G:\PUBG AUTOCLIPS\exports`
(overridable via onboarding or **Settings â†’ Output folder**). Each export is a
separate file named `<match>_clip_<start>s_<id>.mp4`. Export records (path,
status, size) are stored in the SQLite database under
`%LOCALAPPDATA%\PUBG AutoClips`.

