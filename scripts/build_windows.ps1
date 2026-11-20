<#
    PUBG AutoClips - Windows PyInstaller build
    Run from the project root:  powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { $venvPy = 'python' }
Write-Host "=== Building PUBG AutoClips ===" -ForegroundColor Green

$dist = Join-Path $root 'dist'
$build = Join-Path $root 'build'
Remove-Item $dist -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $build -Recurse -Force -ErrorAction SilentlyContinue

$separator = [System.IO.Path]::PathSeparator
$pyiArgs = [System.Collections.Generic.List[string]]::new()
$pyiArgs.Add('--noconfirm')
$pyiArgs.Add('--clean')
$pyiArgs.Add('--windowed')
$pyiArgs.Add('--onedir')
$pyiArgs.Add('--name')
$pyiArgs.Add('PUBGAutoClips')

# Bundled resources
$pyiArgs.Add('--add-data')
$pyiArgs.Add((Join-Path $root 'assets') + $separator + 'assets')
$binDir = Join-Path $root 'bin'
if (Test-Path $binDir) {
    $pyiArgs.Add('--add-data')
    $pyiArgs.Add($binDir + $separator + 'bin')
}
$modelsDir = Join-Path $root 'models'
if (Test-Path $modelsDir) {
    $pyiArgs.Add('--add-data')
    $pyiArgs.Add($modelsDir + $separator + 'models')
}
$pyiArgs.Add('--collect-data')
$pyiArgs.Add('rapidocr_onnxruntime')

foreach ($mod in @(
    'rapidocr_onnxruntime', 'onnxruntime', 'scipy.stats', 'soundfile',
    'PySide6.QtCore', 'PySide6.QtWidgets', 'PySide6.QtGui'
)) {
    $pyiArgs.Add('--hidden-import')
    $pyiArgs.Add($mod)
}
$pyiArgs.Add('--collect-submodules')
$pyiArgs.Add('app')
$pyiArgs.Add('app/main.py')

Write-Host "Running PyInstaller..." -ForegroundColor Cyan
& $venvPy -m PyInstaller $pyiArgs.ToArray()
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit $LASTEXITCODE)." }

$outDir = Join-Path $dist 'PUBGAutoClips'
Copy-Item (Join-Path $root 'README.md') (Join-Path $outDir 'README.txt') -Force
$lic = @"
FFmpeg / FFprobe licensing notice
=================================
If ffmpeg.exe and ffprobe.exe were copied into bin/, their license depends on the
build. BtbN "GPL shared" builds are GPL 2 or later; gyan.dev "essentials" builds
are LGPL 2.1+. You must comply with the applicable licence when redistributing.
The bundled build used here is GPL (includes libx264), so GPL terms apply.
See README.md for details.
"@
$lic | Out-File -FilePath (Join-Path $outDir 'FFMPEG-LICENSE.txt') -Encoding utf8

Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "Executable: $outDir\PUBGAutoClips.exe"
Write-Host "NOTE: This build has NOT been verified on a clean Windows install."
