"""رمزنگاری شبکهٔ محلی.

طرح (سادهشده ولی عملی):
* هر کامپیوتر یک کلید ثابت X25519 دارد (``data/identity.json``). اثر انگشت
  دستگاه = SHA-256 کلید عمومی.
* کد جفتسازی ۶رقمی به PSK تبدیل میشود. تبادل سلام شامل اثبات HMAC با PSK
  است؛ بدون دانستن کد نمیتوان خود را جای دستگاه دیگری جا زد.
* کلید جلسه از ECDH موقتی (X25519) + PSK با HKDFSHA256 ساخته میشود
  (دو کلید جداگانه برای هر جهت). هر بسته با AES-256-GCM رمز میشود.
* بعد از اولین اتصال، کلید ثابت طرف مقابل در ``data/peers.json`` پین میشود.
  اگر عوض شود، اتصال رد میشود (جلوی تعویض دستگاه).

توجه صادقانه: این یک پروتکل اختصاصیِ حسابرسینشده است، نه TLS/Signal.
برای یک شبکهٔ خانگی/محلی امنیت کافی میدهد، ولی ادعای اثباتشدهٔ رمزنگاری
نمیکنیم.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..errors import AppError

PROTOCOL_VERSION = 1
MAX_HEADER = 1024 * 1024
MAX_BLOB = 16 * 1024 * 1024
AAD_HEADER = b"hamrah-lan-header-v1"
AAD_BLOB = b"hamrah-lan-blob-v1"


def code_to_psk(code: str) -> bytes:
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(digits) < 4:
        raise AppError("کد جفتسازی باید حداقل ۴ رقم باشد (پیشنهاد: ۶ رقم).", code="pairing")
    return hashlib.sha256(b"hamrah-ghatie-pairing-v1|" + digits.encode("ascii")).digest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def pub_raw(key: X25519PrivateKey | X25519PublicKey) -> bytes:
    public = key.public_key() if isinstance(key, X25519PrivateKey) else key
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def fingerprint(static_pub: bytes) -> str:
    digest = hashlib.sha256(static_pub).hexdigest()[:20].upper()
    return ":".join(digest[i:i + 4] for i in range(0, len(digest), 4))


class Identity:
    """کلید ثابت دستگاه + پین کردن کلید دستگاههای دیگر (TOFU)."""

    def __init__(self, identity_path: Path, peers_path: Path, device_name: str = "") -> None:
        self.identity_path = Path(identity_path)
        self.peers_path = Path(peers_path)
        self.device_name = device_name or os.environ.get("COMPUTERNAME") or "دستگاه من"
        self._lock = threading.Lock()
        self._private, self._device_id = self._load_or_create()
        self._peers = self._load_peers()

    def _load_or_create(self) -> tuple[X25519PrivateKey, str]:
        if self.identity_path.is_file():
            try:
                data = json.loads(self.identity_path.read_text("utf-8"))
                raw = unb64(data["private_key"])
                if len(raw) == 32:
                    priv = X25519PrivateKey.from_private_bytes(raw)
                    return priv, data.get("device_id") or hashlib.sha256(pub_raw(priv)).hexdigest()[:16]
            except Exception:
                pass
        priv = X25519PrivateKey.generate()
        device_id = hashlib.sha256(pub_raw(priv)).hexdigest()[:16]
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.identity_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({
            "private_key": b64(priv.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )),
            "device_id": device_id,
            "created_at": time.time(),
        }, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, self.identity_path)
        return priv, device_id

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def static_public(self) -> bytes:
        return pub_raw(self._private)

    @property
    def own_fingerprint(self) -> str:
        return fingerprint(self.static_public)

    # ---- پین کردن ----
    def _load_peers(self) -> dict[str, dict[str, Any]]:
        if self.peers_path.is_file():
            try:
                data = json.loads(self.peers_path.read_text("utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def save_peers(self) -> None:
        with self._lock:
            data = dict(self._peers)
        tmp = self.peers_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, self.peers_path)

    def check_and_pin(self, device_id: str, name: str, static_pub: bytes) -> tuple[bool, str]:
        """برمیگرداند (آیا دستگاه جدید است، اثر انگشت)."""
        fp = fingerprint(static_pub)
        with self._lock:
            known = self._peers.get(device_id)
            if known and known.get("static_pub") != b64(static_pub):
                raise AppError(
                    "کلید دستگاه مقابل عوض شده است. اگر خودت برنامه را دوباره نصب کردهای، "
                    "فایل data/peers.json را پاک کن؛ در غیر این صورت اتصال رد شد.",
                    code="peer_changed",
                )
            is_new = known is None
            self._peers[device_id] = {
                "name": name, "static_pub": b64(static_pub),
                "fingerprint": fp, "first_seen": (known or {}).get("first_seen", time.time()),
                "last_seen": time.time(),
            }
        self.save_peers()
        return is_new, fp

    def peers(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._peers.items()}


# ---------- کشف UDP ----------
def canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_discovery(payload: dict[str, Any], psk: bytes) -> dict[str, Any]:
    body = dict(payload)
    mac = hmac.new(psk, canonical(body), hashlib.sha256).hexdigest()[:32]
    body["mac"] = mac
    return body


def verify_discovery(payload: dict[str, Any], psk: bytes, *, drift: float = 300.0) -> bool:
    body = dict(payload or {})
    try:
        given = body.pop("mac")
    except (KeyError, AttributeError):
        return False
    expected = hmac.new(psk, canonical(body), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(str(given), expected):
        return False
    try:
        return abs(time.time() - float(body.get("ts", 0))) <= drift
    except (TypeError, ValueError):
        return False


# ---------- قاب handshake متنی ----------
def send_plain(sock: Any, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def read_exact(sock: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        block = sock.recv(min(remaining, 65536))
        if not block:
            raise ConnectionError("ارتباط بسته شد")
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def recv_plain(sock: Any) -> dict[str, Any]:
    size = struct.unpack("!I", read_exact(sock, 4))[0]
    if size > MAX_HEADER:
        raise AppError("پیام نامعتبر از دستگاه مقابل دریافت شد.")
    return json.loads(read_exact(sock, size).decode("utf-8"))


def _hmac_proof(psk: bytes, hello: dict[str, Any], role: str) -> str:
    transcript = "|".join([
        str(PROTOCOL_VERSION), hello["id"], hello["name"], hello["sp"],
        hello["ep"], hello["n"], role,
    ])
    return hmac.new(psk, transcript.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


@dataclass
class HandshakeResult:
    session: "SecureSession"
    peer_id: str
    peer_name: str
    peer_fingerprint: str
    is_new_peer: bool


class SecureSession:
    """یک ارتباط TCP رمزنگاریشده. ``send``/``recv`` رشته ایمناند."""

    def __init__(self, sock: Any, key_send: bytes, key_recv: bytes,
                 peer_id: str, peer_name: str, fingerprint: str) -> None:
        self.sock = sock
        self.peer_id = peer_id
        self.peer_name = peer_name
        self.fingerprint = fingerprint
        self._send_key = key_send
        self._recv_key = key_recv
        self._send_counter = 0
        self._recv_counter = 0
        # نمک nonce باید در هر دو طرف یکسان باشد (مستقل از جهت کلیدها)
        self._salt = hashlib.sha256(b"".join(sorted([key_send, key_recv]))).digest()[:4]
        self._lock = threading.Lock()
        self._read_lock = threading.Lock()
        self.closed = False

    def _nonce(self, counter: int) -> bytes:
        return self._salt + counter.to_bytes(8, "big")

    def send(self, obj: dict[str, Any], blob: bytes = b"") -> None:
        if self.closed:
            raise ConnectionError("جلسه بسته شده است")
        header = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self._lock:
            n1, n2 = self._send_counter, self._send_counter + 1
            self._send_counter += 2
            enc_h = AESGCM(self._send_key).encrypt(self._nonce(n1), header, AAD_HEADER)
            enc_b = (AESGCM(self._send_key).encrypt(self._nonce(n2), blob, AAD_BLOB)
                     if blob else b"")
            frame = struct.pack("!II", len(enc_h), len(enc_b)) + enc_h + enc_b
            self.sock.sendall(frame)

    def recv(self) -> tuple[dict[str, Any], bytes]:
        with self._read_lock:
            head = read_exact(self.sock, 8)
            len_h, len_b = struct.unpack("!II", head)
            if len_h > MAX_HEADER or len_b > MAX_BLOB:
                raise AppError("بستهای با اندازهٔ غیرمجاز دریافت شد.")
            enc_h = read_exact(self.sock, len_h)
            enc_b = read_exact(self.sock, len_b) if len_b else b""
            n1, n2 = self._recv_counter, self._recv_counter + 1
            self._recv_counter += 2
        header = AESGCM(self._recv_key).decrypt(self._nonce(n1), enc_h, AAD_HEADER)
        blob = (AESGCM(self._recv_key).decrypt(self._nonce(n2), enc_b, AAD_BLOB)
                if enc_b else b"")
        return json.loads(header.decode("utf-8")), blob

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except Exception:
            pass

    # ---------- پروتکل تبادل کلید ----------
    @classmethod
    def handshake(
        cls,
        sock: Any,
        identity: Identity,
        code: str,
        *,
        is_client: bool,
        timeout: float = 8.0,
    ) -> HandshakeResult:
        psk = code_to_psk(code)
        sock.settimeout(timeout)
        role = "C" if is_client else "S"
        eph = X25519PrivateKey.generate()
        nonce = secrets.token_hex(8)
        hello = {
            "t": "hello", "v": PROTOCOL_VERSION,
            "id": identity.device_id, "name": identity.device_name,
            "sp": b64(identity.static_public), "ep": b64(pub_raw(eph)), "n": nonce,
            "role": role,
        }
        hello["proof"] = _hmac_proof(psk, hello, role)

        if is_client:
            send_plain(sock, hello)
            other = recv_plain(sock)
        else:
            other = recv_plain(sock)
            send_plain(sock, hello)

        if other.get("t") != "hello" or other.get("v") != PROTOCOL_VERSION:
            raise AppError("نسخهٔ برنامه روی دو دستگاه متفاوت است.")
        other_role = "S" if is_client else "C"
        if other.get("role") != other_role:
            raise AppError("تبادل کلید نامعتبر بود.")
        if not hmac.compare_digest(str(other.get("proof", "")), _hmac_proof(psk, other, other_role)):
            raise AppError("کد جفتسازی دو دستگاه یکی نیست یا پیام دستکاری شده است.")
        if other["id"] == identity.device_id:
            raise AppError("دستگاه خودت را بهعنوان طرف مقابل پیدا کردیم.")

        peer_static = unb64(other["sp"])
        is_new, fp = identity.check_and_pin(other["id"], other["name"], peer_static)
        shared = eph.exchange(X25519PublicKey.from_public_bytes(unb64(other["ep"])))
        # همهٔ اجزای info باید در دو طرف یکسان باشند -> حتماً مرتب میشوند
        ids = sorted([identity.device_id, other["id"]])
        nonces = sorted([nonce, other["n"]])
        statics = sorted([b64(identity.static_public), b64(peer_static)])
        info = ("hamrah-lan-v1|" + "|".join(ids + nonces + statics)).encode("utf-8")
        material = HKDF(algorithm=hashes.SHA256(), length=64, salt=psk, info=info).derive(shared)
        k_c2s, k_s2c = material[:32], material[32:]
        key_send, key_recv = (k_c2s, k_s2c) if is_client else (k_s2c, k_c2s)
        sock.settimeout(None)
        session = cls(sock, key_send, key_recv, other["id"], other["name"], fp)
        return HandshakeResult(session, other["id"], other["name"], fp, is_new)
