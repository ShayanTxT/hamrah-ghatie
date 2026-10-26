"""استخراج متن خالص از PDF / HTML / DOCX / فایلهای متنی."""
from __future__ import annotations

import html
import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".html", ".htm",
             ".pdf", ".docx", ".epub", ".xml", ".rst", ".py", ".js", ".css"}

_SCRIPT_RE = re.compile(r"<(script|style|noscript|svg)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u200c\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


class _TextExtractor(HTMLParser):
    """تبدیل HTML به متن قابل جستجو (بدون وابستگی خارجی)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "section"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = _WS_RE.sub(" ", raw)
        raw = _NL_RE.sub("\n\n", raw)
        return "\n".join(line.strip() for line in raw.splitlines()).strip()


def strip_html(content: str) -> str:
    """حذف تگها و اسکریپتها؛ مناسب برای ایندکس جستجو."""
    cleaned = _SCRIPT_RE.sub(" ", content or "")
    parser = _TextExtractor()
    try:
        parser.feed(cleaned)
        parser.close()
        return parser.text()
    except Exception:
        return html.unescape(_TAG_RE.sub(" ", cleaned))


def decode_bytes(raw: bytes, hint: str = "") -> str:
    """چند کدگذاری رایج فارسی را امتحان میکند."""
    encodings = ["utf-8-sig", "utf-8", "windows-1256", "cp1256", "iso-8859-6", "latin-1"]
    m = re.search(r"charset=([\w-]+)", hint or "", re.I)
    if m:
        encodings.insert(0, m.group(1))
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def extract_pdf(path: Path, *, max_pages: int = 400) -> str:
    """استخراج متن PDF با pypdf (کتابخانهٔ خالص پایتون، داخل بستهبندی موجود است)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in list(reader.pages)[:max_pages]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)
    except Exception:
        return ""  # PDF خراب/رمزدار -> فقط عنوان ایندکس میشود


def extract_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return strip_html(xml)
    except Exception:
        return ""


def extract_file_text(path: Path, *, max_chars: int = 200_000) -> tuple[str, str]:
    """برمیگرداند (متن، نوع محتوا)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)[:max_chars], "pdf"
    if suffix == ".docx":
        return extract_docx(path)[:max_chars], "docx"
    if suffix in (".epub",):
        try:
            with zipfile.ZipFile(path) as z:
                texts = [strip_html(decode_bytes(z.read(n))) for n in z.namelist()
                         if n.lower().endswith((".html", ".htm", ".xhtml"))][:80]
            return "\n".join(texts)[:max_chars], "epub"
        except Exception:
            return "", "epub"
    raw = path.read_bytes()[: max_chars * 4]
    text = decode_bytes(raw)
    if suffix in (".html", ".htm", ".xml", ".svg"):
        return strip_html(text)[:max_chars], "html"
    return text[:max_chars], "text"
