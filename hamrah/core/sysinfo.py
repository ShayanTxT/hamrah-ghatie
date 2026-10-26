"""مرحلهٔ ۴ — سنجش سختافزار و پیشنهاد مدل زبانی مناسب."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SystemInfo:
    os_name: str = ""
    cpu: str = ""
    cores: int = 0
    ram_gb: float = 0.0
    gpu: str = ""
    vram_gb: float = 0.0
    has_nvidia: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "os": self.os_name, "cpu": self.cpu, "cores": self.cores,
            "ram_gb": round(self.ram_gb, 1), "gpu": self.gpu,
            "vram_gb": round(self.vram_gb, 1), "has_nvidia": self.has_nvidia,
        }

    def summary_fa(self) -> str:
        from .persian import to_persian_digits
        gpu = f"، کارت گرافیک {self.gpu} ({self.vram_gb:.0f} گیگ)" if self.vram_gb else "، بدون کارت گرافیک مجزا"
        return to_persian_digits(
            f"پردازنده {self.cores} هستهای، رم {self.ram_gb:.0f} گیگ{gpu}"
        )


@dataclass
class ModelProfile:
    key: str
    name: str
    filename: str
    url: str
    size_gb: float
    min_ram_gb: float
    min_vram_gb: float
    ctx: int
    gpu_layers: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "name": self.name, "filename": self.filename,
            "url": self.url, "size_gb": self.size_gb, "min_ram_gb": self.min_ram_gb,
            "min_vram_gb": self.min_vram_gb, "ctx": self.ctx,
            "gpu_layers": self.gpu_layers, "note": self.note,
        }


# اندازهها بر حسب بایت واقعی فایلها (از API مدلها گرفته شده):
# 3B = 1,929,903,264 | 7B = 4,683,074,240 | 14B = 8,988,110,976 بایت
PROFILES: dict[str, ModelProfile] = {
    "light": ModelProfile(
        key="light", name="Qwen2.5-3B-Instruct (Q4_K_M)",
        filename="Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        url="https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        size_gb=1.9, min_ram_gb=8, min_vram_gb=0, ctx=4096, gpu_layers=0,
        note="سبک و سریع؛ مناسب کامپیوتر متوسط بدون کارت گرافیک. فارسی قابل قبول.",
    ),
    "balanced": ModelProfile(
        key="balanced", name="Qwen2.5-7B-Instruct (Q4_K_M)",
        filename="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        url="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        size_gb=4.7, min_ram_gb=16, min_vram_gb=6, ctx=4096, gpu_layers=99,
        note="پیشنهاد اصلی برای سیستمهای ۱۶ گیگ به بالا یا کارت گرافیک ۶+ گیگ؛ کیفیت فارسی خیلی بهتر.",
    ),
    "quality": ModelProfile(
        key="quality", name="Qwen2.5-14B-Instruct (Q4_K_M)",
        filename="Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        url="https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        size_gb=9.0, min_ram_gb=32, min_vram_gb=8, ctx=4096, gpu_layers=40,
        note="کیفیت بالا؛ با ۸ گیگ VRAM فقط نیمی از لایهها روی GPU میرود و سرعت کمتر است.",
    ),
}


def _run(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        return (out.stdout or b"").decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def detect_gpu() -> tuple[str, float, bool]:
    """(نام کارت، حجم VRAM به گیگ، آیا NVIDIA است) — بدون نیاز به کتابخانهای اضافه."""
    name, vram, nvidia = "", 0.0, False
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if out:
        first = out.splitlines()[0]
        parts = [p.strip() for p in first.split(",")]
        name = parts[0] if parts else ""
        try:
            vram = float(parts[1]) / 1024.0 if len(parts) > 1 else 0.0
        except ValueError:
            vram = 0.0
        nvidia = True
        return name, vram, nvidia
    if platform.system() == "Windows":
        out = _run([
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "$g = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notlike '*Microsoft*' } "
            "| Select-Object -First 1; if ($g) { \"$($g.Name)|$([math]::Round($g.AdapterRAM/1GB,1))\" }",
        ], timeout=8.0)
        if "|" in out:
            name, _, size = out.partition("|")
            try:
                vram = float(size.strip())
            except ValueError:
                vram = 0.0
            # AdapterRAM در WMI محدود به ۴ گیگ است؛ مقادیر کمتر معتبرند
            if vram >= 4:
                vram = 0.0
            nvidia = "nvidia" in name.lower()
    elif platform.system() == "Linux":
        try:
            for line in Path("/proc/driver/nvidia/gpus").glob("*/information"):
                name = line.read_text(errors="ignore").split("Model:")[-1].strip().splitlines()[0]
                nvidia = True
                break
        except Exception:
            pass
    return name, vram, nvidia


def detect() -> SystemInfo:
    info = SystemInfo(os_name=f"{platform.system()} {platform.release()}")
    info.cpu = platform.processor() or platform.machine() or "نامشخص"
    info.cores = os.cpu_count() or 1
    try:
        import psutil
        info.ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        if platform.system() == "Windows":
            total = _run(["wmic", "computersystem", "get", "TotalPhysicalMemory"])
            digits = "".join(ch for ch in total if ch.isdigit())
            if digits:
                info.ram_gb = int(digits) / (1024 ** 3)
        else:
            try:
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemTotal:"):
                        info.ram_gb = int(line.split()[1]) / (1024 ** 2)
                        break
            except Exception:
                pass
    info.gpu, info.vram_gb, info.has_nvidia = detect_gpu()
    return info


def recommend(info: SystemInfo) -> dict[str, Any]:
    """پیشنهاد مدل بر اساس رم و VRAM + گزینههای جایگزین."""
    if info.ram_gb and info.ram_gb < 12 and info.vram_gb < 4:
        primary = "light"
    elif info.ram_gb >= 24 and info.vram_gb >= 7:
        primary = "balanced"   # 7B کاملاً روی GPU؛ سریع و باکیفیت
    elif info.ram_gb >= 16 or info.vram_gb >= 5:
        primary = "balanced"
    else:
        primary = "light"

    profile = PROFILES[primary].as_dict()
    gpu_layers = profile["gpu_layers"]
    if info.vram_gb < 6 and primary == "balanced":
        gpu_layers = 0  # اجرای CPUای
        profile["note"] += " روی این سیستم بدون GPU قوی بهصورت CPU اجرا میشود و کندتر است."

    alternatives = [
        PROFILES[k].as_dict() for k in ("light", "balanced", "quality") if k != primary
    ]
    # توصیهٔ ویژه برای سیستمهای قوی (مثل ۳۲ گیگ رم + ۸ گیگ VRAM)
    if info.ram_gb >= 28 and info.vram_gb >= 7:
        extra = "با ۳۲ گیگ رم و ۸ گیگ VRAM، 7B کاملاً روی GPU اجرا میشود. 14B هم قابل اجراست ولی کندتر است."
    else:
        extra = ""
    return {
        "primary": profile,
        "gpu_layers": gpu_layers,
        "alternatives": alternatives,
        "system": info.as_dict(),
        "system_summary": info.summary_fa(),
        "note": extra,
    }
