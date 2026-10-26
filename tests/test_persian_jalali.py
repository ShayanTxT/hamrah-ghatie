"""تست نرمالسازی فارسی، ساخت پرسوجوی FTS و تبدیل تاریخ شمسی."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from hamrah.core.jalali import (
    format_date, format_datetime, format_duration,
    gregorian_to_jalali, jalali_to_gregorian,
)
from hamrah.core.persian import (
    build_fts_query, fts_index_text, fts_tokens, normalize, safe_filename, to_persian_digits,
)


def test_persian_variants_are_equal():
    variants = ["اینترنت ملی", "اينترنت ملي", "اينترنت ملی", "اينترنِت ملی"]
    normalized = {normalize(v) for v in variants}
    assert len(normalized) == 1, normalized


def test_kaf_yeh_and_half_space():
    assert normalize("كتابخانة بزرگ") == normalize("کتابخانهٔ بزرگ")
    assert normalize("شبكه") == normalize("شبکه")
    # نیمفاصله به فاصله تبدیل میشود و توکن چسبیده هم در ایندکس اضافه میشود
    assert normalize("اینترنت\u200cملی") == normalize("اینترنت ملی")
    assert "میروم" in fts_index_text("من می\u200cروم")
    assert normalize("مسجد جامع") == normalize("مَسجد جامع")  # اعراب حذف میشود


def test_digits():
    assert normalize("۱۴۰۵") == normalize("1405") == normalize("١٤٠٥")
    assert to_persian_digits("1405/08/04") == "۱۴۰۵/۰۸/۰۴"
    assert "۱۴۰۵" in format_date(date(2026, 10, 26))


def test_fts_query_is_safe_and_prefixy():
    q = build_fts_query('كتاب "خاص" * OR')
    assert q.startswith(('"', '(')) and '"*' in q
    assert " OR " in q  # شاخهٔ حالت چسبیده
    assert "* OR" not in q
    assert fts_tokens("   ") == []
    assert build_fts_query("تهران") == '"تهران"*'
    assert build_fts_query("تهران شیراز") == '("تهران"* AND "شیراز"*) OR "تهرانشیراز"*'


def test_safe_filename():
    assert "/" not in safe_filename("a/b:c?.txt")
    assert safe_filename("").startswith("file")


def test_jalali_known_dates():
    assert gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
    assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    assert gregorian_to_jalali(2023, 3, 21) == (1402, 1, 1)
    assert jalali_to_gregorian(1405, 1, 1) == (2026, 3, 21)


def test_jalali_against_jdatetime():
    jdatetime = pytest.importorskip("jdatetime")
    for year, month, day in [(2000, 1, 1), (2024, 2, 29), (2026, 10, 26),
                             (2030, 12, 31), (1985, 6, 15)]:
        expected = jdatetime.date.fromgregorian(date=date(year, month, day))
        assert gregorian_to_jalali(year, month, day) == (
            expected.year, expected.month, expected.day)


def test_format_helpers():
    assert "—" in format_datetime(datetime(2026, 10, 26, 18, 30))
    assert "ساعت" in format_duration(3600 * 2 + 60)
    assert "ثانیه" in format_duration(5)
