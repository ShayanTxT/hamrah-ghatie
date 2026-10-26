"""مرحلهٔ ۲ — ذخیرهٔ کامل یک صفحهٔ وب بهصورت HTML آفلاین (همراه عکسها).

صفحه بهصورت ``index.html`` + پوشهٔ ``assets/`` ذخیره میشود. لینکها به
مسیرهای محلی بازنویسی میشوند؛ CSSها هم برای ``url(...)`` اسکن میشوند تا
عکسها و فونتهای داخل CSS نیز آفلاین شوند. فقط دانلودهایی انجام میشود که
کاربر شروع کرده (هدف ``PAGE_ASSET`` در سیاست شبکه).
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from .netpolicy import Purpose
from .persian import safe_filename

_TAG_URL_RE = re.compile(
    r'(?P<attr>src|href|poster|data-src|data-original|srcset)\s*=\s*(?P<q>["\'])(?P<val>.*?)(?P=q)',
    re.I | re.S,
)
_CSS_URL_RE = re.compile(r'url\(\s*(?P<q>["\']?)(?P<val>[^\)"\']+)(?P=q)\s*\)', re.I)
_BASE_RE = re.compile(r"<base\s[^>]*href\s*=\s*[\"']([^\"']+)[\"']", re.I)
_SKIP_PREFIXES = ("data:", "javascript:", "mailto:", "tel:", "about:", "#", "blob:")


class _NothingParser(HTMLParser):
    """فقط برای پیدا کردن charset اعلامشدهٔ صفحه."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.charset = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "meta":
            d = {k.lower(): (v or "") for k, v in attrs}
            if "charset" in d:
                self.charset = d["charset"]
            elif d.get("http-equiv", "").lower() == "content-type":
                m = re.search(r"charset=([\w-]+)", d.get("content", ""), re.I)
                if m:
                    self.charset = m.group(1)


class PageSaver:
    def __init__(self, http: Any, cfg: dict[str, Any], paths: Any) -> None:
        self.http = http
        self.cfg = cfg
        self.paths = paths
        self.max_assets = int(cfg.get("max_assets_per_page", 150))
        self.max_bytes = int(cfg.get("max_asset_bytes", 8 * 1024 * 1024))

    def _decode(self, raw: bytes, headers: dict[str, str]) -> str:
        charset = ""
        m = re.search(r"charset=([\w-]+)", headers.get("content-type", ""), re.I)
        if m:
            charset = m.group(1)
        if not charset:
            p = _NothingParser()
            try:
                p.feed(raw[:4096].decode("ascii", "ignore"))
                charset = p.charset
            except Exception:
                pass
        for enc in [charset, "utf-8", "windows-1256", "latin-1"]:
            if not enc:
                continue
            try:
                return raw.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
        return raw.decode("utf-8", "replace")

    def _local_name(self, url: str) -> str:
        path = urllib.parse.urlparse(url).path
        base = urllib.parse.unquote(Path(path).name or "asset")
        base = safe_filename(base, max_length=60)
        digest = hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()[:10]
        stem = Path(base).stem or "asset"
        suffix = Path(base).suffix[:12] or ".bin"
        return f"{digest}_{stem}{suffix}"

    @staticmethod
    def _skip(value: str) -> bool:
        v = value.strip().lower()
        return not v or any(v.startswith(p) for p in _SKIP_PREFIXES)

    def save(
        self,
        url: str,
        dest_dir: Path,
        *,
        progress: Callable[[int, int], None] | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        should_continue = should_continue or (lambda: True)
        dest_dir = Path(dest_dir)
        assets_dir = dest_dir / "assets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        with self.http.open(url, Purpose.DOWNLOAD, timeout=20.0) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            raw = resp.read(max(self.max_bytes, 2 * 1024 * 1024))
        html = self._decode(raw, headers)

        base_match = _BASE_RE.search(html)
        base_url = urllib.parse.urljoin(url, base_match.group(1)) if base_match else url

        mapping: dict[str, str] = {}      # URL مطلق -> نام فایل محلی
        downloaded: set[str] = set()
        total_bytes = len(raw)

        def resolve(value: str) -> tuple[str, str]:
            """برمیگرداند (URL مطلق، مسیر محلی نسبی)."""
            absolute = urllib.parse.urljoin(base_url, value.strip())
            if absolute.startswith("//"):
                absolute = urllib.parse.urlparse(url).scheme + ":" + absolute
            if absolute not in mapping:
                mapping[absolute] = self._local_name(absolute)
            return absolute, "assets/" + mapping[absolute]

        def fetch(absolute: str, *, css_base: str | None = None) -> None:
            nonlocal total_bytes
            if (
                absolute in downloaded
                or len(downloaded) >= self.max_assets
                or not should_continue()
                or urllib.parse.urlparse(absolute).scheme not in ("http", "https")
            ):
                return
            downloaded.add(absolute)
            try:
                data, resp_headers, _ = self.http.get_bytes(
                    absolute, Purpose.PAGE_ASSET, max_bytes=self.max_bytes, timeout=15.0
                )
            except Exception:
                return  # نبود یک عکس نباید کل صفحه را خراب کند
            target = assets_dir / mapping[absolute]
            ctype = resp_headers.get("content-type", "")
            if "css" in ctype or target.suffix.lower() == ".css":
                text = self._decode(data, resp_headers)
                text = rewrite_css(text, absolute)
                target.write_text(text, encoding="utf-8")
                data = text.encode("utf-8")
            else:
                target.write_bytes(data)
            total_bytes += len(data)
            if progress:
                progress(len(downloaded), self.max_assets)

        def rewrite_value(value: str, *, css_base: str) -> str:
            """بازنویسی یک مقدار ویژگی (شامل srcset)."""
            if self._skip(value):
                return value
            if "," in value and re.search(r"\s\d+(\.\d+)?[wx]\b", value):  # srcset
                pieces = []
                for part in value.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    bits = part.split()
                    absolute, local = resolve(bits[0])
                    fetch(absolute, css_base=css_base)
                    pieces.append(" ".join([local] + bits[1:]))
                return ", ".join(pieces)
            absolute, local = resolve(value)
            fetch(absolute, css_base=css_base)
            return local

        def rewrite_css(text: str, css_url: str) -> str:
            def sub(m: "re.Match[str]") -> str:
                val = m.group("val").strip()
                if self._skip(val) or val.startswith("assets/"):
                    return m.group(0)
                absolute = urllib.parse.urljoin(css_url, val)
                if absolute not in mapping:
                    mapping[absolute] = self._local_name(absolute)
                # فایلهای داخل CSS نسبت به پوشهٔ assets لینک میشوند
                local = mapping[absolute]
                fetch(absolute, css_base=css_url)
                return f"url({local})"
            return _CSS_URL_RE.sub(sub, text)

        def rewrite_html(text: str) -> str:
            def sub(m: "re.Match[str]") -> str:
                attr, q, val = m.group("attr"), m.group("q"), m.group("val")
                if self._skip(val):
                    return m.group(0)
                # لینکهای ناوبری (href به صفحات دیگر) نگهداری میشوند ولی عکس/ CSS دانلود میشود
                if attr.lower() == "href":
                    lower = val.lower()
                    if not any(x in lower for x in (".css", ".ico", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ttf")):
                        return m.group(0)
                return f'{attr}={q}{rewrite_value(val, css_base=base_url)}{q}'
            text = _TAG_URL_RE.sub(sub, text)
            # url(...) داخل استایلهای درونخطی
            def style_sub(m: "re.Match[str]") -> str:
                val = m.group("val").strip()
                if self._skip(val) or val.startswith("assets/"):
                    return m.group(0)
                absolute = urllib.parse.urljoin(base_url, val)
                if absolute not in mapping:
                    mapping[absolute] = self._local_name(absolute)
                fetch(absolute)
                return f"url(assets/{mapping[absolute]})"
            text = _CSS_URL_RE.sub(style_sub, text)
            return text

        final_html = rewrite_html(html)
        (dest_dir / "index.html").write_text(final_html, encoding="utf-8")
        (dest_dir / "source.url").write_text(
            f"[InternetShortcut]\nURL={url}\n", encoding="utf-8"
        )
        meta = {
            "url": url, "saved_at": datetime.now().isoformat(timespec="seconds"),
            "assets": len(downloaded), "bytes": total_bytes,
            "base_url": base_url,
        }
        (dest_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "path": str(dest_dir / "index.html"),
            "dir": str(dest_dir),
            "assets": len(downloaded),
            "bytes": total_bytes,
        }
