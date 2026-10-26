"""تست واقعی دانلود و ذخیرهٔ صفحه روی یک سرور HTTP محلی (بدون اینترنت)."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from hamrah.core.downloader import DownloadQueue
from hamrah.core.http import HttpClient
from hamrah.core.pagesaver import PageSaver

FILE_CONTENT = ("متن فارسی تست ".encode("utf-8")) * 500  # ~۱۰ کیلوبایت


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body: bytes, status: int = 200, ctype: str = "text/plain",
              extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", '"v1"')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/file.bin"):
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                start = int(rng[6:].split("-")[0])
                body = FILE_CONTENT[start:]
                self._send(body, 206, "application/octet-stream",
                           {"Content-Range": f"bytes {start}-{len(FILE_CONTENT)-1}/{len(FILE_CONTENT)}"})
            else:
                self._send(FILE_CONTENT, 200, "application/octet-stream")
        elif self.path == "/page.html":
            html = ('<html><head><link rel="stylesheet" href="/style.css"></head>'
                    '<body><h1>صفحهٔ تست</h1><img src="/pic.png"></body></html>').encode("utf-8")
            self._send(html, 200, "text/html; charset=utf-8")
        elif self.path == "/style.css":
            self._send(b"body{background:url(/pic.png)}", 200, "text/css")
        elif self.path == "/pic.png":
            self._send(b"\x89PNG\r\n\x1a\nDATA", 200, "image/png")
        else:
            self._send(b"not found", 404)


def _server():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_real_resumable_download(db, settings, paths):
    server, base = _server()
    try:
        http = HttpClient()
        q = DownloadQueue(db, settings, paths, http=http)
        item_id = q.add_file(base + "/file.bin", filename="file.bin")
        item = q.get(item_id)
        # نصفه نوشتن part پیش از شروع، تا حتماً مسیر Range طی شود
        part = Path(str(item.dest) + ".part")
        part.write_bytes(FILE_CONTENT[:3000])
        db.execute("UPDATE downloads SET bytes_done=?, etag=? WHERE id=?", (3000, '"v1"', item_id))
        q.process_one(q.get(item_id))
        assert Path(item.dest).read_bytes() == FILE_CONTENT
        assert q.get(item_id).status == "done"
        assert any(r.purpose.value == "download" for r in http.guard.records)
    finally:
        server.shutdown(); server.server_close()


def test_real_page_saver(settings, paths):
    server, base = _server()
    try:
        http = HttpClient()
        saver = PageSaver(http, settings, paths)
        result = saver.save(base + "/page.html", paths.pages / "real")
        index = (paths.pages / "real" / "index.html").read_text("utf-8")
        assert "صفحهٔ تست" in index
        assert "/pic.png" not in index and "assets/" in index
        assert result["assets"] >= 2
        assert len(list((paths.pages / "real" / "assets").glob("*"))) >= 2
        # فقط اهداف مجاز ثبت شدهاند
        assert {r.purpose.value for r in http.guard.records} <= {"download", "page_asset"}
    finally:
        server.shutdown(); server.server_close()
