"""خطاهای کاربرپسند فارسی.

قانون: هیچ پیام فنی انگلیسی نباید مستقیم به کاربر نشان داده شود.
جزئیات فنی (traceback) حتماً توسط :mod:`logging_setup` در فایل لاگ نوشته میشود.
"""
from __future__ import annotations

import socket
import sqlite3
import ssl
import subprocess
from typing import Any

GENERIC = "یک مشکل پیش آمد. جزئیات در پوشهٔ data/logs ذخیره شد."

_MESSAGES: list[tuple[tuple[type[BaseException], ...], str]] = [
    ((FileNotFoundError,), "فایل مورد نظر پیدا نشد. شاید جابهجا یا حذف شده باشد."),
    ((PermissionError,), "دسترسی به این فایل ممکن نیست. برنامه را از پوشهای اجرا کنید که اجازهٔ نوشتن دارد (مثلاً داخل Documents نه Program Files)."),
    ((ConnectionRefusedError,), "اتصال برقرار نشد؛ مقصد درخواست را رد کرد."),
    ((socket.timeout, TimeoutError, subprocess.TimeoutExpired), "زمان اتصال تمام شد. دوباره تلاش میکنیم."),
    ((socket.gaierror,), "آدرس مقصد قابل حل کردن نیست (مشکل DNS یا نبود اینترنت)."),
    ((ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError), "ارتباط شبکه ناگهان قطع شد. ادامهٔ کار از همانجا از سر گرفته میشود."),
    ((ssl.SSLError,), "ارتباط امن برقرار نشد (گواهی یا پروکسی مشکل دارد)."),
    ((sqlite3.Error,), "پایگاه داده در دسترس نیست. اگر برنامه روی فلش است، آن را به پوشهای با دسترسی نوشتن منتقل کنید."),
    ((UnicodeDecodeError,), "کدگذاری این فایل قابل تشخیص نبود؛ فقط فایلهای UTF-8 و ANSI فارسی پشتیبانی میشوند."),
    ((ValueError,), "ورودی نامعتبر است. لطفاً مقادیر را دوباره بررسی کنید."),
]

# OSError خیلی کلی است؛ باید بعد از استثناهای دقیقتر بررسی شود.
_OSError_FALLBACK = "خطای سیستمی هنگام کار با فایل یا شبکه رخ داد."


class AppError(Exception):
    """خطای قابل پیشبینی با پیام فارسی برای نمایش به کاربر."""

    def __init__(self, user_message: str, *, detail: str = "", code: str = "app") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail
        self.code = code

    def __str__(self) -> str:  # pragma: no cover
        return self.user_message


def friendly(exc: BaseException, context: str = "") -> str:
    """تبدیل استثنا به پیام فارسی. ``context`` جملهای است که قبلش میآید."""
    if isinstance(exc, AppError):
        message = exc.user_message
    else:
        message = ""
        for types, text in _MESSAGES:
            if isinstance(exc, types):
                message = _OSError_FALLBACK if isinstance(exc, OSError) and not isinstance(
                    exc, (ConnectionError, FileNotFoundError, PermissionError)
                ) else text
                break
        if not message:
            message = GENERIC
    return f"{context} {message}".strip() if context else message


def user_error(context: str, detail: str = "") -> AppError:
    """ساخت سریع خطای فارسی."""
    return AppError(context, detail=detail)
