"""کلاینت HTTP سبک (فقط urllib استاندارد) با عبور اجباری از NetworkGuard."""
from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from .netpolicy import NetworkGuard, Purpose


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class HttpClient:
    """همهٔ درخواستها از اینجا رد میشوند تا سیاست شبکه رعایت شود.

    بهطور پیشفرض پروکسی سیستم دور زده میشود تا تست اتصال، وضعیت واقعی
    اینترنت را نشان دهد (پروکسی داخلی ممکن است پاسخ جعلی بدهد).
    """

    def __init__(
        self,
        guard: NetworkGuard | None = None,
        *,
        user_agent: str = "HamrahGhatie/1.0",
        use_system_proxy: bool = False,
    ) -> None:
        self.guard = guard or NetworkGuard()
        self.user_agent = user_agent
        handlers: list[Any] = []
        if not use_system_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        else:
            handlers.append(urllib.request.ProxyHandler())
        self.opener = urllib.request.build_opener(*handlers)

    def open(
        self,
        url: str,
        purpose: Purpose,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        timeout: float = 8.0,
    ):
        self.guard.authorize(url, purpose, method)
        hdrs = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        return self.opener.open(req, timeout=timeout)

    def get_bytes(
        self,
        url: str,
        purpose: Purpose,
        *,
        max_bytes: int = 32 * 1024 * 1024,
        timeout: float = 8.0,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str], int]:
        """خواندن پاسخ با سقف حجم؛ برای تستها و ذخیرهٔ صفحات."""
        with self.open(url, purpose, headers=headers, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            declared = int(resp_headers.get("content-length") or 0)
            limit = min(max_bytes, declared) if declared else max_bytes
            data = resp.read(limit + 1)
            if len(data) > limit:
                data = data[:limit]
            return data, resp_headers, status
