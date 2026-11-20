---
name: pubg-performance-optimisation
description: CPU-first performance and resource management for PUBG AutoClips on the target machine (Intel i5-12400F, AMD RX 6500 XT 4GB, 16GB RAM, Windows 11). Use when optimising analysis/export speed, memory use, background workers, sampling intervals or Windows resource handling.
---

# PUBG Performance Optimisation (project-specific)

## Target hardware

- CPU: Intel Core i5-12400F (6 cores / 12 threads) — **all inference is CPU**
- GPU: AMD Radeon RX 6500 XT 4 GB — no CUDA, no NVIDIA requirements
- RAM: 16 GB DDR4
- Storage: NVMe SSD + 2 TB HDD; source recordings up to ~2 GB, 25–40 min typical
- OS: Windows 11 64-bit

## Measured baselines (do not regress)

| Scenario | Before | After |
|---|---|---|
| 16.6 min / 1080p full analysis | >30 min | **~87–102 s** |
| Frame extraction (500 frames) | ~60 s of seeks | **~11 s** (one FFmpeg pass) |
| RapidOCR per kill-feed crop | ~1.6 s | **~0.26 s** |
| 3 s clip → vertical 1080x1920 export | — | ~0.3–0.8 s |

## Rules

1. **Decode once.** Extract sampled frames with FFmpeg `fps=1/N` in a single pass; share the same
   frames between OCR and visual analysis. See `app/media/frame_extractor.py`.
2. **Never load the full video into RAM.** Keep only sampled frames (bounded ~500–900) in memory;
   stream audio as 1 s PCM chunks via `ffmpeg -f s16le`.
3. **Adaptive sampling.** `interval = max(configured_interval, duration / 900)` caps any recording
   at ~900 samples regardless of length. Presets: Fast 3 s, Balanced 2 s, Accurate 1 s.
4. **Fast OCR config.** `limit_side_len=736`, `limit_type='max'`, `use_cls=False`, no upscaling,
   no CLAHE. Parallel OCR engines were tested and did **not** help (CPU already saturated).
5. **Background workers only.** All long tasks run in QThreads (`app/workers/*`). GUI must never
   block. Use `CancellationToken` for cancel/pause/resume.
6. **Keep QObject workers alive** — this was a real production bug: a locally-created
   `AnalysisWorker` was garbage-collected before `QThread.start()`, so the job stayed at
   "starting" forever with zero clips. Store worker references on `MainWindow`
   (`_analysis_worker`, `_export_worker`).
7. **Cache / reuse.** Thumbnails are cached in `app_cache_dir()/thumbnails`; results are persisted
   to SQLite so re-export does not require re-analysis.
8. **Temporary files.** Frame extraction uses a temp directory that is removed after analysis;
   never leave unpacked frames behind.

## Windows considerations

- Always use argv-list subprocess calls; never `shell=True`. Paths contain spaces
  (`G:\PUBG AUTOCLIPS`, `C:\Users\...\AppData\Local\...`).
- ffmpeg/ffprobe resolution order: settings override → PATH → bundled `bin/`.
- Hardware encoding is optional: check `h264_amf` availability before offering it; CPU
  `libx264` is the reliable default. AMD GPU is not used for inference.
- Logs are rotating files in `%LOCALAPPDATA%\PUBG AutoClips\PUBG AutoClips\Logs`.

## Verification

- `pytest -q` (whole suite) and a timed run on a real recording.
- Watch analysis progress stages: Frames → Audio → OCR+Visual → Scoring → Clips.
- If analysis takes many minutes again, check sampling interval, OCR preprocessing, and that
  frame extraction is succeeding (look for "Extracted N frames in one pass" in the log).
