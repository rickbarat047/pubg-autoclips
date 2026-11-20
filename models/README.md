# OCR models

RapidOCR (via `rapidocr_onnxruntime`) ships its detection/recognition ONNX
models inside the installed Python package, so PUBG AutoClips does **not**
download models at runtime and works fully offline after installation.

PyInstaller builds use `--collect-data rapidocr_onnxruntime` to bundle those
model files. If you want to override model location, set the environment
variable `PUBG_AC_MODEL_DIR` to a directory containing your models.

Place any optional custom model files in this directory as needed. There are
no required files here for the default configuration.
