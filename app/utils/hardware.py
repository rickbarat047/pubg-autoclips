"""Hardware information and processing preset helpers."""
from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class CpuInfo:
    name: str
    cores_physical: int
    cores_logical: int


@dataclass
class MemoryInfo:
    total_gb: float
    available_gb: float


@dataclass
class GpuInfo:
    name: str
    vendor: str
    vram_gb: float | None


@dataclass
class HardwareReport:
    os_name: str
    os_version: str
    architecture: str
    cpu: CpuInfo
    memory: MemoryInfo
    gpu: GpuInfo
    ffmpeg_version: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _wmi_query(prop: str) -> list[str]:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_{prop} | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0:
            return [line.strip() for line in out.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []


def get_cpu() -> CpuInfo:
    name = platform.processor() or "Unknown CPU"
    names = _wmi_query("Processor")
    if names:
        name = names[0]
    return CpuInfo(
        name=name,
        cores_physical=os.cpu_count() // 2 if os.cpu_count() else 1,
        cores_logical=os.cpu_count() or 1,
    )


def get_memory() -> MemoryInfo:
    total = available = 0.0
    try:
        import psutil  # optional
        vm = psutil.virtual_memory()
        total, available = vm.total / 1e9, vm.available / 1e9
    except Exception:
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$o=Get-CimInstance Win32_OperatingSystem; "
                 "Write-Output ($o.TotalVisibleMemorySize/1MB); "
                 "Write-Output ($o.FreePhysicalMemory/1MB)"],
                capture_output=True, text=True, timeout=15,
            )
            nums = [float(x) for x in out.stdout.split()]
            if len(nums) >= 2:
                total, available = nums[0], nums[1]
        except Exception:
            pass
    return MemoryInfo(total_gb=round(total, 1), available_gb=round(available, 1))


def get_gpu() -> GpuInfo:
    names = _wmi_query("VideoController")
    name = names[0] if names else "Not detected"
    vendor = "Unknown"
    lowered = name.lower()
    if "nvidia" in lowered:
        vendor = "NVIDIA"
    elif "amd" in lowered or "radeon" in lowered:
        vendor = "AMD"
    elif "intel" in lowered:
        vendor = "Intel"
    vram: float | None = None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object -ExpandProperty AdapterRAM"],
            capture_output=True, text=True, timeout=15,
        )
        vals = [float(x) for x in out.stdout.split() if x.strip()]
        if vals:
            vram = round(max(vals) / 1e9, 1)
    except Exception:
        pass
    return GpuInfo(name=name, vendor=vendor, vram_gb=vram)


def get_ffmpeg_version(ffmpeg_path: str | None = None) -> str | None:
    exe = ffmpeg_path or "ffmpeg"
    try:
        out = subprocess.run([exe, "-version"], capture_output=True,
                             text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.splitlines()[0]
    except Exception:
        pass
    return None


def detect_hardware(ffmpeg_path: str | None = None) -> HardwareReport:
    return HardwareReport(
        os_name=platform.system(),
        os_version=platform.version(),
        architecture=platform.machine(),
        cpu=get_cpu(),
        memory=get_memory(),
        gpu=get_gpu(),
        ffmpeg_version=get_ffmpeg_version(ffmpeg_path),
    )


def recommended_workers() -> int:
    logical = os.cpu_count() or 4
    return max(2, min(8, logical - 2))
