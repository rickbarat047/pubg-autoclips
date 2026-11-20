# FFmpeg binaries

This folder is intentionally empty in the Git repository.

PUBG AutoClips requires `ffmpeg.exe` and `ffprobe.exe` to analyse audio, extract
frames and render vertical clips. Download a Windows build and place both
executables (plus any DLL files for "shared" builds) in this folder.

- GitHub builds: https://github.com/BtbN/FFmpeg-Builds/releases
- gyan.dev builds: https://www.gyan.dev/ffmpeg/builds/

The build used during development was BtbN `win64-gpl-shared` (GPL 2+), which
includes `libx264` and `h264_amf`. Redistributing these binaries requires
compliance with the applicable FFmpeg licence — see the root README.md.
