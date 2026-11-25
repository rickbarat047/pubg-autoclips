"""Validated application configuration (Pydantic v2)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .utils.paths import default_output_folder, settings_path

PresetName = Literal["fast", "balanced", "accurate"]
LayoutName = Literal["blurred", "crop", "pillarbox", "original"]
ExportMode = Literal["compilation", "separate"]


class NormalizedRegion(BaseModel):
    """Kill-feed rectangle in normalised [0,1] coordinates."""
    x: float = Field(0.68, ge=0.0, le=1.0)
    y: float = Field(0.02, ge=0.0, le=1.0)
    w: float = Field(0.31, ge=0.001, le=1.0)
    h: float = Field(0.28, ge=0.001, le=1.0)

    @model_validator(mode="after")
    def within_bounds(self) -> "NormalizedRegion":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError("Kill-feed region exceeds the frame bounds")
        return self

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        x = int(round(self.x * width))
        y = int(round(self.y * height))
        w = int(round(self.w * width))
        h = int(round(self.h * height))
        return x, y, max(1, w), max(1, h)


class KillFeedSettings(BaseModel):
    sample_interval_sec: float = Field(2.0, gt=0.0, le=30.0)
    confidence_threshold: float = Field(0.45, ge=0.0, le=1.0)
    min_observations: int = Field(1, ge=1, le=10)
    duplicate_window_sec: float = Field(10.0, ge=0.0, le=60.0)
    enabled: bool = True


class AudioSettings(BaseModel):
    enabled: bool = True
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    analysis_window_sec: float = Field(0.5, gt=0.0, le=5.0)
    enabled_chunk_cache: bool = True


class VisualSettings(BaseModel):
    enabled: bool = True
    sample_interval_sec: float = Field(2.0, gt=0.0, le=10.0)
    motion_threshold: float = Field(0.5, ge=0.0, le=1.0)
    scene_change_threshold: float = Field(0.35, ge=0.0, le=1.0)


class ScoringWeights(BaseModel):
    confirmed_kill: float = 40.0
    multi_kill_bonus: float = 15.0
    audio_intensity: float = 15.0
    visual_activity: float = 10.0
    sustained_combat: float = 10.0
    scene_context: float = 5.0
    uncertainty_penalty: float = 20.0
    min_event_score: float = Field(25.0, ge=0.0)


class ClipSettings(BaseModel):
    min_duration_sec: float = Field(20.0, ge=5.0)
    max_duration_sec: float = Field(60.0, ge=10.0)
    pre_event_sec: float = Field(8.0, ge=0.0)
    post_event_sec: float = Field(12.0, ge=0.0)
    max_clips_per_match: int = Field(12, ge=1, le=100)
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    merge_gap_sec: float = Field(4.0, ge=0.0, le=30.0)

    @model_validator(mode="after")
    def check_durations(self) -> "ClipSettings":
        if self.min_duration_sec > self.max_duration_sec:
            raise ValueError("Minimum duration cannot exceed maximum duration")
        return self


class CompilationSettings(BaseModel):
    """Settings for the single highlight compilation export mode."""

    pre_event_sec: float = Field(10.0, ge=0.0, le=120.0)
    post_event_sec: float = Field(5.0, ge=0.0, le=120.0)
    min_segment_sec: float = Field(10.0, ge=3.0, le=120.0)
    max_segment_sec: float = Field(30.0, ge=5.0, le=300.0)
    merge_gap_sec: float = Field(6.0, ge=0.0, le=30.0)
    max_segments: int = Field(12, ge=1, le=50)
    order_by_score: bool = False  # chronological by default
    audio_fade_sec: float = Field(0.15, ge=0.0, le=1.0)
    # Minimum confidence for non-kill events (audio-only / visual-only noise
    # is excluded unless it is strong).
    min_support_confidence: float = Field(0.55, ge=0.0, le=1.0)
    min_support_score: float = Field(35.0, ge=0.0)

    @model_validator(mode="after")
    def check_bounds(self) -> "CompilationSettings":
        if self.min_segment_sec > self.max_segment_sec:
            raise ValueError("Minimum segment cannot exceed maximum segment")
        return self


class RenderSettings(BaseModel):
    layout: LayoutName = "blurred"
    width: int = Field(1080, ge=320)
    height: int = Field(1920, ge=320)
    fps: int = Field(30, ge=15, le=60)
    crf: int = Field(21, ge=17, le=28)
    preset: Literal["ultrafast", "veryfast", "faster", "fast", "medium", "slow"] = "veryfast"
    audio_bitrate_kbps: int = Field(192, ge=64, le=320)
    hardware_encoding: bool = False
    hw_encoder: str = "h264_amf"


class ProcessingSettings(BaseModel):
    preset: PresetName = "balanced"
    max_workers: int = Field(4, ge=1, le=16)
    ocr_device: str = "cpu"


class AppSettings(BaseModel):
    """Top-level persistent settings."""
    version: int = 6
    onboarding_complete: bool = False
    ign: str = ""
    output_folder: str = Field(default_factory=default_output_folder)
    export_mode: ExportMode = "compilation"
    auto_export: bool = False
    auto_export_max_clips: int = Field(5, ge=1, le=20)
    compilation: CompilationSettings = Field(default_factory=CompilationSettings)
    calibration: NormalizedRegion = Field(default_factory=NormalizedRegion)
    calibration_source_resolution: str = ""
    kill_feed: KillFeedSettings = Field(default_factory=KillFeedSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    visual: VisualSettings = Field(default_factory=VisualSettings)
    scoring: ScoringWeights = Field(default_factory=ScoringWeights)
    clips: ClipSettings = Field(default_factory=ClipSettings)
    render: RenderSettings = Field(default_factory=RenderSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    ffmpeg_path: str = ""
    ffprobe_path: str = ""

    @field_validator("ign", mode="before")
    @classmethod
    def strip_ign(cls, v: object) -> str:
        return str(v).strip() if v is not None else ""

    def apply_preset(self, name: PresetName | None = None) -> None:
        """Set the active preset name without overwriting manual detection values.

        Detection intervals/thresholds are independently editable in Settings,
        so applying a preset on every save must not silently revert them.
        """
        name = name or self.processing.preset
        self.processing.preset = name

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        path = path or settings_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            settings = cls.model_validate(data)
            # Older configurations had no default export folder; migrate them.
            if not settings.output_folder:
                settings.output_folder = default_output_folder()
            if settings.version < 2:
                # v1 sampled far too often for CPU-only OCR (30+ min/match).
                settings.apply_preset("balanced")
                settings.kill_feed.duplicate_window_sec = 10.0
                settings.version = 2
            if settings.version < 3:
                # v2 exported every highlight separately; v3 defaults to one
                # compiled highlight video. Existing preferences are kept.
                settings.version = 3
            if settings.version < 4:
                # Two observations at 2 s sampling missed briefly-visible feed
                # rows (missing kills). Per-row signatures now guard against
                # duplicates, so one observation is sufficient.
                if settings.kill_feed.min_observations == 2:
                    settings.kill_feed.min_observations = 1
                settings.version = 4
            if settings.version < 5:
                # Collapse duplicate detections of the same feed row into one
                # clip segment instead of rendering near-identical sections.
                if settings.compilation.merge_gap_sec == 2.0:
                    settings.compilation.merge_gap_sec = 6.0
                settings.version = 5
            if settings.version < 6:
                # Review-before-export is the new default. Pydantic has already
                # applied the new False default when `auto_export` was absent
                # from the JSON, and preserved an explicit True if the user
                # chose it. Only the schema version needs advancing.
                settings.version = 6
            return settings
        except Exception:
            # Corrupt settings must never prevent startup.
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)


# Alias used across the codebase.
Settings = AppSettings
