"""مرحلهٔ ۳ — خوانندهٔ بومی ZIM (بدون نیاز به نصب Kiwix).

پیادهسازی خالص پایتون از فرمت ZIM (نگارش ۵ و ۶) بر اساس مستندات openZIM:
https://wiki.openzim.org/wiki/ZIM_file_format

پشتیبانی: کلاسترهای بدون فشردهسازی، zlib، bzip2، LZMA2/XZ و Zstandard،
کلاسترهای extended (آفست ۸ بایتی)، ورودیهای redirect/linktarget و
namespaceهای قدیمی (A/I/M/X) و جدید («-»).

اگر به فرمت ناشناختهای برخورد کردیم، از بایندینگ ``libzim`` (که ویندوز-باینری
هم دارد) بهعنوان مسیر پشتیبان استفاده میشود.
"""
from __future__ import annotations

import bz2
import io
import lzma
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

MAGIC = 0x044D495A
REDIRECT = 0xFFFF
LINKTARGET = 0xFFFE
DELETED = 0xFFFD


class ZimError(Exception):
    pass


@dataclass(frozen=True)
class ZimEntry:
    index: int
    namespace: str
    path: str
    full_path: str
    title: str
    mime: str
    cluster: int | None
    blob: int | None
    redirect_index: int | None

    @property
    def is_redirect(self) -> bool:
        return self.redirect_index is not None

    @property
    def is_content(self) -> bool:
        return self.cluster is not None and self.blob is not None

    @property
    def is_html(self) -> bool:
        return "html" in self.mime.lower()


class ZimArchive:
    """یک فایل ZIM فقطخواندنی. منابع بهصورت تنبل (lazy) خوانده میشوند."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ZimError("فایل ZIM پیدا نشد")
        self._fh = self.path.open("rb")
        self._read_header()

    # ---------- ساختار فایل ----------
    def _read_header(self) -> None:
        fh = self._fh
        header = fh.read(80)
        if len(header) < 80 or struct.unpack_from("<I", header, 0)[0] != MAGIC:
            raise ZimError("این فایل ZIM معتبر نیست (امضای فایل اشتباه است)")
        self.major, self.minor = struct.unpack_from("<HH", header, 4)
        self.uuid = header[8:24]
        self.entry_count = struct.unpack_from("<I", header, 24)[0]
        self.cluster_count = struct.unpack_from("<I", header, 28)[0]
        self.path_ptr_pos = struct.unpack_from("<Q", header, 32)[0]
        self.title_ptr_pos = struct.unpack_from("<Q", header, 40)[0]
        self.cluster_ptr_pos = struct.unpack_from("<Q", header, 48)[0]
        self.mime_list_pos = struct.unpack_from("<Q", header, 56)[0]
        self.main_page = struct.unpack_from("<I", header, 64)[0]
        self.checksum_pos = struct.unpack_from("<Q", header, 72)[0]
        self.file_size = self.path.stat().st_size

        fh.seek(self.mime_list_pos)
        raw = fh.read(64 * 1024)
        mimes: list[str] = []
        for piece in raw.split(b"\x00"):
            if not piece:
                break
            mimes.append(piece.decode("utf-8", "replace"))
        self.mimes = mimes

        fh.seek(self.path_ptr_pos)
        self._path_ptrs = list(struct.unpack_from(
            f"<{self.entry_count}Q", fh.read(8 * self.entry_count), 0
        )) if self.entry_count else []
        fh.seek(self.cluster_ptr_pos)
        self._cluster_ptrs = list(struct.unpack_from(
            f"<{self.cluster_count}Q", fh.read(8 * self.cluster_count), 0
        )) if self.cluster_count else []

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self) -> "ZimArchive":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ---------- متادیتا ----------
    def _metadata_raw(self, name: str) -> bytes:
        try:
            return self.read_path(f"M/{name}")[0]
        except (KeyError, ZimError):
            return b""

    @property
    def title(self) -> str:
        return (self._metadata_raw("Title").decode("utf-8", "ignore")
                or self._metadata_raw("Name").decode("utf-8", "ignore")
                or self.path.stem)

    @property
    def language(self) -> str:
        return self._metadata_raw("Language").decode("utf-8", "ignore") or "?"

    @property
    def main_path(self) -> str | None:
        if self.main_page == 0xFFFFFFFF or self.main_page >= self.entry_count:
            return None
        try:
            return self.entry(self.main_page).full_path
        except ZimError:
            return None

    # ---------- دایرکتوری ----------
    @lru_cache(maxsize=4096)  # noqa: B019 - آبجکت per-instance است و همراه فایل بسته میشود
    def _dirent(self, index: int) -> ZimEntry:
        if index < 0 or index >= self.entry_count:
            raise ZimError("شمارهٔ ورودی خارج از محدوده است")
        self._fh.seek(self._path_ptrs[index])
        data = self._fh.read(8192)
        if len(data) < 16:
            raise ZimError("ورودی دایرکتوری ناقص است")
        mime_id, param_len = struct.unpack_from("<H", data, 0)[0], data[2]
        namespace = chr(data[3])
        strings_at = 16
        cluster = blob = redirect_index = None
        if mime_id == REDIRECT:
            redirect_index = struct.unpack_from("<I", data, 8)[0]
            strings_at = 12
        elif mime_id in (LINKTARGET, DELETED):
            strings_at = 8
        else:
            cluster, blob = struct.unpack_from("<II", data, 8)

        parts = data[strings_at:].split(b"\x00", 2)
        path = parts[0].decode("utf-8", "replace") if parts else ""
        title = parts[1].decode("utf-8", "replace") if len(parts) > 1 else ""
        # namespace قدیمی در مسیر میآید؛ namespace جدید («-») حذف میشود
        full_path = path if namespace in ("-", "\x00") else f"{namespace}/{path}"
        mime = self.mimes[mime_id] if 0 <= mime_id < len(self.mimes) else "application/octet-stream"
        return ZimEntry(index, namespace, path, full_path, title or path,
                        mime, cluster, blob, redirect_index)

    def entry(self, index: int) -> ZimEntry:
        return self._dirent(index)

    def entries(self) -> Iterator[ZimEntry]:
        for i in range(self.entry_count):
            yield self._dirent(i)

    def _build_path_index(self) -> dict[str, int]:
        index: dict[str, int] = {}
        for e in self.entries():
            index.setdefault(e.full_path, e.index)
            if e.path != e.full_path:
                index.setdefault(e.path, e.index)
            # حذف پیشوند namespace برای جستجوی راحتتر
            if "/" in e.full_path:
                index.setdefault(e.full_path.split("/", 1)[1], e.index)
        return index

    def find(self, path: str) -> ZimEntry | None:
        if not hasattr(self, "_path_index"):
            self._path_index = self._build_path_index()
        variants = [path, path.lstrip("/")]
        if "/" not in path:
            variants += [f"A/{path}", f"C/{path}", f"-/{path}"]
        for v in variants:
            idx = self._path_index.get(v)
            if idx is not None:
                return self._dirent(idx)
        return None

    # ---------- محتوا ----------
    @lru_cache(maxsize=6)  # noqa: B019
    def _cluster_data(self, index: int) -> bytes:
        if index < 0 or index >= self.cluster_count:
            raise ZimError("شمارهٔ کلاستر نامعتبر است")
        start = self._cluster_ptrs[index]
        end = (self._cluster_ptrs[index + 1] if index + 1 < self.cluster_count
               else (self.checksum_pos or self.file_size))
        if end <= start or end > self.file_size:
            end = self.file_size
        self._fh.seek(start)
        raw = self._fh.read(end - start)
        if not raw:
            raise ZimError("کلاستر خالی است")
        info = raw[0]
        compression = info & 0x0F
        offset_size = 8 if (info & 0x10) and self.major >= 6 else 4
        payload = raw[1:]
        if compression in (0, 1):
            data = payload
        elif compression == 2:
            data = zlib.decompress(payload)
        elif compression == 3:
            data = bz2.decompress(payload)
        elif compression == 4:
            try:
                data = lzma.decompress(payload, format=lzma.FORMAT_XZ)
            except lzma.LZMAError:
                data = lzma.decompress(payload, format=lzma.FORMAT_ALONE)
        elif compression == 5:
            try:
                import zstandard as zstd
                data = zstd.ZstdDecompressor().stream_reader(io.BytesIO(payload)).read()
            except ImportError as exc:
                raise ZimError("برای خواندن این ZIM به بستهٔ zstandard نیاز است") from exc
        else:
            raise ZimError(f"نوع فشردهسازی ناشناخته: {compression}")
        return data

    def _blob(self, cluster: int, blob: int) -> bytes:
        data = self._cluster_data(cluster)
        offset_size = 8 if (self.major >= 6 and (self._cluster_info(cluster) & 0x10)) else 4
        fmt = "<Q" if offset_size == 8 else "<I"
        if len(data) < offset_size:
            raise ZimError("جدول آفست کلاستر ناقص است")
        first = struct.unpack_from(fmt, data, 0)[0]
        num_offsets = first // offset_size
        if num_offsets < 2 or blob >= num_offsets - 1:
            raise ZimError("شمارهٔ بلاب نامعتبر است")
        start = struct.unpack_from(fmt, data, blob * offset_size)[0]
        end = struct.unpack_from(fmt, data, (blob + 1) * offset_size)[0]
        if end < start or end > len(data):
            raise ZimError("محدودهٔ بلاب نامعتبر است")
        return data[start:end]

    def _cluster_info(self, index: int) -> int:
        self._fh.seek(self._cluster_ptrs[index])
        return self._fh.read(1)[0]

    def read_entry(self, entry: ZimEntry, *, _depth: int = 0) -> tuple[bytes, str]:
        """خواندن محتوای یک ورودی (با دنبال کردن redirect)."""
        if _depth > 16:
            raise ZimError("حلقهٔ نامتناهی در redirectها")
        if entry.is_redirect and entry.redirect_index is not None:
            return self.read_entry(self._dirent(entry.redirect_index), _depth=_depth + 1)
        if not entry.is_content or entry.cluster is None or entry.blob is None:
            raise ZimError("این ورودی محتوایی ندارد")
        try:
            return self._blob(entry.cluster, entry.blob), entry.mime
        except ZimError:
            # پشتیبان: بایندینگ libzim (در بستهٔ ویندوزی موجود است)
            return self._libzim_read(entry.full_path)

    def read_path(self, path: str) -> tuple[bytes, str]:
        entry = self.find(path)
        if entry is None:
            raise KeyError(f"ورودی پیدا نشد: {path}")
        return self.read_entry(entry)

    # ---------- جستجو ----------
    def search_titles(self, query: str, *, limit: int = 30) -> list[ZimEntry]:
        from .persian import normalize
        needle = normalize(query)
        out: list[ZimEntry] = []
        for e in self.entries():
            if not e.is_html and not e.namespace in ("A", "-"):
                continue
            if needle in normalize(e.title) or needle in normalize(e.path):
                out.append(e)
                if len(out) >= limit:
                    break
        return out

    def _libzim_read(self, full_path: str) -> tuple[bytes, str]:
        """خواندن محتوا با libzim وقتی خوانندهٔ داخلی از فرمتی پشتیبانی نکرد."""
        try:
            from libzim.reader import Archive  # type: ignore
            archive = Archive(str(self.path))
            for candidate in (full_path, full_path.split("/", 1)[-1]):
                try:
                    item = archive.get_entry_by_path(candidate).get_item()
                    return bytes(item.content), item.mimetype
                except Exception:
                    continue
        except ImportError:
            pass
        raise ZimError("خواندن محتوای این مقاله ممکن نشد (فرمت فشردهسازی پشتیبانی نمیشود)")

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path), "title": self.title, "language": self.language,
            "entries": self.entry_count, "clusters": self.cluster_count,
            "main": self.main_path, "version": f"{self.major}.{self.minor}",
        }


def open_zim(path: str | Path) -> ZimArchive:
    """باز کردن ZIM. خطاهای فنی به پیام فارسی تبدیل میشوند."""
    return ZimArchive(path)
