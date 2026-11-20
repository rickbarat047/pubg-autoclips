"""Application exception hierarchy with actionable messages."""
from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors."""
    message = "An unexpected error occurred."
    hint = ""

    def __init__(self, message: str | None = None, hint: str | None = None):
        self.detail = message or self.message
        self.hint = hint if hint is not None else self.hint
        super().__init__(self.detail)

    def user_message(self) -> str:
        if self.hint:
            return f"{self.detail}\n\n{self.hint}"
        return self.detail


class MediaError(AppError):
    message = "The media file could not be processed."
    hint = "Ensure the file is a valid MP4 recording and is not corrupted."


class InvalidVideoError(MediaError):
    message = "This file is not a valid video."
    hint = "Choose an MP4 file produced by OBS Studio."


class UnsupportedCodecError(MediaError):
    message = "The video uses an unsupported codec."
    hint = "Record with H.264 video and AAC audio in OBS Studio."


class MissingAudioStreamError(MediaError):
    message = "The recording has no audio stream."
    hint = "Audio-based detection is disabled; visual and OCR analysis still work."


class MissingFfmpegError(AppError):
    message = "FFmpeg / FFprobe was not found."
    hint = ("Install FFmpeg and place ffmpeg.exe and ffprobe.exe in the app's "
            "bin/ folder or on your PATH. See README.md.")


class OcrInitError(AppError):
    message = "The OCR engine could not be initialised."
    hint = "Check that the OCR model files are present in the models/ocr folder."


class DatabaseError(AppError):
    message = "A database error occurred."


class ExportError(AppError):
    message = "Video export failed."
    hint = "Check free disk space and that FFmpeg is installed correctly."


class InsufficientStorageError(ExportError):
    message = "There is not enough free disk space to export."


class CancelledError(AppError):
    message = "The operation was cancelled."


class ConfigError(AppError):
    message = "The application configuration is invalid."
