"""گره شبکهٔ محلی: TCP سرور/کلاینت، چت، و انتقال فایل قابلادامه.

همهٔ پیامها قبل از ارسال با AES-GCM رمز میشوند (نگاه کنید به crypto.py).
دریافت هر فایل نیازمند تأیید صریح کاربر است؛ فایل نیمهکاره در
``data/incoming/*.part`` نگهداری میشود و بعد از وصل شدن دوباره، فرستنده
از همان آفست ادامه میدهد.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..db import Database
from ..errors import friendly
from ..persian import safe_filename
from . import protocol as P
from .crypto import HandshakeResult, Identity, SecureSession, code_to_psk
from .discovery import Discovery, Peer


class LanNode:
    def __init__(
        self,
        cfg: dict[str, Any],
        paths: Any,
        db: Database,
        *,
        identity: Identity | None = None,
        discovery: Discovery | None = None,
        callbacks: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.db = db
        self.code = str(cfg.get("pairing_code", ""))
        self.tcp_port = int(cfg.get("lan_tcp_port", 54546))
        self.identity = identity or Identity(paths.identity_path, paths.peers_path,
                                             str(cfg.get("device_name", "")))
        self.cb = callbacks or {}
        self.discovery = discovery or Discovery(
            cfg, self.identity,
            on_update=lambda peers: self._emit("on_peers", peers),
            on_message=lambda msg: self._emit("on_error", msg),
        )
        self._sessions: dict[str, SecureSession] = {}
        self._aliases: dict[str, str] = {}
        self._incoming: dict[str, P.FileOffer] = {}
        self._approved: set[str] = set()
        self._accept_events: dict[str, tuple[threading.Event, list[Any]]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._threads: list[threading.Thread] = []

    # ---------- کمکی ----------
    def _emit(self, name: str, *args: Any) -> Any:
        fn = self.cb.get(name)
        if not fn:
            return None
        try:
            return fn(*args)
        except Exception:
            return None

    def _session_for(self, peer_id: str) -> SecureSession | None:
        with self._lock:
            real = self._aliases.get(peer_id, peer_id)
            return self._sessions.get(real)

    def _register(self, result: HandshakeResult, alias: str | None = None) -> None:
        with self._lock:
            old = self._sessions.get(result.peer_id)
            if old and old is not result.session:
                old.close()
            self._sessions[result.peer_id] = result.session
            if alias:
                self._aliases[alias] = result.peer_id
        if result.is_new_peer:
            self._emit("on_new_peer", result.peer_name, result.peer_fingerprint)

    def _unregister(self, session: SecureSession) -> None:
        with self._lock:
            for key, value in list(self._sessions.items()):
                if value is session:
                    del self._sessions[key]
            for key, value in list(self._aliases.items()):
                if value == session.peer_id:
                    del self._aliases[key]
        session.close()

    # ---------- چرخهٔ حیات ----------
    def start(self) -> None:
        if not self.code:
            self._emit("on_error", "کد جفتسازی خالی است. از تب تنظیمات یک کد ۶رقمی وارد کن.")
            return
        code_to_psk(self.code)  # زود خطای کد نامعتبر را بدهد
        self._stop.clear()
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind(("0.0.0.0", self.tcp_port))
            self._server.listen(16)
            self._server.settimeout(1.0)
        except OSError as exc:
            self._emit("on_error", friendly(exc, "راهاندازی شبکهٔ محلی ممکن نیست."))
            self._server = None
            return
        t = threading.Thread(target=self._accept_loop, name="lan-accept", daemon=True)
        t.start()
        self._threads.append(t)
        self.discovery.start()

    def stop(self) -> None:
        self._stop.set()
        self.discovery.stop()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()

    # ---------- سرور ----------
    def _accept_loop(self) -> None:
        while not self._stop.is_set() and self._server:
            try:
                sock, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._connection, args=(sock, False, None),
                                 name=f"lan-in-{addr[0]}", daemon=True)
            t.start()
            self._threads.append(t)

    def connect(self, peer: Peer) -> bool:
        """اتصال به یک همسایه (معمولاً خودکار بعد از کشف شدن انجام میشود)."""
        if self._session_for(peer.device_id):
            return True
        try:
            sock = socket.create_connection((peer.host, peer.port), timeout=5.0)
        except OSError:
            return False
        try:
            result = SecureSession.handshake(sock, self.identity, self.code, is_client=True)
            self._register(result, alias=peer.device_id if peer.device_id.startswith("manual:") else None)
            t = threading.Thread(target=self._recv_loop, args=(result.session,),
                                 name="lan-out-recv", daemon=True)
            t.start()
            self._threads.append(t)
            return True
        except Exception as exc:
            try:
                sock.close()
            except OSError:
                pass
            self._emit("on_error", friendly(exc, "اتصال به دستگاه مقابل برقرار نشد."))
            return False

    def _connection(self, sock: socket.socket, is_client: bool, _unused: Any) -> None:
        try:
            result = SecureSession.handshake(sock, self.identity, self.code, is_client=False)
        except Exception as exc:
            try:
                sock.close()
            except OSError:
                pass
            self._emit("on_error", friendly(exc, "یک دستگاه سعی کرد وصل شود."))
            return
        self._register(result)
        self._recv_loop(result.session)

    def _recv_loop(self, session: SecureSession) -> None:
        try:
            while not self._stop.is_set():
                msg, blob = session.recv()
                self._handle(msg, blob, session)
        except (ConnectionError, OSError, ValueError):
            pass
        except Exception as exc:
            self._emit("on_error", friendly(exc, "ارتباط با یک دستگاه قطع شد."))
        finally:
            self._unregister(session)

    # ---------- پردازش پیامها ----------
    def _handle(self, msg: dict[str, Any], blob: bytes, session: SecureSession) -> None:
        kind = msg.get("t", "")
        if kind == P.CHAT:
            text = str(msg.get("text", ""))[:8000]
            self.db.execute(
                "INSERT INTO lan_messages(peer_id, direction, content, ts) VALUES(?, 'in', ?, ?)",
                (session.peer_id, text, time.time()),
            )
            self._emit("on_message", session.peer_id, session.peer_name, text)
        elif kind == P.PING:
            session.send({"t": P.PONG})
        elif kind == P.FILE_OFFER:
            self._handle_offer(msg, session)
        elif kind == P.FILE_ACCEPT:
            self._resolve_accept(msg.get("id", ""), int(msg.get("offset", 0)))
        elif kind == P.FILE_REJECT:
            self._resolve_accept(msg.get("id", ""), None)
        elif kind == P.FILE_CHUNK:
            self._handle_chunk(msg, blob, session)
        elif kind == P.FILE_DONE:
            self._handle_done(msg, session)
        elif kind == P.FILE_ERROR:
            self._emit("on_error", f"خطا در انتقال فایل: {msg.get('error', 'نامشخص')}")

    def _handle_offer(self, msg: dict[str, Any], session: SecureSession) -> None:
        file_id = str(msg.get("id", ""))
        name = safe_filename(str(msg.get("name", "فایل")))
        size = int(msg.get("size", 0))
        digest = str(msg.get("sha256", ""))
        if not file_id or size < 0:
            session.send({"t": P.FILE_ERROR, "id": file_id, "error": "bad offer"})
            return
        final = self.paths.incoming / P.incoming_filename(name, file_id)
        part = Path(str(final) + ".part")
        offer = P.FileOffer(file_id, name, size, digest, session.peer_id,
                            "in", 0, str(final))

        if file_id not in self._approved:
            allowed = bool(self._emit("on_offer", offer))
            if not allowed:
                session.send({"t": P.FILE_REJECT, "id": file_id})
                return
            self._approved.add(file_id)

        offset = part.stat().st_size if part.exists() else 0
        if offset > size:
            offset = 0
            part.write_bytes(b"")
        offer.offset = offset
        with self._lock:
            self._incoming[file_id] = offer
        session.send({"t": P.FILE_ACCEPT, "id": file_id, "offset": offset})
        self._emit("on_progress", offer, offset, size)

    def _handle_chunk(self, msg: dict[str, Any], blob: bytes, session: SecureSession) -> None:
        file_id = str(msg.get("id", ""))
        offer = self._incoming.get(file_id)
        if not offer or not blob:
            return
        try:
            with open(offer.path + ".part" if not offer.path.endswith(".part") else offer.path, "ab") as f:
                f.write(blob)
        except OSError as exc:
            session.send({"t": P.FILE_ERROR, "id": file_id, "error": friendly(exc)})
            return
        offer.offset += len(blob)
        self._emit("on_progress", offer, offer.offset, offer.size)

    def _handle_done(self, msg: dict[str, Any], session: SecureSession) -> None:
        file_id = str(msg.get("id", ""))
        offer = self._incoming.pop(file_id, None)
        if not offer:
            return
        part = Path(str(offer.path) + ".part")
        final = Path(offer.path)
        if part.exists() and P.verify_sha256(part, offer.sha256):
            if final.exists():
                final.unlink()
            part.replace(final)
            self.db.execute(
                "INSERT INTO lan_messages(peer_id, direction, content, ts) VALUES(?, 'in', ?, ?)",
                (offer.peer_id, f"📥 فایل دریافت شد: {final.name}", time.time()),
            )
            self._emit("on_file_done", offer, str(final))
        else:
            self._emit("on_error", f"فایل {offer.name} کامل نرسید؛ دفعهٔ بعد ادامه پیدا میکند.")

    def _resolve_accept(self, file_id: str, offset: int | None) -> None:
        with self._lock:
            entry = self._accept_events.get(file_id)
        if entry:
            event, box = entry
            box.append(offset)
            event.set()

    # ---------- ارسال ----------
    def send_chat(self, peer_id: str, text: str) -> bool:
        session = self._session_for(peer_id)
        if not session:
            peer = next((p for p in self.discovery.peers() if p.device_id == peer_id), None)
            if not peer or not self.connect(peer):
                return False
            session = self._session_for(peer_id)
        if not session:
            return False
        try:
            session.send({"t": P.CHAT, "text": text[:8000]})
            self.db.execute(
                "INSERT INTO lan_messages(peer_id, direction, content, ts) VALUES(?, 'out', ?, ?)",
                (session.peer_id, text, time.time()),
            )
            return True
        except Exception as exc:
            self._unregister(session)
            self._emit("on_error", friendly(exc, "ارسال پیام ممکن نشد."))
            return False

    def send_file(self, peer_id: str, path: str | Path) -> None:
        """ارسال فایل در یک نخ جداگانه؛ بدون محدودیت حجم و با ادامهٔ خودکار."""
        path = Path(path)
        if not path.is_file():
            self._emit("on_error", "فایل انتخابشده پیدا نشد.")
            return
        t = threading.Thread(target=self._sender_loop, args=(peer_id, path),
                             name="lan-send", daemon=True)
        t.start()
        self._threads.append(t)

    def _sender_loop(self, peer_id: str, path: Path) -> None:
        try:
            digest = P.sha256_file(path)
            file_id = P.make_file_id(path.name, path.stat().st_size, digest)
            size = path.stat().st_size
        except Exception as exc:
            self._emit("on_error", friendly(exc, "آمادهسازی فایل برای ارسال ممکن نشد."))
            return
        offer = P.FileOffer(file_id, path.name, size, digest, peer_id,
                            "out", 0, str(path))
        event, box = threading.Event(), []
        with self._lock:
            self._accept_events[file_id] = (event, box)

        for _attempt in range(200):
            if self._stop.is_set():
                return
            session = self._session_for(peer_id)
            if not session:
                peer = next((p for p in self.discovery.peers() if p.device_id == peer_id), None)
                if peer:
                    self.connect(peer)
                    session = self._session_for(peer_id) or self._session_for(peer.device_id)
                else:
                    manual = self.discovery.add_manual(peer_id.split(":")[1], self.tcp_port) \
                        if peer_id.startswith("manual:") else None
                    if manual:
                        self.connect(manual)
                        session = self._session_for(peer_id)
            if not session:
                self._stop.wait(2.0)
                continue
            try:
                event.clear()
                box.clear()
                session.send({"t": P.FILE_OFFER, "id": file_id, "name": path.name,
                              "size": size, "sha256": digest})
                if not event.wait(300.0):
                    continue
                offset_raw = box[0] if box else None
                if offset_raw is None:
                    self._emit("on_error", f"دریافت فایل «{path.name}» توسط طرف مقابل رد شد.")
                    return
                offset = max(0, min(size, int(offset_raw)))
                offer.offset = offset
                with open(path, "rb") as f:
                    f.seek(offset)
                    while offset < size:
                        if self._stop.is_set():
                            return
                        block = f.read(P.CHUNK_SIZE)
                        if not block:
                            break
                        session.send({"t": P.FILE_CHUNK, "id": file_id, "offset": offset}, block)
                        offset += len(block)
                        offer.offset = offset
                        self._emit("on_progress", offer, offset, size)
                session.send({"t": P.FILE_DONE, "id": file_id})
                return
            except Exception as exc:
                self._unregister(session)
                self._emit("on_error", friendly(exc, "انتقال فایل قطع شد؛ دوباره تلاش میکنیم."))
                self._stop.wait(2.0)
        self._emit("on_error", "ارسال فایل بعد از تلاشهای مکرر انجام نشد.")

    # ---------- نمایش ----------
    def peers(self) -> list[Peer]:
        return self.discovery.peers()

    def messages(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM lan_messages ORDER BY ts DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in reversed(rows)]

    @property
    def own_fingerprint(self) -> str:
        return self.identity.own_fingerprint
