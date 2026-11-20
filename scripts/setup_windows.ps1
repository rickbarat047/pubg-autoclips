<#
    PUBG AutoClips - Windows development setup
    Run from the project root:  powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "=== PUBG AutoClips setup ===" -ForegroundColor Green

# 1. Python version check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    throw "Python 3.11 (64-bit) not found on PATH. Install from https://www.python.org/downloads/release/python-3119/"
}
$ver = & python -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
Write-Host "Found Python $ver"
if (-not $ver.StartsWith('3.11')) {
    Write-Warning "Python 3.11 is recommended. Found $ver - continuing."
}
$bits = & python -c "import struct;print(struct.calcsize('P')*8)"
if ($bits -ne '64') { throw "64-bit Python is required (found $bits-bit)." }

# 2. Virtual environment
if (-not (Test-Path '.venv')) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
& $venvPy -m pip install --upgrade pip setuptools wheel

# 3. Dependencies
Write-Host "Installing dependencies (this may take several minutes)..." -ForegroundColor Cyan
& $venvPy -m pip install -r requirements-dev.txt

# 4. FFmpeg / FFprobe check
Write-Host "Checking FFmpeg..." -ForegroundColor Cyan
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
$fp = Get-Command ffprobe -ErrorAction SilentlyContinue
$localFF = Join-Path $root 'bin\ffmpeg.exe'
$localFP = Join-Path $root 'bin\ffprobe.exe'
if ((-not $ff) -and (-not (Test-Path $localFF))) {
    Write-Warning "FFmpeg not found. Download an LGPL/GPL build (see README.md) and place ffmpeg.exe and ffprobe.exe in .\bin"
} else {
    Write-Host "FFmpeg available." -ForegroundColor Green
}

# 5. OCR model verification (RapidOCR bundles its ONNX models)
Write-Host "Verifying OCR engine..." -ForegroundColor Cyan
& $venvPy -c "from rapidocr_onnxruntime import RapidOCR; e=RapidOCR(); print('RapidOCR OK')"
if ($LASTEXITCODE -ne 0) { throw "RapidOCR initialisation failed." }

# 6. Basic application check
Write-Host "Running basic import check..." -ForegroundColor Cyan
& $venvPy -c "import app.main; import app.ui.main_window; print('Application imports OK')"
if ($LASTEXITCODE -ne 0) { throw "Application import check failed." }

Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "Launch with:  .\.venv\Scripts\python.exe -m app.main"
