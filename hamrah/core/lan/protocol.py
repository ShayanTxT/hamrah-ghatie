"""پیامها و منطق انتقال فایل قابلادامه در شبکهٔ محلی."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..persian import safe_filename

CHAT = "chat"
FILE_OFFER = "file_offer"
FILE_ACCEPT = "file_accept"
FILE_REJECT = "file_reject"
FILE_CHUNK = "file_chunk"
FILE_DONE = "file_done"
FILE_ERROR = "file_error"
PING = "ping"
PONG = "pong"

CHUNK_SIZE = 256 * 1024


@dataclass
class FileOffer:
    file_id: str
    name: str
    size: int
    sha256: str
    peer_id: str = ""
    direction: str = "in"      # in = دریافتی، out = ارسالی
    offset: int = 0
    path: str = ""
    approved: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "file_id": self.file_id, "name": self.name, "size": self.size,
            "sha256": self.sha256,
            "direction": self.direction, "offset": self.offset,
            "path": self.path, "approved": self.approved, "error": self.error,
        }


def make_file_id(name: str, size: int, digest: str) -> str:
    """شناسهای پایدار برای ادامهٔ دانلود حتی بعد از قطع ارتباط."""
    return hashlib.sha256(f"{name}|{size}|{digest}".encode("utf-8")).hexdigest()[:24]


def sha256_file(path: Path, *, progress: Callable[[int, int], None] | None = None) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
            done += len(block)
            if progress:
                progress(done, total)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> bool:
    if not expected:
        return True
    return sha256_file(Path(path)) == expected


def incoming_filename(name: str, file_id: str) -> str:
    """نام امن فایل دریافتی؛ در صورت تکراری شدن پسوند هش اضافه میشود."""
    safe = safe_filename(name)
    p = Path(safe)
    return f"{p.stem}.{file_id[:6]}{p.suffix or '.bin'}"
