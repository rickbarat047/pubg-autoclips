---
name: pubg-killfeed-ocr
description: Specialised knowledge for PUBG kill-feed recognition in PUBG AutoClips. Use when working on kill-feed calibration, IGN matching, RapidOCR preprocessing, duplicate suppression, confidence scoring, event timestamps or OCR accuracy validation. Project IGN is rickbarat; recordings are 1728x1080/30fps; OCR is RapidOCR + ONNX Runtime on CPU.
---

# PUBG Kill-Feed OCR (project-specific)

## Fixed project facts

- Player IGN: **rickbarat**
- Source gameplay: **1728x1080, 30 FPS** (OBS MP4; some recordings are 1920x1080)
- OCR: **RapidOCR 1.4.x + ONNX Runtime, CPU only** (PP-OCRv4 det/rec bundled in the package)
- Kill-feed region: stored as **normalised coordinates** in `AppSettings.calibration`
- Exports: `G:\PUBG AUTOCLIPS\exports`

## Relevant modules

| Concern | Module |
|---|---|
| OCR engine + preprocessing | `app/detection/kill_feed/ocr_engine.py` |
| Detection loop, confirmation, dedup | `app/detection/kill_feed/feed_detector.py` |
| Text normalisation + IGN matching | `app/detection/kill_feed/ign_matcher.py` |
| Rectangle calibration helpers | `app/detection/kill_feed/calibration.py` |
| UI calibration dialog | `app/ui/calibration_dialog.py` |
| Frame source (fast path) | `app/media/frame_extractor.py` |

## Calibration rules

- Never hardcode a pixel region. Store `(x, y, w, h)` normalised to `[0, 1]`; convert with
  `NormalizedRegion.to_pixels(width, height)`.
- Default region `x=0.68, y=0.02, w=0.31, h=0.28` is a starting point only. It worked for the
  verified 1920x1080 recording because PUBG's kill feed sits top-right under the "ALIVE" counter.
- Let the user draw the rectangle on a screenshot, preview the crop, run an OCR test, then confirm.
- The same normalised region must work at 1728x1080 and 1920x1080.

## OCR performance settings (already applied — do not regress)

- `RapidOCR.text_det.limit_side_len = 736`, `limit_type = "max"`:
  the library default upscales small crops to a 736px **min** side, which made each crop take
  ~1.6 s on CPU. Max-side keeps 1080p crops native (~0.26 s).
- Call `engine(crop, use_cls=False)` — HUD text is upright; the orientation classifier is wasted work.
- Do **not** upscale 2x or run CLAHE in `OcrEngine.preprocess`; that was the original bottleneck.
- Frames come from a single FFmpeg `fps=1/N` extraction pass, shared with visual analysis.

## Matching rules

1. Normalise both OCR text and IGN: case-fold, strip decorations (`[](){}<>-_|:,.` etc.),
   map common OCR confusions (`0→o`, `1→l`, `5→s`, `8→b`, `4→a`, `2→z`, `7→t`, …).
2. `ign_match_score()` returns 1.0 for exact token, 0.95 when the IGN appears inside a line.
   Confirmed threshold is 0.82; 0.45–0.82 is "possible"/uncertain.
3. Guard short tokens: substring matching is only valid for tokens of length
   `>= max(3, len(ign)//2)`, otherwise single letters like "a" look like a match.
4. Real example that must match:
   `"1KILLED OASSISTED 82 ALIVE ... 23[NTRS]rickbaratTX[2K] SkrillexArea27"` → score 0.95.

## Confirmation and deduplication (critical)

- The kill feed persists for several seconds and the region also contains a changing
  alive-counter and compass. **Never use the whole OCR line as a dedup signature** — it changes
  every sample, so no entry ever reaches the required consecutive observations and **zero events
  are produced**.
- Key confirmation on the stable IGN (`normalize_text(ign)`) with a time cooldown
  (`kill_feed.duplicate_window_sec`, default 10 s). Require `min_observations` (default 2)
  consecutive sightings; a sampling gap > `2 * interval` resets the run.
- Keep `source`, `ocr_confidence`, `recognised_text`, `observations` and `evidence` on every event.

## Kill vs knock honesty

- OCR alone cannot reliably distinguish kills from knocks. Only label a knock when the feed text
  itself contains a knock indicator (`knocked`, `knock`, `down`, `dbno`, `bleeding`).
- Categories: `confirmed`, `knock`, `uncertain`, `possible`. Never upgrade "possible" to a kill
  without additional evidence.

## Validation checklist

- `pytest tests/test_feed_detector.py tests/test_ign_matcher.py tests/test_pipeline.py`
- Regression test `test_changing_hud_text_does_not_block_confirmation` must pass.
- With synthetic frames containing `TESTPLAYER killed BOT`, expect one confirmed event at the
  correct timestamp.
- On the verified 999 s recording, expect ~4–5 feed events and ~3 clips in ~90 s.
