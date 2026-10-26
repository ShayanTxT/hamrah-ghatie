"""سیاست شبکه — تنها سه دلیل برای باز کردن سوکت وجود دارد.

این ماژول یک «نگهبان» است: تمام درخواستهای HTTP/Socket برنامه باید از آن
عبور کنند و دلیلشان را اعلام کنند. هر چیز دیگری (آپدیت، تله\u200cمتری، فونت
آنلاین، CDN) نهتنها پیادهمسازی نشده، بلکه در سطح کد هم ممنوع شده است.
تستها از رکوردهای نگهبان برای اثبات همین موضوع استفاده میکنند.
"""
from __future__ import annotations

import ipaddress
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from .errors import AppError


class Purpose(str, Enum):
    PROBE = "probe"            # تست وضعیت اتصال
    DOWNLOAD = "download"      # دانلودی که کاربر شروع کرده
    PAGE_ASSET = "page_asset"  # عکس/سیاساس صفحهای که کاربر خواسته ذخیره شود
    LOCAL_AI = "local_ai"      # فقط 127.0.0.1 (llama-server روی همان کامپیوتر)
    LAN = "lan"                # شبکهٔ محلی


PURPOSE_FA = {
    Purpose.PROBE: "تست وضعیت اتصال",
    Purpose.DOWNLOAD: "دانلود درخواستی شما",
    Purpose.PAGE_ASSET: "ذخیرهٔ صفحهٔ وب",
    Purpose.LOCAL_AI: "ارتباط داخلی با مدل هوش مصنوعی",
    Purpose.LAN: "شبکهٔ محلی",
}


@dataclass
class CallRecord:
    url: str
    purpose: Purpose
    host: str
    method: str = "GET"


class NetworkGuard:
    """ثبت و کنترل تمام درخواستهای شبکهای.

    ``strict=True`` (پیشفرض) جلوی هر درخواست با هدف LOCAL_AI به غیر loopback
    و جلوی هر مقصد خصوصی/loopback برای تست اتصال اینترنت جهانی را میگیرد.
    """

    def __init__(self, *, strict: bool = True) -> None:
        self.strict = strict
        self._records: list[CallRecord] = []
        self._lock = threading.Lock()

    @property
    def records(self) -> list[CallRecord]:
        with self._lock:
            return list(self._records)

    def authorize(self, url: str, purpose: Purpose, method: str = "GET") -> CallRecord:
        if not isinstance(purpose, Purpose):
            raise AppError(
                "درخواست شبکهای بدون دلیل مشخص مسدود شد.",
                detail=f"unknown purpose {purpose!r}", code="network_policy",
            )
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if purpose is Purpose.LOCAL_AI and self.strict:
            if host not in ("127.0.0.1", "localhost", "::1"):
                raise AppError(
                    "مدل هوش مصنوعی فقط باید بهصورت محلی اجرا شود؛ اتصال به آدرس بیرونی مسدود شد.",
                    detail=url, code="network_policy",
                )
        rec = CallRecord(url=url, purpose=purpose, host=host, method=method)
        with self._lock:
            self._records.append(rec)
        return rec

    def assert_policy(self, allowed: set[Purpose]) -> None:
        """برای تستها: هیچ درخواستی خارج از ``allowed`` نباید ثبت شده باشد."""
        bad = [r for r in self.records if r.purpose not in allowed]
        if bad:
            raise AssertionError(f"درخواستهای شبکهای غیرمجاز: {bad}")


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "::1")


def is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False
