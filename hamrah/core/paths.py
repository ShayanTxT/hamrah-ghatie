"""مدیریت مسیرها — همهچیز کنار فایل اجرایی است.

قانون طلایی پروژه: بعد از ساخت، برنامه هیچ فایلی را خارج از پوشهٔ خودش
نمیخواند/نمینویسد (بهجز منابع فقطخواندنی داخل باندل و فایلهایی که کاربر
صراحتاً برای وارد کردن انتخاب میکند). در نتیجه کپی کردن پوشه = انتقال کامل
برنامه به کامپیوتر دیگر.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_DATA_DIR = "HAMRAH_DATA"


def is_frozen() -> bool:
    """آیا داخل بستهٔ PyInstaller اجرا میشویم؟"""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """پوشهای که exe (یا پوشهٔ پروژه) در آن قرار دارد."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    """پوشهٔ منابع فقطخواندنی (در حالت بستهبندی شده همان _MEIPASS است)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_root()))  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


class Paths:
    """تمام مسیرهای برنامه. ساخت این کلاس پوشهها را ایجاد میکند."""

    def __init__(self, data_dir: str | os.PathLike[str] | None = None) -> None:
        env = os.environ.get(ENV_DATA_DIR)
        self.root = Path(data_dir or env or (app_root() / "data")).resolve()
        self.bundle = bundle_root()
        self.ensure()

    # ---- منابع باندلشده (فقط خواندنی) ----
    @property
    def assets(self) -> Path:
        return self.bundle / "assets"

    @property
    def fonts(self) -> Path:
        return self.assets / "fonts"

    @property
    def styles(self) -> Path:
        return self.assets / "styles"

    # ---- دادههای کاربر (همه کنار exe) ----
    @property
    def db_path(self) -> Path:
        return self.root / "app.db"

    @property
    def config_path(self) -> Path:
        return self.root / "settings.json"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def downloads(self) -> Path:
        return self.root / "downloads"

    @property
    def pages(self) -> Path:
        return self.root / "pages"

    @property
    def library(self) -> Path:
        return self.root / "library"

    @property
    def zim(self) -> Path:
        return self.library / "zim"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def incoming(self) -> Path:
        return self.root / "incoming"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def identity_path(self) -> Path:
        return self.root / "identity.json"

    @property
    def peers_path(self) -> Path:
        return self.root / "peers.json"

    def all_dirs(self) -> list[Path]:
        return [
            self.root, self.logs, self.downloads, self.pages, self.library,
            self.zim, self.models, self.bin_dir, self.incoming, self.exports,
            self.tmp,
        ]

    def ensure(self) -> None:
        for d in self.all_dirs():
            d.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:  # pragma: no cover - فقط دیباگ
        return f"Paths(root={self.root!s}, bundle={self.bundle!s})"
