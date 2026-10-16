"""跨平台主机与 NVIDIA GPU 指标采集。"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
import time
from typing import Any

import psutil

from app.collectors.base import BaseCollector
from app.schemas.dashboard import HardwareSnapshot


def _safe_float(value: str) -> float | None:
    """将 nvidia-smi 的 N/A 安全转换为空值。"""

    cleaned = value.strip()
    if not cleaned or cleaned.upper() in {"N/A", "[N/A]"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


class HardwareCollector(BaseCollector[HardwareSnapshot]):
    """采集 CPU/RAM，并在可用时读取 NVIDIA GPU。

    GPU 子进程设置短超时，避免驱动异常拖慢整个实时循环；AMD Provider 后续可按同一
    返回结构接入，而无需修改 DashboardService。
    """

    _GPU_QUERY = (
        "name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
        "power.draw,fan.speed"
    )

    def __init__(self) -> None:
        self._cached_windows_gpu: dict[str, object] | None = None
        self._windows_gpu_cached_at = 0.0

    async def collect(self) -> HardwareSnapshot:
        """并行收集系统和 GPU 数据。"""

        memory = psutil.virtual_memory()
        frequency = psutil.cpu_freq()
        base = HardwareSnapshot(
            cpu_usage=round(psutil.cpu_percent(interval=None), 1),
            cpu_frequency_mhz=round(frequency.current, 0) if frequency else 0.0,
            ram_used_gb=round((memory.total - memory.available) / 1024**3, 1),
            ram_total_gb=round(memory.total / 1024**3, 1),
            uptime_seconds=max(0, int(time.time() - psutil.boot_time())),
        )

        gpu = await self._collect_nvidia()
        if gpu is None and sys.platform == "win32":
            gpu = await self._collect_windows_gpu()
        return base.model_copy(update=gpu) if gpu else base

    async def _collect_nvidia(self) -> dict[str, object] | None:
        """使用系统自带 nvidia-smi 读取首张 GPU，不要求额外 Python SDK。"""

        try:
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                f"--query-gpu={self._GPU_QUERY}",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=1.5)
        except (FileNotFoundError, TimeoutError, OSError):
            return None

        if process.returncode != 0 or not stdout:
            return None

        row = next(csv.reader(io.StringIO(stdout.decode(errors="replace"))), None)
        if not row or len(row) < 7:
            return None

        gpu_usage = _safe_float(row[1]) or 0.0
        vram_used = (_safe_float(row[2]) or 0.0) / 1024
        vram_total = (_safe_float(row[3]) or 0.0) / 1024
        return {
            "gpu_available": True,
            "gpu_name": row[0].strip(),
            "gpu_usage": round(gpu_usage, 1),
            "vram_used_gb": round(vram_used, 1),
            "vram_total_gb": round(vram_total, 1),
            "gpu_temperature_c": _safe_float(row[4]),
            "gpu_power_w": _safe_float(row[5]),
            "gpu_fan_percent": _safe_float(row[6]),
        }

    async def _collect_windows_gpu(self) -> dict[str, object] | None:
        """通过 Windows 性能计数器读取 AMD/Intel 等非 NVIDIA GPU。

        PowerShell 冷启动相对昂贵，因此结果缓存 10 秒。温度、功耗等 Windows
        没有稳定公共计数器的字段保持为空，避免将估算值伪装成硬件读数。
        """

        now = time.monotonic()
        if self._cached_windows_gpu and now - self._windows_gpu_cached_at < 10:
            return self._cached_windows_gpu

        script = r"""
$ErrorActionPreference = 'Stop'
$memorySamples = (Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples
$best = $memorySamples | Sort-Object CookedValue -Descending | Select-Object -First 1
if (-not $best) { exit 1 }
$match = [regex]::Match($best.InstanceName, 'luid_0x[0-9a-f]+_0x[0-9a-f]+_phys_\d+')
$luid = $match.Value
$usage = 0
if ($luid) {
  $engineSamples = (Get-Counter '\GPU Engine(*)\Utilization Percentage').CounterSamples |
    Where-Object { $_.InstanceName -like "*$luid*" }
  $usage = [Math]::Min(100, (($engineSamples | Measure-Object CookedValue -Sum).Sum))
}
$total = Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Video' -ErrorAction SilentlyContinue |
  ForEach-Object { Get-ChildItem $_.PSPath -ErrorAction SilentlyContinue } |
  ForEach-Object { (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).'HardwareInformation.qwMemorySize' } |
  Measure-Object -Maximum | Select-Object -ExpandProperty Maximum
$adapter = Get-CimInstance Win32_VideoController |
  Where-Object Name -Match 'AMD|NVIDIA|Intel|Arc|Radeon|GeForce' |
  Sort-Object AdapterRAM -Descending | Select-Object -First 1
[pscustomobject]@{
  name = if ($adapter) { $adapter.Name } else { 'Windows GPU' }
  usage = [Math]::Round($usage, 1)
  vram_used = [Math]::Round($best.CookedValue / 1GB, 1)
  vram_total = if ($total) { [Math]::Round($total / 1GB, 1) } else { 0 }
} | ConvertTo-Json -Compress
"""

        try:
            process = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
            payload: dict[str, Any] = json.loads(stdout.decode(errors="replace"))
        except (
            FileNotFoundError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):
            return self._cached_windows_gpu

        if process.returncode != 0:
            return self._cached_windows_gpu

        self._cached_windows_gpu = {
            "gpu_available": True,
            "gpu_name": str(payload.get("name") or "Windows GPU"),
            "gpu_usage": float(payload.get("usage") or 0),
            "vram_used_gb": float(payload.get("vram_used") or 0),
            "vram_total_gb": float(payload.get("vram_total") or 0),
        }
        self._windows_gpu_cached_at = time.monotonic()
        return self._cached_windows_gpu
