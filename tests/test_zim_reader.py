"""تست خوانندهٔ بومی ZIM روی یک فایل ZIM واقعی (نمونهٔ ۱۴ مگابایتی)."""
from __future__ import annotations

import pytest

from hamrah.core.textutil import strip_html
from hamrah.core.zim_reader import ZimArchive, ZimError


def test_open_real_zim(sample_zim):
    if sample_zim is None:
        pytest.skip("فایل نمونهٔ ZIM موجود نیست")
    with ZimArchive(sample_zim) as archive:
        info = archive.as_dict()
        assert info["entries"] > 1000
        assert info["clusters"] > 0
        assert "climate" in info["title"].lower()
        assert info["language"] == "eng"
        assert info["main"] is not None


def test_read_main_page_and_redirect(sample_zim):
    if sample_zim is None:
        pytest.skip("فایل نمونهٔ ZIM موجود نیست")
    with ZimArchive(sample_zim) as archive:
        html, mime = archive.read_path(archive.main_path)
        assert mime == "text/html"
        assert b"<html" in html.lower()
        assert "Climate" in strip_html(html.decode("utf-8", "ignore"))

        redirects = [e for e in archive.entries() if e.is_redirect]
        assert redirects
        data, _ = archive.read_entry(redirects[0])
        assert len(data) > 100


def test_title_search(sample_zim):
    if sample_zim is None:
        pytest.skip("فایل نمونهٔ ZIM موجود نیست")
    with ZimArchive(sample_zim) as archive:
        hits = archive.search_titles("climate", limit=10)
        assert hits
        assert any("Climate" in h.title or "climate" in h.title.lower() for h in hits)
        assert archive.find("A/index") is not None


def test_bad_file(tmp_path):
    bad = tmp_path / "bad.zim"
    bad.write_bytes(b"not a zim file")
    with pytest.raises(ZimError):
        ZimArchive(bad)
