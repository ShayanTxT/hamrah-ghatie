"""تبدیل تاریخ میلادی ↔ شمسی — پیادهسازی خالص پایتون، بدون وابستگی.

الگوریتم تبدیل میلادی به شمسی بر اساس دورهٔ ۳۳ سالهٔ بیرشک است.
تبدیل معکوس با جستجوی دودویی روی همان تابع انجام میشود تا همیشه سازگار
باشد (از تفاوت الگوریتمهای مختلف در سال کبیسه جلوگیری میکند).
"""
from __future__ import annotations

from datetime import date, datetime

from .persian import to_persian_digits

MONTHS_FA = [
    "", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
WEEKDAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سهشنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

_G_DAYS_BEFORE_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل (سال، ماه، روز) میلادی به (سال، ماه، روز) شمسی.

    >>> gregorian_to_jalali(2026, 3, 21)
    (1405, 1, 1)
    """
    if not (1 <= gm <= 12 and 1 <= gd <= 31):
        raise ValueError("تاریخ میلادی نامعتبر است")
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + _G_DAYS_BEFORE_MONTH[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """معکوس تبدیل؛ با جستجوی دودویی روی :func:`gregorian_to_jalali`.

    >>> jalali_to_gregorian(1405, 1, 1)
    (2026, 3, 21)
    """
    if not (1 <= jm <= 12 and 1 <= jd <= 31):
        raise ValueError("تاریخ شمسی نامعتبر است")
    target = (jy, jm, jd)
    # تخمین اولیه: نوروز هر سال شمسی حوالی ۲۱ مارس سال میلادی jy+621
    center = date(jy + 621, 3, 21).toordinal()
    lo, hi = center - 400, center + 400
    # گسترش بازه در صورت نیاز (برای سالهای خیلی دور)
    def _conv(ordinal: int) -> tuple[int, int, int]:
        d = date.fromordinal(ordinal)
        return gregorian_to_jalali(d.year, d.month, d.day)

    while _conv(lo) > target:
        lo -= 400
    while _conv(hi) < target:
        hi += 400
    while lo < hi:
        mid = (lo + hi) // 2
        d = date.fromordinal(mid)
        if gregorian_to_jalali(d.year, d.month, d.day) < target:
            lo = mid + 1
        else:
            hi = mid
    d = date.fromordinal(lo)
    return d.year, d.month, d.day


def from_datetime(value: datetime | None = None) -> tuple[int, int, int]:
    value = value or datetime.now()
    return gregorian_to_jalali(value.year, value.month, value.day)


def format_date(value: datetime | date | None = None, *, with_weekday: bool = False) -> str:
    """مثال: «۱۴۰۵/۰۸/۰۴» یا «یکشنبه ۴ آبان ۱۴۰۵»."""
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    dt = value or datetime.now()
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    if with_weekday:
        # دوشنبه = ۰ در پایتون؛ شنبه = ۰ در تقویم فارسی
        wd = WEEKDAYS_FA[(dt.weekday() + 2) % 7]
        return to_persian_digits(f"{wd} {jd} {MONTHS_FA[jm]} {jy}")
    return to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")


def format_datetime(value: datetime | None = None, *, with_seconds: bool = False) -> str:
    """مثال: «۱۴۰۵/۰۸/۰۴ — ۱۸:۳۲». برای تاریخچهٔ قطعیها."""
    dt = value or datetime.now()
    d = format_date(dt)
    fmt = "%H:%M:%S" if with_seconds else "%H:%M"
    return f"{d} — {to_persian_digits(dt.strftime(fmt))}"


def format_duration(seconds: float) -> str:
    """مدت زمان به فارسی: «۲ ساعت و ۱۵ دقیقه»."""
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} روز")
    if hours:
        parts.append(f"{hours} ساعت")
    if minutes:
        parts.append(f"{minutes} دقیقه")
    if not parts:
        parts.append(f"{secs} ثانیه")
    return to_persian_digits(" و ".join(parts))
