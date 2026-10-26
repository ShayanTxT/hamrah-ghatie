"""تست صف دانلود قابلادامه — بدون هیچ درخواست شبکهای واقعی."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hamrah.core.downloader import DownloadQueue, parse_content_range
from hamrah.core.netpolicy import NetworkGuard, Purpose
from hamrah.core.pagesaver import PageSaver


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class FakeHttp:
    """شبیهساز سرور HTTP که Range و ETag را پشتیبانی میکند."""

    def __init__(self, content: bytes, *, supports_range: bool = True,
                 interrupt_after: int | None = None):
        self.content = content
        self.supports_range = supports_range
        self.interrupt_after = interrupt_after
        self.calls: list[dict] = []
        self.guard = NetworkGuard()

    def open(self, url, purpose, *, method="GET", headers=None, data=None, timeout=8.0):
        assert purpose in (Purpose.DOWNLOAD, Purpose.PAGE_ASSET)
        self.guard.authorize(url, purpose, method)
        headers = dict(headers or {})
        self.calls.append({"url": url, "headers": headers})
        rng = headers.get("Range", "")
        start = int(rng.removeprefix("bytes=").split("-")[0]) if rng.startswith("bytes=") else 0
        if start and self.supports_range:
            body = self.content[start:]
            resp_headers = {
                "Content-Range": f"bytes {start}-{len(self.content) - 1}/{len(self.content)}",
                "Content-Length": str(len(body)),
                "ETag": '"abc123"',
            }
            status = 206
        else:
            body = self.content
            resp_headers = {"Content-Length": str(len(body)), "ETag": '"abc123"'}
            status = 200
        return FakeResponse(body, status, resp_headers)

    def get_bytes(self, url, purpose, *, max_bytes=..., timeout=8.0, headers=None):
        resp = self.open(url, purpose, headers=headers, timeout=timeout)
        return resp.read(), {k.lower(): v for k, v in resp.headers.items()}, resp.status


@pytest.fixture()
def queue(db, settings, paths):
    return DownloadQueue(db, settings, paths, http=FakeHttp(b"HELLO-WORLD"))


def test_parse_content_range():
    assert parse_content_range("bytes 100-199/200") == (100, 200)
    assert parse_content_range("garbage") is None


def test_simple_download(queue, paths):
    item_id = queue.add_file("https://example.com/file.zip", filename="file.zip")
    item = queue.get(item_id)
    queue.process_one(item)
    dest = Path(item.dest)
    assert dest.read_bytes() == b"HELLO-WORLD"
    assert queue.get(item_id).status == "done"
    assert not Path(str(dest) + ".part").exists()
    assert queue.http.calls[0]["url"].startswith("https://")


def test_resume_after_interruption(db, settings, paths):
    content = bytes(range(256)) * 40  # ۱۰ کیلوبایت
    http = FakeHttp(content)
    q = DownloadQueue(db, settings, paths, http=http)
    item_id = q.add_file("https://example.com/big.bin", filename="big.bin")
    item = q.get(item_id)

    # شبیهسازی قطع شدن وسط دانلود: فقط ۴ کیلوبایت اول در *.part ذخیره شده
    part = Path(str(item.dest) + ".part")
    part.write_bytes(content[:4096])
    db.execute("UPDATE downloads SET bytes_done = ?, etag = ?, status = 'pending' WHERE id = ?",
               (4096, '"abc123"', item_id))

    item2 = q.get(item_id)
    q.process_one(item2)
    assert Path(item2.dest).read_bytes() == content
    assert any(c["headers"].get("Range") == "bytes=4096-" for c in http.calls)
    assert q.get(item_id).status == "done"


def test_server_ignoring_range_restarts_cleanly(db, settings, paths):
    content = b"ABCDEFGH"
    http = FakeHttp(content, supports_range=False)
    q = DownloadQueue(db, settings, paths, http=http)
    item_id = q.add_file("https://example.com/x.bin", filename="x.bin")
    item = q.get(item_id)
    part = Path(str(item.dest) + ".part")
    part.write_bytes(b"OLD-DATA")
    db.execute("UPDATE downloads SET bytes_done = ?, etag = ? WHERE id = ?", (8, '"abc123"', item_id))
    q.process_one(q.get(item_id))
    assert Path(item.dest).read_bytes() == content
    assert not part.exists()


def test_pause_on_national_and_resume_on_free(queue):
    assert queue.should_run("free") is True
    assert queue.should_run("national") is False
    assert queue.should_run("down") is False
    queue.pause_all()
    assert queue.should_run("free") is False
    queue.resume_all()
    assert queue.should_run("free") is True


def test_page_saver_downloads_assets_and_rewrites(paths, settings):
    html = ('<html><head><link rel="stylesheet" href="/style.css"></head>'
            '<body><img src="/pic.png"><a href="/other.html">لینک</a>'
            '<script src="x.js"></script></body></html>').encode("utf-8")
    http = FakeHttp(html)

    class PageHttp(FakeHttp):
        def open(self, url, purpose, **kwargs):
            if url.endswith("style.css"):
                return FakeResponse(b"body{background:url(/bg.png)}", 200,
                                    {"Content-Type": "text/css"})
            if url.endswith(("pic.png", "bg.png", "x.js")):
                return FakeResponse(b"BINARY", 200, {"Content-Type": "image/png"})
            return FakeHttp.open(self, url, purpose, **kwargs)

    page_http = PageHttp(html)
    saver = PageSaver(page_http, settings, paths)
    result = saver.save("https://example.com/page.html", paths.pages / "sample")
    index = (paths.pages / "sample" / "index.html").read_text("utf-8")
    assert "assets/" in index
    assert "/pic.png" not in index
    assert (paths.pages / "sample" / "source.url").is_file()
    assert result["assets"] >= 3
    assert len(list((paths.pages / "sample" / "assets").glob("*"))) >= 3
