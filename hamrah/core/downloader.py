"""مرحلهٔ ۲ — صف دانلود مقاوم به قطعی (resume).

ویژگیها:
* فایل نیمهکاره همیشه ``*.part`` است؛ بعد از تکمیل به نام اصلی تغییر نام میدهد.
* از ETag/Last-Modified بهعنوان ``If-Range`` استفاده میکند تا اگر سرور فایل را
  عوض کرده بود، دانلود از صفر شروع شود (جلوی خراب شدن فایل).
* اگر سرور Range را نادیده گرفت و ۲۰۰ داد، فایل از نو نوشته میشود.
* هنگام «فقط ملی» یا «قطع کامل» صف متوقف میشود و با برگشتن اینترنت آزاد
  خودکار ادامه پیدا میکند.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import DEFAULTS
from .db import Database
from .http import HttpClient
from .netpolicy import Purpose
from .persian import safe_filename

CHUNK = 64 * 1024
STATUS_FA = {
    "pending": "در انتظار",
    "running": "در حال دانلود",
    "waiting_net": "منتظر اینترنت آزاد",
    "paused": "متوقف شده",
    "done": "انجام شد",
    "error": "خطا",
}


@dataclass
class DownloadItem:
    id: int
    url: str
    kind: str
    dest: str
    status: str
    bytes_done: int
    bytes_total: int
    etag: str | None
    last_modified: str | None
    error: str | None
    attempts: int
    created_at: float
    updated_at: float

    @classmethod
    def from_row(cls, row: Any) -> "DownloadItem":
        return cls(
            id=row["id"], url=row["url"], kind=row["kind"], dest=row["dest"],
            status=row["status"], bytes_done=row["bytes_done"], bytes_total=row["bytes_total"],
            etag=row["etag"], last_modified=row["last_modified"], error=row["error"],
            attempts=row["attempts"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @property
    def name(self) -> str:
        return Path(self.dest).name

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "url": self.url, "kind": self.kind, "dest": self.dest,
            "status": self.status, "status_fa": STATUS_FA.get(self.status, self.status),
            "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
            "error": self.error, "attempts": self.attempts, "name": self.name,
        }


def filename_from_url(url: str, fallback: str = "download.bin") -> str:
    """استخراج نام فایل امن از URL (پشتیبانی از نامهای فارسی/percent-encoded)."""
    path = urllib.parse.urlparse(url).path
    name = urllib.parse.unquote(Path(path).name or "")
    name = safe_filename(name)
    return name or fallback


def parse_content_range(value: str) -> tuple[int, int] | None:
    """پارس ``Content-Range: bytes 123-456/789`` -> (شروع، کل)."""
    m = re.search(r"bytes\s+(\d+)-\d+/(\d+)", value or "", re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


class DownloadQueue:
    """صف دانلود مبتنی بر SQLite (بعد از بستن برنامه هم ادامه پیدا میکند)."""

    def __init__(
        self,
        db: Database,
        cfg: dict[str, Any],
        paths: Any,
        http: HttpClient | None = None,
        page_saver: Any | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.cfg = cfg
        self.paths = paths
        self.http = http or HttpClient(user_agent=str(cfg.get("user_agent", DEFAULTS["user_agent"])))
        self.page_saver = page_saver
        self.clock = clock
        self._user_paused = False
        self._lock = threading.Lock()
        # آیتمهایی که وسط کار بودهاند به صف برمیگردند
        self.db.execute("UPDATE downloads SET status = 'pending' WHERE status IN ('running','waiting_net')")

    # ---------- مدیریت صف ----------
    def add_file(self, url: str, dest_dir: Path | None = None, filename: str | None = None) -> int:
        dest_dir = Path(dest_dir or self.paths.downloads)
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = safe_filename(filename or filename_from_url(url))
        dest = dest_dir / name
        return self._insert(url, "file", str(dest))

    def add_page(self, url: str, dest_dir: Path | None = None) -> int:
        dest_dir = Path(dest_dir or self.paths.pages)
        dest_dir.mkdir(parents=True, exist_ok=True)
        host = urllib.parse.urlparse(url).netloc or "صفحه"
        name = safe_filename(host + "_" + (urllib.parse.urlparse(url).path.strip("/") or "index").replace("/", "_"))
        dest = dest_dir / name
        return self._insert(url, "page", str(dest))

    def _insert(self, url: str, kind: str, dest: str) -> int:
        now = self.clock()
        existing = self.db.query("SELECT id FROM downloads WHERE url = ? AND dest = ?", (url, dest))
        if existing:
            return int(existing[0]["id"])
        return self.db.execute(
            "INSERT INTO downloads(url, kind, dest, status, created_at, updated_at) "
            "VALUES(?, ?, ?, 'pending', ?, ?)",
            (url, kind, dest, now, now),
        )

    def get(self, item_id: int) -> DownloadItem | None:
        rows = self.db.query("SELECT * FROM downloads WHERE id = ?", (item_id,))
        return DownloadItem.from_row(rows[0]) if rows else None

    def list_items(self) -> list[DownloadItem]:
        rows = self.db.query("SELECT * FROM downloads ORDER BY created_at DESC, id DESC")
        return [DownloadItem.from_row(r) for r in rows]

    def pending(self) -> list[DownloadItem]:
        rows = self.db.query(
            "SELECT * FROM downloads WHERE status IN ('pending','waiting_net') ORDER BY created_at"
        )
        return [DownloadItem.from_row(r) for r in rows]

    def set_status(self, item_id: int, status: str, error: str | None = None) -> None:
        self.db.execute(
            "UPDATE downloads SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, self.clock(), item_id),
        )

    def remove(self, item_id: int, *, delete_files: bool = False) -> None:
        item = self.get(item_id)
        if item and delete_files:
            for p in (Path(item.dest), Path(str(item.dest) + ".part")):
                try:
                    if p.is_file():
                        p.unlink()
                    elif p.is_dir():
                        import shutil
                        shutil.rmtree(p, ignore_errors=True)
                except OSError:
                    pass
        self.db.execute("DELETE FROM downloads WHERE id = ?", (item_id,))

    def pause_all(self) -> None:
        with self._lock:
            self._user_paused = True
        self.db.execute("UPDATE downloads SET status = 'paused' WHERE status IN ('pending','waiting_net')")

    def resume_all(self) -> None:
        with self._lock:
            self._user_paused = False
        self.db.execute("UPDATE downloads SET status = 'pending' WHERE status = 'paused'")

    def retry(self, item_id: int) -> None:
        self.db.execute("UPDATE downloads SET status = 'pending', error = NULL, attempts = 0 WHERE id = ?",
                        (item_id,))

    @property
    def user_paused(self) -> bool:
        with self._lock:
            return self._user_paused

    def _update_progress(self, item_id: int, done: int, total: int) -> None:
        self.db.execute(
            "UPDATE downloads SET bytes_done = ?, bytes_total = ?, updated_at = ? WHERE id = ?",
            (done, total, self.clock(), item_id),
        )

    # ---------- اجرای یک آیتم ----------
    def process_one(
        self,
        item: DownloadItem,
        *,
        progress: Callable[[int, int], None] | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> None:
        """دانلود یک آیتم. در صورت خطا استثنا میدهد تا حلقه تصمیم بگیرد."""
        should_continue = should_continue or (lambda: True)
        if item.kind == "page":
            self._process_page(item, progress=progress, should_continue=should_continue)
        else:
            self._process_file(item, progress=progress, should_continue=should_continue)

    def _process_file(
        self,
        item: DownloadItem,
        *,
        progress: Callable[[int, int], None] | None,
        should_continue: Callable[[], bool],
    ) -> None:
        dest = Path(item.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0 and not Path(str(dest) + ".part").exists():
            self.set_status(item.id, "done")
            return
        part = Path(str(dest) + ".part")
        existing = part.stat().st_size if part.exists() else 0

        headers: dict[str, str] = {}
        if existing:
            headers["Range"] = f"bytes={existing}-"
            if item.etag:
                headers["If-Range"] = item.etag
            elif item.last_modified:
                headers["If-Range"] = item.last_modified

        resp = self.http.open(item.url, Purpose.DOWNLOAD, headers=headers or None,
                              timeout=20.0)
        status = getattr(resp, "status", 200) or 200
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        etag = resp_headers.get("etag")
        last_modified = resp_headers.get("last-modified")

        if status == 206:
            parsed = parse_content_range(resp_headers.get("content-range", ""))
            if parsed and parsed[0] != existing:
                # سرور از جای دیگری شروع کرده؛ از نو مینویسیم
                existing = 0
                mode = "wb"
            else:
                mode = "ab"
            total = (parsed[1] if parsed else existing + int(resp_headers.get("content-length", 0)))
        elif status == 200:
            existing = 0
            mode = "wb"
            total = int(resp_headers.get("content-length", 0) or 0)
        else:
            resp.close()
            raise RuntimeError(f"سرور کد {status} برگرداند")

        self.db.execute(
            "UPDATE downloads SET etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified), "
            "bytes_total = ?, status = 'running', error = NULL WHERE id = ?",
            (etag, last_modified, total, item.id),
        )
        done = existing
        try:
            with resp, open(part, mode) as out:
                while True:
                    if not should_continue():
                        # توقف نرم: همانجا رها میکند، دفعهٔ بعد ادامه میدهد
                        self.set_status(item.id, "waiting_net")
                        return
                    block = resp.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    self._update_progress(item.id, done, total)
                    if progress:
                        progress(done, total)
        finally:
            resp.close()

        if total and done < total:
            # اتصال وسط کار قطع شد؛ وضعیت خطا نمیدهیم، همان pending میماند
            self._update_progress(item.id, done, total)
            raise ConnectionError("دانلود نیمهکاره ماند")

        part.replace(dest)
        self.set_status(item.id, "done")

    def _process_page(
        self,
        item: DownloadItem,
        *,
        progress: Callable[[int, int], None] | None,
        should_continue: Callable[[], bool],
    ) -> None:
        if self.page_saver is None:
            from .pagesaver import PageSaver  # وابستگی دایرهای نداریم چون اینجا import محلی است
            self.page_saver = PageSaver(self.http, self.cfg, self.paths)
        self.set_status(item.id, "running")
        result = self.page_saver.save(
            item.url, Path(item.dest),
            progress=progress, should_continue=should_continue,
        )
        self.db.execute(
            "UPDATE downloads SET bytes_done = ?, bytes_total = ?, status = 'done', "
            "error = NULL, updated_at = ? WHERE id = ?",
            (result.get("bytes", 0), result.get("bytes", 0), self.clock(), item.id),
        )

    # ---------- حلقهٔ صف ----------
    def should_run(self, state: str) -> bool:
        """``state`` مقدار NetState است؛ در حالت ملی/قطع صف متوقف میشود."""
        if self.user_paused:
            return False
        if self.cfg.get("auto_pause_on_national", True):
            return state == "free"
        return state != "down"

    def run_loop(
        self,
        get_state: Callable[[], str],
        *,
        stop_event: threading.Event,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        progress: Callable[[int, int, int], None] | None = None,
        idle_sleep: float = 1.0,
    ) -> None:
        """حلقهٔ بیرونی صف. طراحی شده تا داخل QThread اجرا شود."""
        def emit(kind: str, payload: dict[str, Any]) -> None:
            if on_event:
                try:
                    on_event(kind, payload)
                except Exception:
                    pass

        while not stop_event.is_set():
            if not self.should_run(get_state()):
                for item in self.pending():
                    self.set_status(item.id, "waiting_net")
                emit("paused", {"state": get_state()})
                stop_event.wait(2.0)
                continue
            items = self.pending()
            if not items:
                stop_event.wait(idle_sleep)
                continue
            self.db.execute("UPDATE downloads SET status = 'pending' WHERE status = 'waiting_net'")
            item = items[0]
            self.set_status(item.id, "running")
            emit("started", item.as_dict())
            try:
                self.process_one(
                    item,
                    progress=lambda d, t, i=item.id: progress(i, d, t) if progress else None,
                    should_continue=lambda: (not stop_event.is_set()) and self.should_run(get_state()),
                )
                current = self.get(item.id)
                if current and current.status == "done":
                    emit("finished", current.as_dict())
            except Exception as exc:
                self.db.execute(
                    "UPDATE downloads SET status = 'pending', error = ?, attempts = attempts + 1, "
                    "updated_at = ? WHERE id = ?",
                    (f"{type(exc).__name__}: {exc}", self.clock(), item.id),
                )
                emit("error", {"id": item.id, "error": str(exc)})
                # عقبنشینی نمایی کوتاه (۱، ۲، ۴، ... حداکثر ۳۰ ثانیه)
                attempts = (self.get(item.id).attempts if self.get(item.id) else 1) or 1
                stop_event.wait(min(30.0, 2 ** min(attempts - 1, 5)))
