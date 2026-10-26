"""تست سیاست «هیچ درخواست شبکهای جز سه مورد مجاز».

این تستها سورسکد را اسکن میکنند تا مطمئن شویم هیچ وابستگی خارجی،
تله\u200cمتری، بررسی آپدیت یا CDN به برنامه اضافه نشده است.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hamrah.core.errors import AppError
from hamrah.core.http import HttpClient
from hamrah.core.netpolicy import NetworkGuard, Purpose

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "hamrah" / "core"

FORBIDDEN_IMPORTS = ("import requests", "import httpx", "import aiohttp",
                     "import urllib3", "from requests", "from httpx",
                     "import sentry_sdk", "import boto3", "import telemetry")
FORBIDDEN_URLS = ("google-analytics", "googletagmanager", "sentry.io",
                  "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com",
                  "fonts.googleapis.com", "api.github.com/repos/.*/releases/latest")
ALLOWED_SOCKET_MODULES = {
    "http.py", "probes.py", "crypto.py", "discovery.py", "node.py",
}


def test_no_forbidden_imports_or_urls():
    problems = []
    # فقط سورسهای خودمان اسکن میشوند (نه پوشههای build/dist ساخته PyInstaller)
    targets = list(CORE.rglob("*.py")) + list((ROOT / "hamrah" / "ui").rglob("*.py"))
    targets += list((ROOT / "tools").rglob("*.py")) + [ROOT / "run.py"]
    for p in targets:
        text = p.read_text("utf-8", "ignore")
        for token in FORBIDDEN_IMPORTS:
            if token in text:
                problems.append(f"{p.name}: {token}")
        for token in FORBIDDEN_URLS[:7]:
            if token in text:
                problems.append(f"{p.name}: {token}")
    assert not problems, problems


def test_only_allowed_modules_open_sockets():
    problems = []
    for p in CORE.rglob("*.py"):
        text = p.read_text("utf-8", "ignore")
        if ("socket.socket(" in text or "socket.create_connection(" in text
                or "urlopen(" in text or "getaddrinfo(" in text):
            if p.name not in ALLOWED_SOCKET_MODULES:
                problems.append(p.name)
    assert not problems, problems


def test_guard_rejects_unknown_purpose():
    guard = NetworkGuard()
    with pytest.raises(AppError):
        guard.authorize("https://example.com", "some-random-purpose")  # type: ignore[arg-type]


def test_local_ai_is_loopback_only():
    guard = NetworkGuard()
    guard.authorize("http://127.0.0.1:18081/health", Purpose.LOCAL_AI)
    guard.authorize("http://localhost:18081/completion", Purpose.LOCAL_AI)
    with pytest.raises(AppError):
        guard.authorize("http://192.168.1.5:18081/health", Purpose.LOCAL_AI)
    with pytest.raises(AppError):
        guard.authorize("https://api.openai.com/v1/chat", Purpose.LOCAL_AI)


def test_guard_records_and_assert_policy():
    guard = NetworkGuard()
    guard.authorize("https://www.google.com/generate_204", Purpose.PROBE)
    guard.authorize("https://example.com/file.zip", Purpose.DOWNLOAD)
    guard.authorize("http://127.0.0.1:18081/health", Purpose.LOCAL_AI)
    assert len(guard.records) == 3
    guard.assert_policy({Purpose.PROBE, Purpose.DOWNLOAD, Purpose.LOCAL_AI})
    with pytest.raises(AssertionError):
        guard.assert_policy({Purpose.PROBE})


class FakeResp(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.status = 200
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class FakeOpener:
    def __init__(self):
        self.urls: list[str] = []

    def open(self, req, timeout=None):
        self.urls.append(req.full_url)
        return FakeResp(b"ok")


def test_http_client_passes_through_guard():
    guard = NetworkGuard()
    client = HttpClient(guard)
    client.opener = FakeOpener()
    data, headers, status = client.get_bytes(
        "http://127.0.0.1:18081/health", Purpose.LOCAL_AI, timeout=1)
    assert data == b"ok"
    assert guard.records[0].purpose is Purpose.LOCAL_AI
