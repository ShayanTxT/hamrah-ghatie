"""تستهای جداگانهٔ اتصال — بدون وابستگی به Qt و قابل تزریق (injectable).

هر تست یک :class:`ProbeResult` میدهد. اجرای واقعی در :class:`DefaultProbeRunner`
است؛ در تستها یک Runner قلابی جایگزین میشود تا هیچ سوکت واقعی باز نشود.
"""
from __future__ import annotations

import os
import platform
import re
import socket
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from .http import HttpClient
from .netpolicy import Purpose

DEFAULT_TIMEOUT = 2.0


@dataclass
class ProbeResult:
    name: str
    target: str
    kind: str                 # https | tcp | dns | gateway | link
    ok: bool
    latency_ms: float = 0.0
    error: str = ""
    group: str = "other"      # external | internal | dns | gateway | link

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "target": self.target, "kind": self.kind,
            "ok": self.ok, "latency_ms": round(self.latency_ms, 1),
            "error": self.error, "group": self.group,
        }


@dataclass
class ProbeBundle:
    ts: float
    results: list[ProbeResult] = field(default_factory=list)

    def count(self, group: str) -> int:
        return sum(1 for r in self.results if r.group == group and r.ok)

    def total(self, group: str) -> int:
        return sum(1 for r in self.results if r.group == group)

    @property
    def external_ok(self) -> int:
        return self.count("external")

    @property
    def internal_ok(self) -> int:
        return self.count("internal")

    @property
    def dns_ok(self) -> int:
        return self.count("dns")

    @property
    def gateway_ok(self) -> int:
        return self.count("gateway")

    @property
    def link_ok(self) -> bool:
        return any(r.ok for r in self.results if r.group == "link")

    def summary(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "external": f"{self.external_ok}/{self.total('external')}",
            "internal": f"{self.internal_ok}/{self.total('internal')}",
            "dns": f"{self.dns_ok}/{self.total('dns')}",
            "gateway": f"{self.gateway_ok}/{self.total('gateway')}",
            "link": self.link_ok,
            "results": [r.as_dict() for r in self.results],
        }


class DefaultProbeRunner:
    """اجرای واقعی تستها با کتابخانهٔ استاندارد."""

    def __init__(self, http: HttpClient | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.http = http or HttpClient()
        self.timeout = timeout
        self._gateway_cache: str | None = None

    @staticmethod
    def _elapsed(start: float) -> float:
        return (time.monotonic() - start) * 1000.0

    def https(self, name: str, url: str, group: str) -> ProbeResult:
        start = time.monotonic()
        try:
            # هر پاسخ HTTP (حتی ۴۰۳/۵۰۲) یعنی مقصد شبکه قابل دسترس است.
            with self.http.open(url, Purpose.PROBE, method="GET", timeout=self.timeout,
                                headers={"Range": "bytes=0-0", "Cache-Control": "no-store"}) as resp:
                resp.read(1)
            return ProbeResult(name, url, "https", True, self._elapsed(start), group=group)
        except Exception as exc:  # HTTPError هم یعنی سرور پاسخ داده است
            from urllib.error import HTTPError
            if isinstance(exc, HTTPError):
                return ProbeResult(name, url, "https", True, self._elapsed(start), group=group)
            return ProbeResult(name, url, "https", False, self._elapsed(start),
                               f"{type(exc).__name__}: {exc}", group)

    def tcp(self, name: str, host: str, port: int, group: str) -> ProbeResult:
        start = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=self.timeout):
                pass
            return ProbeResult(name, f"{host}:{port}", "tcp", True, self._elapsed(start), group=group)
        except Exception as exc:
            return ProbeResult(name, f"{host}:{port}", "tcp", False, self._elapsed(start),
                               f"{type(exc).__name__}: {exc}", group)

    def dns_system(self, name: str, host: str) -> ProbeResult:
        start = time.monotonic()
        try:
            socket.setdefaulttimeout(self.timeout)
            infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            ok = bool(infos)
            return ProbeResult(name, host, "dns", ok, self._elapsed(start),
                               "" if ok else "بدون پاسخ", "dns")
        except Exception as exc:
            return ProbeResult(name, host, "dns", False, self._elapsed(start),
                               f"{type(exc).__name__}: {exc}", "dns")
        finally:
            socket.setdefaulttimeout(None)

    def dns_udp(self, name: str, server: str, domain: str) -> ProbeResult:
        """پرسش DNS خام (UDP/53) — بدون تکیه بر resolver سیستمعامل."""
        start = time.monotonic()
        query_id = int(time.time() * 1000) & 0xFFFF
        packet = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0)
        for part in domain.split("."):
            raw = part.encode("idna")
            packet += bytes([len(raw)]) + raw
        packet += b"\x00" + struct.pack("!HH", 1, 1)  # A, IN
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(self.timeout)
                s.sendto(packet, (server, 53))
                data, _ = s.recvfrom(2048)
            if len(data) < 12:
                raise ValueError("پاسخ DNS کوتاه است")
            rid, flags, _, _, _, _ = struct.unpack("!HHHHHH", data[:12])
            # rcode=0 (موفق) یا 3 (NXDOMAIN) یعنی سرویس DNS کار میکند
            ok = rid == query_id and (flags & 0x000F) in (0, 3)
            return ProbeResult(name, f"{server} ← {domain}", "dns", ok,
                               self._elapsed(start), "" if ok else "پاسخ نامعتبر", "dns")
        except Exception as exc:
            return ProbeResult(name, f"{server} ← {domain}", "dns", False,
                               self._elapsed(start), f"{type(exc).__name__}: {exc}", "dns")

    def gateway(self) -> str | None:
        """پیدا کردن دروازهٔ پیشفرض (مودم/روتر)."""
        if self._gateway_cache:
            return self._gateway_cache
        ip = self._gateway_windows() if platform.system() == "Windows" else self._gateway_unix()
        self._gateway_cache = ip
        return ip

    @staticmethod
    def _run(cmd: list[str], timeout: float = 4.0) -> str:
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
            return (out.stdout or b"").decode("utf-8", "ignore")
        except Exception:
            return ""

    def _gateway_windows(self) -> str | None:
        # PowerShell cmdletها مستقل از زبان ویندوز هستند (فارسی/انگلیسی)
        out = self._run([
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
            "| Sort-Object RouteMetric | Select-Object -First 1).NextHop",
        ])
        found = self._first_ip(out)
        if found:
            return found
        out = self._run(["route", "print", "0.0.0.0"])
        for line in out.splitlines():
            if "0.0.0.0" in line and "255.255.255.255" not in line:
                found = self._first_ip(line)
                if found:
                    return found
        return None

    def _gateway_unix(self) -> str | None:
        out = self._run(["ip", "route", "show", "default"])
        found = self._first_ip(out.replace("via ", " "))
        return found

    @staticmethod
    def _valid_gateway(candidate: str) -> bool:
        parts = candidate.split(".")
        if not all(0 <= int(p) <= 255 for p in parts):
            return False
        if candidate in ("0.0.0.0", "255.255.255.255", "127.0.0.1"):
            return False
        # 169.254.x.x یعنی DHCP جواب نداده؛ روتر واقعی نیست
        if parts[0] == "169" and parts[1] == "254":
            return False
        return True

    @classmethod
    def _first_ip(cls, text: str) -> str | None:
        for match in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", text or ""):
            candidate = match.group(1)
            if cls._valid_gateway(candidate):
                return candidate
        return None

    def gateway_probe(self) -> ProbeResult:
        """تست مودم/روتر با سقف زمانی کوتاه (در قطعی کامل نباید چرخه را کند کند)."""
        start = time.monotonic()
        gw = self.gateway()
        if not gw:
            return ProbeResult("مودم/روتر", "دروازهٔ پیشفرض", "gateway", False,
                               self._elapsed(start), "دروازهای پیدا نشد", "gateway")
        short = max(0.4, min(self.timeout, 1.0))
        # دو پورت رایج بهصورت همزمان تا منتظر چهار timeout پشتسرهم نمانیم
        original = self.timeout
        try:
            self.timeout = short
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.tcp, "مودم/روتر", gw, port, "gateway")
                           for port in (80, 443)]
                for fut in as_completed(futures):
                    r = fut.result()
                    if r.ok:
                        r.latency_ms = self._elapsed(start)
                        return r
        finally:
            self.timeout = original
        ping_ok = self._ping(gw)
        return ProbeResult("مودم/روتر", gw, "gateway", ping_ok, self._elapsed(start),
                           "" if ping_ok else "پاسخی از مودم نیامد", "gateway")

    def _ping(self, host: str) -> bool:
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "1", "-w", "900", host]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", host]
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=3.0, check=False)
            return out.returncode == 0
        except Exception:
            return False

    def link_probe(self) -> ProbeResult:
        """آیا اصلاً کارت شبکهای وصل است؟"""
        start = time.monotonic()
        try:
            import psutil  # وابستگی سبک، در بستهبندی موجود است
            stats = psutil.net_if_stats()
            ok = any(v.isup and not name.lower().startswith(("lo", "loopback"))
                     for name, v in stats.items())
        except Exception:
            try:
                infos = socket.getaddrinfo(socket.gethostname(), None)
                ok = any(not info[4][0].startswith("127.") for info in infos)
            except Exception:
                ok = False
        return ProbeResult("کارت شبکه", "وضعیت لینک", "link", ok, self._elapsed(start),
                           "" if ok else "هیچ کارت شبکهٔ فعالی پیدا نشد", "link")


def run_all_probes(
    settings: dict[str, Any],
    runner: Any | None = None,
    *,
    clock: Callable[[], float] = time.time,
    parallel: bool = True,
) -> ProbeBundle:
    """اجرای همهٔ تستها و ساخت یک :class:`ProbeBundle`.

    ``runner`` برای تستها قابل تزریق است؛ متدهایش همان امضای
    :class:`DefaultProbeRunner` را دارند.
    """
    runner = runner or DefaultProbeRunner(timeout=float(settings.get("probe_timeout", DEFAULT_TIMEOUT)))
    jobs: list[tuple[str, Callable[[], ProbeResult]]] = []

    for url in settings.get("internal_hosts", []):
        host = urlparse(url).netloc or url
        jobs.append((f"داخلی {host}", lambda u=url, h=host: runner.https(f"سایت داخلی {h}", u, "internal")))
        jobs.append((f"tcp {host}:443", lambda h=host: runner.tcp(f"اتصال TCP {h}", h, 443, "internal")))

    for url in settings.get("external_urls", []):
        host = urlparse(url).netloc or url
        jobs.append((f"خارجی {host}", lambda u=url, h=host: runner.https(f"سایت خارجی {h}", u, "external")))

    for host, port in settings.get("external_tcp", []):
        jobs.append((f"tcp {host}:{port}", lambda h=host, p=port: runner.tcp(f"اتصال TCP {h}", h, int(p), "external")))

    domain = settings.get("dns_test_domain", "example.com")
    jobs.append(("dns سیستم", lambda: runner.dns_system("حل نام توسط ویندوز", domain)))
    for idx, server in enumerate(settings.get("dns_servers", [])):
        jobs.append((f"dns {server}", lambda s=server: runner.dns_udp(f"پرسش مستقیم DNS {s}", s, domain)))

    jobs.append(("گیتوی", runner.gateway_probe))
    jobs.append(("لینک", runner.link_probe))

    results: list[ProbeResult] = []
    if parallel:
        with ThreadPoolExecutor(max_workers=min(20, max(2, len(jobs)))) as pool:
            futures = {pool.submit(fn): label for label, fn in jobs}
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as exc:  # نباید یک تست خراب کل چرخه را متوقف کند
                    results.append(ProbeResult(futures[fut], "?", "error", False, 0.0,
                                               f"{type(exc).__name__}: {exc}"))
    else:
        for label, fn in jobs:
            try:
                results.append(fn())
            except Exception as exc:
                results.append(ProbeResult(label, "?", "error", False, 0.0,
                                           f"{type(exc).__name__}: {exc}"))
    # ترتیب ثابت برای نمایش پایدار در UI
    order = {"external": 0, "internal": 1, "dns": 2, "gateway": 3, "link": 4, "other": 5}
    results.sort(key=lambda r: (order.get(r.group, 5), r.name))
    return ProbeBundle(ts=clock(), results=results)
