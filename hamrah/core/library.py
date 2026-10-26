"""مرحلهٔ ۳ — کتابخانهٔ آفلاین: ایندکس تماممتن فایلها + ZIMهای ویکیپدیا.

همهچیز در SQLite FTS5 ذخیره میشود. نکتهٔ کلیدی: ستونهای FTS حاوی متن
**نرمالشده** هستند (ی/ي، ک/ك، نیمفاصله، اعراب، ارقام) و پرسوجو هم دقیقاً
همان نرمالسازی را میبیند؛ بنابراین جستجوی فارسی درست کار میکند.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from .db import Database
from .persian import build_fts_query, fts_index_text, normalize, truncate
from .textutil import SUPPORTED, extract_file_text, strip_html
from .zim_reader import ZimArchive, ZimError, open_zim

MAX_FILE_BYTES = 60 * 1024 * 1024


@dataclass
class SearchResult:
    doc_id: int
    path: str
    title: str
    source: str
    kind: str
    snippet: str
    score: float
    content: str = ""

    @property
    def source_label(self) -> str:
        if self.source.startswith("zim:"):
            return "ویکیپدیای آفلاین"
        if self.source.startswith("page:"):
            return "صفحهٔ ذخیرهشده"
        return "فایلهای من"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.doc_id, "path": self.path, "title": self.title,
            "source": self.source, "source_label": self.source_label,
            "kind": self.kind, "snippet": self.snippet, "score": self.score,
        }


class Library:
    def __init__(self, db: Database, cfg: dict[str, Any], paths: Any) -> None:
        self.db = db
        self.cfg = cfg
        self.paths = paths
        self.max_chars = int(cfg.get("max_index_chars", 200_000))

    # ---------- ایندکسگذاری ----------
    def _upsert(
        self,
        *,
        path: str,
        title: str,
        content: str,
        kind: str,
        source: str,
        size: int = 0,
        mtime: float = 0.0,
    ) -> int:
        content = (content or "")[: self.max_chars]
        title_norm = fts_index_text(title)
        body_norm = fts_index_text(content)
        now = time.time()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
            if row:
                doc_id = int(row["id"])
                conn.execute(
                    "UPDATE documents SET title=?, kind=?, source=?, size=?, mtime=?, content=?, indexed_at=? WHERE id=?",
                    (title, kind, source, size, mtime, content, now, doc_id),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO documents(path, title, kind, source, size, mtime, content, indexed_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (path, title, kind, source, size, mtime, content, now),
                )
                doc_id = int(cur.lastrowid)
            conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
            conn.execute(
                "INSERT INTO documents_fts(rowid, title_norm, body_norm, path) VALUES(?, ?, ?, ?)",
                (doc_id, title_norm, body_norm, path),
            )
        return doc_id

    def remove_document(self, path: str) -> None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
            if not row:
                return
            conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (row["id"],))
            conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))

    def index_file(self, path: Path, *, source: str | None = None, force: bool = False) -> bool:
        """یک فایل را ایندکس میکند. ``False`` یعنی نیازی به بهروزرسانی نبود."""
        path = Path(path)
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            return False
        if path.stat().st_size > MAX_FILE_BYTES:
            return False
        mtime = path.stat().st_mtime
        if not force:
            row = self.db.query("SELECT mtime FROM documents WHERE path = ?", (str(path),))
            if row and abs(float(row[0]["mtime"]) - mtime) < 0.5:
                return False
        text, kind = extract_file_text(path, max_chars=self.max_chars)
        if not text.strip():
            # حتی فایل بدون متن قابل استخراج را با عنوانش ایندکس میکنیم
            text = path.stem
        src = source or ("page:" + str(path.parent) if (path.parent / "meta.json").exists() else "file")
        self._upsert(path=str(path), title=path.stem, content=text, kind=kind,
                     source=src, size=path.stat().st_size, mtime=mtime)
        return True

    def scan_folder(
        self,
        folder: Path | None = None,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        """اسکن پوشهٔ کتابخانه (پیشفرض ``data/library``)."""
        folder = Path(folder or self.paths.library)
        should_continue = should_continue or (lambda: True)
        files: list[Path] = []
        for p in folder.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in SUPPORTED:
                continue
            if "zim" in p.parts or p.name.startswith("."):
                continue
            files.append(p)
        added = skipped = errors = 0
        for i, p in enumerate(files, 1):
            if not should_continue():
                break
            try:
                added += int(self.index_file(p))
            except Exception:
                errors += 1
            if progress:
                progress(i, len(files), p.name)
        self._sync_missing(files)
        return {"total": len(files), "added": added, "skipped": skipped, "errors": errors}

    def _sync_missing(self, existing: list[Path]) -> None:
        """حذف ایندکس فایلهایی که از دیسک پاک شدهاند (فقط فایلهای شخصی)."""
        known = set(str(p) for p in existing)
        rows = self.db.query("SELECT path FROM documents WHERE source NOT LIKE 'zim:%'")
        for row in rows:
            if row["path"] not in known and not row["path"].startswith("zim://"):
                self.remove_document(row["path"])

    def index_zim(
        self,
        zim_path: Path,
        *,
        max_articles: int | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """وارد کردن یک فایل ZIM و ایندکس کردن مقالههایش.

        برای ZIMهای خیلی بزرگ (چند میلیون مقاله) پیشفرض فقط
        ``zim_max_articles`` مقاله ایندکس میشود تا حجم دیتابیس و زمان
        قابل قبول بماند؛ عنوان بقیه همچنان از خود ZIM قابل جستجو است.
        """
        zim_path = Path(zim_path)
        should_continue = should_continue or (lambda: True)
        limit = int(max_articles or self.cfg.get("zim_max_articles", 5000))
        source = "zim:" + str(zim_path)
        archive = open_zim(zim_path)
        try:
            candidates = []
            for e in archive.entries():
                if e.namespace not in ("A", "C", "-"):
                    continue
                if e.is_html or e.is_redirect or e.path.lower().endswith((".html", ".htm")):
                    candidates.append(e)
            total = min(len(candidates), limit)
            tag = hashlib.sha1(str(zim_path).encode("utf-8")).hexdigest()[:8]
            indexed = errors = 0
            for i, e in enumerate(candidates[:limit], 1):
                if not should_continue():
                    break
                try:
                    raw, mime = archive.read_entry(e)
                    text = strip_html(raw.decode("utf-8", "replace"))
                    if len(text) < 30:
                        continue
                    virtual = f"zim://{tag}/{e.full_path}"
                    self._upsert(
                        path=virtual, title=e.title or e.path, content=text[:50_000],
                        kind="zim", source=source, size=len(raw), mtime=0.0,
                    )
                    indexed += 1
                except (ZimError, KeyError, OSError, UnicodeError):
                    errors += 1
                if progress and (i % 10 == 0 or i == total):
                    progress(i, total, e.title)
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO zim_archives(path, title, entry_count, indexed_count, added_at) "
                    "VALUES(?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET "
                    "title=excluded.title, entry_count=excluded.entry_count, indexed_count=excluded.indexed_count",
                    (str(zim_path), archive.title, archive.entry_count, indexed, time.time()),
                )
            return {
                "title": archive.title, "entries": archive.entry_count,
                "candidates": len(candidates), "indexed": indexed,
                "errors": errors, "limited": len(candidates) > limit,
            }
        finally:
            archive.close()

    def remove_zim(self, zim_path: Path) -> int:
        source = "zim:" + str(Path(zim_path))
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT id FROM documents WHERE source = ?", (source,)).fetchall()
            for r in rows:
                conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (r["id"],))
            conn.execute("DELETE FROM documents WHERE source = ?", (source,))
            conn.execute("DELETE FROM zim_archives WHERE path = ?", (str(Path(zim_path)),))
        return len(rows)

    # ---------- جستجو ----------
    def search(self, query: str, *, limit: int = 30, source: str | None = None) -> list[SearchResult]:
        q = (query or "").strip()
        if not q:
            return self.recent(limit=limit)
        source_filter = " AND d.source = ?" if source else ""
        base_params: tuple[Any, ...] = (source,) if source else ()
        sql = (
            "SELECT d.id, d.path, d.title, d.source, d.kind, d.content, "
            "snippet(documents_fts, 1, '«', '»', '…', 18) AS snip, "
            "bm25(documents_fts, 4.0, 1.0, 0.0) AS rank "
            "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
            "WHERE documents_fts MATCH ?" + source_filter +
            " ORDER BY rank LIMIT ?"
        )
        results: list[SearchResult] = []
        for operator in ("AND", "OR"):
            fts_query = build_fts_query(q, operator=operator)
            if not fts_query:
                break
            try:
                rows = self.db.query(sql, (fts_query, *base_params, limit))
            except Exception:
                # پرسوجوی عجیب (مثلاً فقط علائم) -> نتیجهای نداریم
                return []
            if rows:
                results = [SearchResult(
                    doc_id=int(r["id"]), path=r["path"], title=r["title"],
                    source=r["source"], kind=r["kind"],
                    snippet=truncate(r["snip"] or truncate(r["content"], 180), 260),
                    score=float(r["rank"]),
                    content=r["content"][:4000],
                ) for r in rows]
                break
        return results

    def recent(self, *, limit: int = 20) -> list[SearchResult]:
        rows = self.db.query(
            "SELECT id, path, title, source, kind, content FROM documents ORDER BY indexed_at DESC LIMIT ?",
            (limit,),
        )
        return [SearchResult(int(r["id"]), r["path"], r["title"], r["source"], r["kind"],
                             truncate(r["content"], 200), 0.0, r["content"][:4000]) for r in rows]

    def get_by_path(self, path: str) -> dict[str, Any] | None:
        rows = self.db.query("SELECT * FROM documents WHERE path = ?", (path,))
        return dict(rows[0]) if rows else None

    def zim_list(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query("SELECT * FROM zim_archives ORDER BY added_at DESC")]

    def stats(self) -> dict[str, int]:
        return {
            "documents": int(self.db.scalar("SELECT COUNT(*) FROM documents") or 0),
            "zim_files": int(self.db.scalar("SELECT COUNT(*) FROM zim_archives") or 0),
            "fts_rows": int(self.db.scalar("SELECT COUNT(*) FROM documents_fts") or 0),
        }
