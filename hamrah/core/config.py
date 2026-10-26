"""تنظیمات کاربر بهصورت JSON ساده در ``data/settings.json``."""
from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # --- وضعیت اتصال ---
    "check_interval": 10,             # ثانیه بین دو تست
    "hysteresis_up": 2,               # چند نمونهٔ پیاپی برای تغییر به وضعیت بهتر
    "hysteresis_down": 2,             # چند نمونهٔ پیاپی برای تغییر به وضعیت بدتر
    "internal_hosts": ["https://www.aparat.com/", "https://www.digikala.com/", "https://www.irna.ir/"],
    "external_urls": ["https://www.google.com/generate_204", "https://www.cloudflare.com/cdn-cgi/trace"],
    "external_tcp": [["1.1.1.1", 443], ["8.8.8.8", 53], ["1.0.0.1", 443]],
    "dns_servers": ["1.1.1.1", "8.8.8.8"],
    "dns_test_domain": "example.com",
    "probe_timeout": 2.0,
    "notify_on_change": True,
    "notify_on_return": True,
    # --- کیف آمادگی ---
    "auto_pause_on_national": True,
    "max_asset_bytes": 8 * 1024 * 1024,
    "max_assets_per_page": 150,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HamrahGhatie/1.0",
    "use_system_proxy": False,
    # --- کتابخانه ---
    "max_index_chars": 200_000,
    "zim_max_articles": 5000,
    # --- دستیار ---
    "llama_port": 18081,
    "llama_ctx": 4096,
    "llama_gpu_layers": -1,           # 1- => تشخیص خودکار
    "llama_threads": 0,               # 0 => خودکار
    "llama_temperature": 0.7,
    "llama_max_tokens": 512,
    "ai_use_library": True,
    # --- شبکهٔ محلی ---
    "device_name": "",                # خالی => نام کامپیوتر
    "pairing_code": "",               # ۶ رقم، باید دو طرف یکی باشد
    "lan_udp_port": 54545,
    "lan_tcp_port": 54546,
    "lan_auto_accept_trusted": False,
    # --- رابط ---
    "theme": "light",                 # light / dark
    "font_size": 10,
    "minimize_to_tray": True,
    "start_minimized": False,
    "stage": 5,
}


class Config:
    """خواندن/نوشتن امن تنظیمات (ذخیرهٔ اتمیک برای جلوگیری از خرابی روی فلش)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        self._data.update({k: v for k, v in raw.items() if k in DEFAULTS})
                except (OSError, ValueError):
                    # تنظیمات خراب -> همان پیشفرضها، فایل خراب نگهداری میشود برای عیبیابی
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update({k: v for k, v in values.items() if k in DEFAULTS})

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def save(self) -> None:
        with self._lock:
            data = dict(self._data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def device_display_name(self) -> str:
        return self.get("device_name") or socket.gethostname()
