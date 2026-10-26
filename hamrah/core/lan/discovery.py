"""کشف خودکار کامپیوترهای همسایه با UDP broadcast (بدون اینترنت).

پیامها حاوی HMAC ساختهشده از کد جفتسازی هستند؛ بنابراین دستگاههایی که کد
متفاوتی دارند، حضور شما را نمیبینند. برچسب زمانی هم جلوی replay را میگیرد.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from .crypto import Identity, code_to_psk, sign_discovery, verify_discovery

PEER_TTL = 18.0
ANNOUNCE_INTERVAL = 4.0


@dataclass
class Peer:
    device_id: str
    name: str
    host: str
    port: int
    version: str = ""
    last_seen: float = 0.0
    fingerprint: str = ""      # بعد از handshake پر میشود

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.device_id, "name": self.name, "host": self.host,
            "port": self.port, "last_seen": self.last_seen,
            "fingerprint": self.fingerprint,
        }


class Discovery:
    def __init__(
        self,
        cfg: dict[str, Any],
        identity: Identity,
        *,
        on_update: Callable[[list[Peer]], None] | None = None,
        on_message: Callable[[str], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.identity = identity
        self.code = str(cfg.get("pairing_code", ""))
        self.psk = code_to_psk(self.code) if self.code else b""
        self.udp_port = int(cfg.get("lan_udp_port", 54545))
        self.tcp_port = int(cfg.get("lan_tcp_port", 54546))
        self.on_update = on_update
        self.on_message = on_message
        self._peers: dict[str, Peer] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._sock: socket.socket | None = None

    # ---------- چرخهٔ حیات ----------
    def start(self) -> None:
        if not self.code:
            if self.on_message:
                self.on_message("برای دیده شدن در شبکهٔ محلی، اول یک کد جفتسازی در تنظیمات وارد کن.")
            return
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except OSError:
                pass
            self._sock.bind(("", self.udp_port))
            self._sock.settimeout(1.0)
        except OSError as exc:
            if self.on_message:
                self.on_message(f"گوش دادن به شبکهٔ محلی ممکن نیست (پورت {self.udp_port} اشغال است).")
            self._sock = None
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._listen_loop, name="lan-listen", daemon=True),
            threading.Thread(target=self._announce_loop, name="lan-announce", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # ---------- ارسال و دریافت ----------
    def _payload(self) -> dict[str, Any]:
        return {
            "t": "hello", "v": 1, "id": self.identity.device_id,
            "name": self.identity.device_name, "port": self.tcp_port,
            "ts": time.time(),
        }

    def broadcast_addresses(self) -> list[str]:
        addrs = {"255.255.255.255", "<broadcast>"}
        try:
            import psutil
            for _name, infos in psutil.net_if_addrs().items():
                for info in infos:
                    if info.family == socket.AF_INET and info.broadcast:
                        addrs.add(str(info.broadcast))
        except Exception:
            pass
        return list(addrs)

    def _announce_loop(self) -> None:
        while not self._stop.is_set():
            if not self._sock:
                break
            payload = sign_discovery(self._payload(), self.psk)
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            for addr in self.broadcast_addresses():
                try:
                    self._sock.sendto(raw, (addr, self.udp_port))
                except OSError:
                    continue
            self._stop.wait(ANNOUNCE_INTERVAL)

    def _listen_loop(self) -> None:
        while not self._stop.is_set():
            if not self._sock:
                break
            try:
                raw, (host, _port) = self._sock.recvfrom(8192)
            except socket.timeout:
                self._expire()
                continue
            except OSError:
                break
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict) or not self.psk:
                    continue
                if not verify_discovery(payload, self.psk):
                    continue
                peer_id = str(payload.get("id", ""))
                if not peer_id or peer_id == self.identity.device_id:
                    continue
                with self._lock:
                    self._peers[peer_id] = Peer(
                        device_id=peer_id, name=str(payload.get("name", "?"))[:60],
                        host=host, port=int(payload.get("port", self.tcp_port)),
                        version=str(payload.get("v", "")), last_seen=time.time(),
                    )
            except (ValueError, TypeError, OSError):
                continue
            self._expire()
            self._notify()

    def _expire(self) -> None:
        now = time.time()
        with self._lock:
            for key in [k for k, v in self._peers.items() if now - v.last_seen > PEER_TTL]:
                del self._peers[key]

    def _notify(self) -> None:
        if self.on_update:
            try:
                self.on_update(self.peers())
            except Exception:
                pass

    def peers(self) -> list[Peer]:
        self._expire()
        with self._lock:
            return list(self._peers.values())

    def add_manual(self, host: str, port: int | None = None) -> Peer:
        """اتصال دستی برای شبکهای که broadcast را مسدود کرده است."""
        peer = Peer(device_id=f"manual:{host}:{port or self.tcp_port}",
                    name=host, host=host, port=int(port or self.tcp_port),
                    last_seen=time.time())
        with self._lock:
            self._peers[peer.device_id] = peer
        self._notify()
        return peer
