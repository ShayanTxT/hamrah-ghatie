"""نرمالسازی متن فارسی برای جستجو و نمایش.

مسئلهای که حل میکنیم: در فایلهای فارسی، یک کلمه ممکن است با «ی» عربی، «ك»
عربی، نیمفاصله (ZWNJ)، اعراب یا ارقام فارسی/عربی نوشته شده باشد. جستجو
باید همهٔ این شکلها را یکی بگیرد. برای اینکه FTS5 هم همین رفتار را داشته
باشد، هم متن ایندکسشده و هم پرسوجوی کاربر از همین تابع عبور میکنند.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# نگاشت کاراکترهای همارز
_MAP = {
    # ی/ي/ى و ک/ك
    "\u064a": "\u06cc",  # ي عربی -> ی فارسی
    "\u0649": "\u06cc",  # ى (الف مقصوره) -> ی
    "\u0643": "\u06a9",  # ك عربی -> ک فارسی
    "\u06c0": "\u06cc",  # ۀ -> ی (تسامح در جستجو)
    "\u06d0": "\u06cc",  # ې
    # همزهها
    "\u0622": "\u0627", "\u0623": "\u0627", "\u0625": "\u0627",
    "\u0671": "\u0627", "\u0672": "\u0627", "\u0673": "\u0627",
    "\u0624": "\u0648",  # ؤ -> و
    "\u0626": "\u06cc",  # ئ -> ی
    "\u0629": "\u0647",  # ة -> ه
    # فاصلهها و کنترلها
    # نیمفاصله به فاصلهٔ معمولی تبدیل میشود؛ معادلسازی نهایی («میروم» = «می\u200cروم»)
    # با اضافه کردن توکنهای چسبیده در fts_index_text انجام میشود.
    "\u200c": " ", "\u200d": " ", "\u200e": "", "\u200f": "", "\ufeff": "",
    "\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u3000": " ",
    "\u0640": "",        # کشیده
}
# اعراب قرآنی / تلفظی
for _cp in list(range(0x064B, 0x0660)) + [0x0670, 0x06D6, 0x06D7, 0x06D8, 0x06D9,
                                          0x06DA, 0x06DB, 0x06DC, 0x06DF, 0x06E0,
                                          0x06E1, 0x06E2, 0x06E3, 0x06E4, 0x06E7,
                                          0x06E8, 0x06EA, 0x06EB, 0x06EC, 0x06ED]:
    _MAP.setdefault(chr(_cp), "")
# ارقام فارسی و عربی -> لاتین (تا «۱۴۰۵» و «1405» یکی شوند)
for _i in range(10):
    _MAP[chr(0x06F0 + _i)] = str(_i)
    _MAP[chr(0x0660 + _i)] = str(_i)

_TRANSLATION = str.maketrans(_MAP)
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_WS = re.compile(r"\s+")
_BAD_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize(text: str | None, *, keep_zwnj: bool = False) -> str:
    """نرمالسازی کامل برای ایندکس و پرسوجو.

    ``keep_zwnj=True`` نیمفاصله را به فاصلهٔ معمولی تبدیل میکند (برای نمایش).
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    if keep_zwnj:
        out = out.replace("\u200c", " ").replace("\u200d", " ")
    out = out.translate(_TRANSLATION).casefold()
    return _WS.sub(" ", out).strip()


def to_persian_digits(text: str) -> str:
    """تبدیل ارقام لاتین به فارسی برای نمایش (تاریخ، اعداد، ...)."""
    return str(text).translate(_PERSIAN_DIGITS)


def safe_filename(name: str, *, max_length: int = 120) -> str:
    """پاکسازی نام فایل از کاراکترهای ممنوعهٔ ویندوز."""
    cleaned = _BAD_FILENAME.sub("_", name or "file").strip(" .")
    cleaned = _WS.sub(" ", cleaned)
    if not cleaned:
        cleaned = "file"
    return cleaned[:max_length]


def fts_tokens(query: str) -> list[str]:
    """توکنهای نرمالشده و امن برای FTS5."""
    normalized = normalize(query)
    tokens: list[str] = []
    for token in normalized.split():
        # حذف کاراکترهایی که در نحو FTS5 معنی دارند
        token = "".join(ch for ch in token if ch not in '"*(){}[]:^-+')
        token = token.strip()
        if token:
            tokens.append(token)
    return tokens


def fts_index_text(text: str) -> str:
    """متن آمادهٔ ایندکس: نرمالشده + توکنهای چسبیدهٔ دوتایی.

    اضافه کردن حالت چسبیدهٔ هر دو کلمهٔ مجاور باعث میشود جستجوی
    «میروم» سند «می\u200cروم» را هم پیدا کند، و برعکس.
    """
    normalized = normalize(text)
    tokens = normalized.split()
    joined = [tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1)]
    return " ".join([normalized] + joined)


def build_fts_query(query: str, *, operator: str = "AND") -> str:
    """ساخت پرسوجوی FTS5 امن با جستجوی پیشوندی و پوشش نیمفاصله.

    مثال: «اینترنت ملی» -> ``("اینترنت"* AND "ملی"*) OR "اینترنتملی"*``
    """
    op = operator.upper()
    if op not in ("AND", "OR"):
        raise ValueError("عملگر باید AND یا OR باشد")
    tokens = fts_tokens(query)
    parts = [f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens]
    if not parts:
        return ""
    base = f" {op} ".join(parts)
    if op == "AND" and len(tokens) > 1:
        joined = "".join(tokens).replace('"', '""')
        return f'({base}) OR "{joined}"*'
    return base


def human_size(num_bytes: float) -> str:
    """حجم فایل به فارسی (مقیاس اعشاری، همانند حجمی که سایتها اعلام میکنند)."""
    units = ["بایت", "کیلوبایت", "مگابایت", "گیگابایت", "ترابایت"]
    value = float(num_bytes)
    i = 0
    while value >= 1000 and i < len(units) - 1:
        value /= 1000
        i += 1
    if i == 0:
        return to_persian_digits(f"{int(value)} {units[i]}")
    return to_persian_digits(f"{value:.1f} {units[i]}")


def truncate(text: str, limit: int = 180) -> str:
    text = _WS.sub(" ", text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"
