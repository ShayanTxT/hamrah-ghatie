"""تست کتابخانهٔ آفلاین و جستجوی تماممتن فارسی (FTS5)."""
from __future__ import annotations

from pathlib import Path

from hamrah.core.library import Library


def test_index_and_search_persian_variants(db, settings, paths):
    lib = Library(db, settings, paths)
    folder = paths.library
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "notes.txt").write_text(
        "گزارش قطعی اینترنت ملی\nدر شبكهٔ داخلی، كتابخانهٔ آفلاین همچنان کار میکند.\n"
        "من می\u200cروم تا اخبار را بررسی کنم.",
        encoding="utf-8",
    )
    indexed = lib.index_file(folder / "notes.txt")
    assert indexed is True
    assert lib.index_file(folder / "notes.txt") is False  # بدون تغییر، دوباره ایندکس نشد

    for query in ["اینترنت ملی", "اينترنت ملي", "شبکه", "شبكه", "كتابخانه", "میروم"]:
        hits = lib.search(query)
        assert hits, f"جستجوی {query!r} نتیجهای نداشت"
        assert hits[0].source_label == "فایلهای من"

    hits = lib.search("اینترنت ملی")
    assert "اینترنت" in hits[0].snippet or "مل" in hits[0].snippet


def test_html_file_is_stripped(db, settings, paths):
    lib = Library(db, settings, paths)
    p = paths.library / "page.html"
    p.write_text("<html><script>var x=1;</script><body><h1>تهران</h1><p>آب و هوا</p></body></html>",
                 encoding="utf-8")
    lib.index_file(p)
    assert not lib.search("var x=1")
    assert lib.search("آب و هوا")


def test_scan_folder_and_stats(db, settings, paths):
    lib = Library(db, settings, paths)
    (paths.library / "a.txt").write_text("مطلب اول", encoding="utf-8")
    (paths.library / "b.md").write_text("مطلب دوم", encoding="utf-8")
    (paths.library / "ignore.exe").write_bytes(b"binary")
    result = lib.scan_folder(progress=lambda i, t, name: None)
    assert result["total"] == 2 and result["added"] == 2
    stats = lib.stats()
    assert stats["documents"] == 2
    assert len(lib.recent()) == 2


def test_zim_index_and_unified_search(db, settings, paths, sample_zim):
    if sample_zim is None:
        import pytest
        pytest.skip("فایل نمونهٔ ZIM موجود نیست")
    settings["zim_max_articles"] = 40
    lib = Library(db, settings, paths)
    result = lib.index_zim(sample_zim, max_articles=40)
    assert result["entries"] > 1000
    assert result["indexed"] > 10
    assert lib.stats()["documents"] >= result["indexed"]
    assert len(lib.zim_list()) == 1
    hits = lib.search("climate", limit=10)
    assert hits
    assert any("ویکیپدیا" in h.source_label for h in hits)
    removed = lib.remove_zim(sample_zim)
    assert removed >= 10
    assert lib.stats()["documents"] == 0
