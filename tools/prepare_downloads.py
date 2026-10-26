"""اسکریپت «آمادهسازی» — فقط زمانی اجرا شود که اینترنت هست.

این اسکریپت تنها جایی است که برنامه بهطور خودکار (و با اجازهٔ صریح شما)
فایلهای حجیم را دانلود میکند. بعد از قطعی، خود برنامه هیچ درخواست
اینترنتی جز تست اتصال و دانلودهایی که خودتان شروع کنید انجام نمیدهد.

نمونهها:
    python tools/prepare_downloads.py --list
    python tools/prepare_downloads.py --preset zim-fa-mini --preset model-balanced --preset llama-cuda
    python tools/prepare_downloads.py --preset zim-fa-mini --import-folder D:\\
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hamrah.core.config import Config  # noqa: E402
from hamrah.core.db import Database  # noqa: E402
from hamrah.core.downloader import DownloadQueue  # noqa: E402
from hamrah.core.http import HttpClient  # noqa: E402
from hamrah.core.paths import Paths  # noqa: E402
from hamrah.core.persian import human_size  # noqa: E402

KIVIX = "https://download.kiwix.org/zim/wikipedia/"
HF = "https://huggingface.co/bartowski/"
LLAMA_RELEASE = "b11901"   # نسخهٔ پینشده؛ در صورت نیاز به نسخهٔ جدیدتر این مقدار را عوض کنید
LLAMA_BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_RELEASE}/"

# (آدرس، پوشهٔ مقصد نسبت به data، حجم تقریبی به بایت، توضیح)
PRESETS: dict[str, tuple[str, str, int, str]] = {
    # --- مدلهای زبانی ---
    "model-light": (
        HF + "Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        "models", 1_929_903_264,
        "Qwen2.5-3B Q4_K_M — مناسب ۸ گیگ رم و CPU بدون GPU",
    ),
    "model-balanced": (
        HF + "Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "models", 4_683_074_240,
        "Qwen2.5-7B Q4_K_M — پیشنهاد اصلی برای سیستم ۳۲ گیگ رم + ۸ گیگ VRAM",
    ),
    "model-quality": (
        HF + "Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        "models", 8_988_110_976,
        "Qwen2.5-14B Q4_K_M — کیفیت بالا، کندتر (بخشی روی CPU)",
    ),
    # --- ویکیپدیای آفلاین (ZIM) ---
    "zim-fa-top-mini": (
        KIVIX + "wikipedia_fa_top_mini_2026-07a.zim", "library/zim", 220_000_000,
        "ویکیپدیای فارسی — مقالههای برتر، بدون عکس (کوچک، برای شروع)",
    ),
    "zim-fa-mini": (
        KIVIX + "wikipedia_fa_all_mini_2026-10.zim", "library/zim", 2_570_000_000,
        "ویکیپدیای فارسی — همهٔ مقالهها، عکسهای کم (پیشنهادی)",
    ),
    "zim-fa-top-maxi": (
        KIVIX + "wikipedia_fa_top_maxi_2026-07a.zim", "library/zim", 2_400_000_000,
        "ویکیپدیای فارسی — مقالههای برتر همراه عکس",
    ),
    "zim-fa-nopic": (
        KIVIX + "wikipedia_fa_all_nopic_2026-10.zim", "library/zim", 6_360_000_000,
        "ویکیپدیای فارسی — همهٔ مقالهها بدون عکس",
    ),
    "zim-fa-maxi": (
        KIVIX + "wikipedia_fa_all_maxi_2026-10.zim", "library/zim", 13_780_000_000,
        "ویکیپدیای فارسی کامل همراه عکسها",
    ),
    "zim-en-top-mini": (
        KIVIX + "wikipedia_en_top_mini_2026-09.zim", "library/zim", 300_000_000,
        "ویکیپدیای انگلیسی — مقالههای برتر، کوچک",
    ),
    "zim-en-top-maxi": (
        KIVIX + "wikipedia_en_top_maxi_2026-09.zim", "library/zim", 6_990_000_000,
        "ویکیپدیای انگلیسی — مقالههای برتر همراه عکس",
    ),
    # --- llama.cpp ---
    "llama-cpu": (
        LLAMA_BASE + f"llama-{LLAMA_RELEASE}-bin-win-cpu-x64.zip", "bin", 30_000_000,
        "llama-server.exe نسخهٔ CPU (بدون نیاز به کارت گرافیک)",
    ),
    "llama-cuda": (
        LLAMA_BASE + f"llama-{LLAMA_RELEASE}-bin-win-cuda-12.4-x64.zip", "bin", 250_000_000,
        "llama-server.exe نسخهٔ CUDA (برای GPUهای NVIDIA)",
    ),
    "llama-cudart": (
        LLAMA_BASE + "cudart-llama-bin-win-cuda-12.4-x64.zip", "bin", 300_000_000,
        "کتابخانههای CUDA همراه بستهٔ cuda (در همان data/bin استخراج شود)",
    ),
}

MODEL_EXTS = {".gguf"}
ZIM_EXTS = {".zim"}
DOC_EXTS = {".pdf", ".html", ".htm", ".txt", ".md", ".epub", ".docx", ".csv"}


def main() -> int:
    parser = argparse.ArgumentParser(description="دانلود فایلهای لازم قبل از قطعی اینترنت")
    parser.add_argument("--data-dir", default="", help="پوشهٔ data (پیشفرض کنار سورس/exe)")
    parser.add_argument("--preset", action="append", default=[], help="کلید فایل مورد نظر (چندبار قابل تکرار)")
    parser.add_argument("--list", action="store_true", help="نمایش فهرست فایلها و حجمها")
    parser.add_argument("--minimal", action="store_true",
                        help="بستهٔ حداقلی: zim-fa-mini + model-balanced + llama-cuda")
    parser.add_argument("--import-folder", default="",
                        help="وارد کردن فایلها از فلش/هارد به پوشهٔ data")
    args = parser.parse_args()

    paths = Paths(args.data_dir or None)
    print(f"پوشهٔ داده: {paths.root}\n")

    if args.list:
        print(f"{'کلید':<22} {'حجم':<14} توضیح")
        print("─" * 90)
        for key, (url, dest, size, note) in PRESETS.items():
            print(f"{key:<22} {human_size(size):<14} {note}")
        return 0

    if args.import_folder:
        return import_folder(Path(args.import_folder), paths)

    keys = list(args.preset)
    if args.minimal:
        keys += ["zim-fa-mini", "model-balanced", "llama-cuda", "llama-cudart"]
    keys = list(dict.fromkeys(keys))
    if not keys:
        print("هیچ فایلی انتخاب نشده. از --list و --preset استفاده کنید.")
        return 1

    for key in keys:
        if key not in PRESETS:
            print(f"❌ کلید ناشناخته: {key}")
            return 1

    cfg = Config(paths.config_path)
    db = Database(paths.db_path)
    http = HttpClient(user_agent=str(cfg.get("user_agent")))
    queue = DownloadQueue(db, cfg, paths, http=http)
    total = sum(PRESETS[k][2] for k in keys)
    print(f"تعداد {len(keys)} فایل، مجموع تقریبی {human_size(total)}\n")

    for key in keys:
        url, dest_key, size, note = PRESETS[key]
        dest_dir = paths.root / dest_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = url.rsplit("/", 1)[-1].split("?")[0]
        target = dest_dir / name
        if target.is_file() and target.stat().st_size > 0:
            print(f"✅ {key}: قبلاً دانلود شده ({human_size(target.stat().st_size)})")
            finish(target, paths)
            continue
        print(f"⬇  {key}: {note} — حدود {human_size(size)}")
        item_id = queue.add_file(url, dest_dir=dest_dir, filename=name)
        for attempt in range(1, 4):
            try:
                queue.process_one(
                    queue.get(item_id),
                    progress=lambda d, t: print(
                        f"\r   {human_size(d)} / {human_size(t) if t else '?'}", end="", flush=True),
                )
                print()
                if queue.get(item_id).status == "done":
                    finish(target, paths)
                    break
            except Exception as exc:
                print(f"\n   تلاش {attempt} ناموفق: {type(exc).__name__}: {exc} — ادامه از همانجا...")
                time.sleep(2)
        else:
            print(f"❌ {key} دانلود نشد. فایل .part نگهداشته شد؛ دوباره اجرا کنید.")
    print("\nتمام. پوشهٔ data را کنار exe نگهدارید.")
    return 0


def finish(path: Path, paths: Paths) -> None:
    """پسپردازش: استخراج بستههای llama.cpp."""
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                z.extractall(paths.bin_dir)
            print(f"   📦 محتویات {path.name} در data/bin استخراج شد.")
        except zipfile.BadZipFile:
            print("   ⚠ فایل ZIP ناقص است؛ دوباره دانلود کنید.")


def import_folder(source: Path, paths: Paths) -> int:
    """کپی فایلها از فلش/هارد خارجی به پوشهٔ data."""
    if not source.is_dir():
        print(f"❌ پوشه پیدا نشد: {source}")
        return 1
    mapping = [
        (MODEL_EXTS, paths.models), (ZIM_EXTS, paths.zim),
        (DOC_EXTS, paths.library / "فایلهای من"),
    ]
    for dest in (paths.models, paths.zim, paths.library / "فایلهای من", paths.bin_dir):
        dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in source.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if p.name.lower() == "llama-server.exe" or ext == ".dll":
            dest_dir = paths.bin_dir
        else:
            dest_dir = next((d for exts, d in mapping if ext in exts), None)
        if dest_dir is None:
            continue
        target = dest_dir / p.name
        if target.exists() and target.stat().st_size == p.stat().st_size:
            continue
        print(f"   کپی {p.name} -> {dest_dir.name} ({human_size(p.stat().st_size)})")
        shutil.copy2(p, target)
        count += 1
        if ext == ".zip" and "llama" in p.name.lower():
            finish(target, paths)
    print(f"\n✅ {count} فایل وارد شد. حالا برنامه را باز کنید و از تب کتابخانه «اسکن» را بزنید.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
