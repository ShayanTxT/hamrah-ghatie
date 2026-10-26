"""تست رمزنگاری، کشف، و ادامهٔ انتقال فایل در شبکهٔ محلی."""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from hamrah.core.errors import AppError
from hamrah.core.lan import protocol as P
from hamrah.core.lan.crypto import (
    Identity, SecureSession, code_to_psk, fingerprint, sign_discovery, verify_discovery,
)
from hamrah.core.lan.node import LanNode


def test_pairing_code_and_fingerprint(tmp_path):
    psk = code_to_psk("123456")
    assert len(psk) == 32
    assert code_to_psk("123456") == psk
    with pytest.raises(AppError):
        code_to_psk("12")
    ident = Identity(tmp_path / "id.json", tmp_path / "peers.json", "لپتاپ")
    assert ident.device_id and len(ident.own_fingerprint) > 10
    assert fingerprint(ident.static_public) == ident.own_fingerprint


def test_peer_pinning_detects_changed_key(tmp_path):
    ident = Identity(tmp_path / "id.json", tmp_path / "peers.json", "A")
    other = Identity(tmp_path / "id2.json", tmp_path / "peers2.json", "B")
    new, fp = ident.check_and_pin("peer1", "B", other.static_public)
    assert new is True and fp
    new2, _ = ident.check_and_pin("peer1", "B", other.static_public)
    assert new2 is False
    impostor = Identity(tmp_path / "id3.json", tmp_path / "peers3.json", "C")
    with pytest.raises(AppError):
        ident.check_and_pin("peer1", "B", impostor.static_public)


def test_discovery_signature():
    psk = code_to_psk("654321")
    payload = {"t": "hello", "id": "abc", "ts": time.time()}
    signed = sign_discovery(payload, psk)
    assert verify_discovery(dict(signed), psk)
    tampered = dict(signed)
    tampered["id"] = "attacker"
    assert not verify_discovery(tampered, psk)
    assert not verify_discovery(dict(signed), code_to_psk("111111"))
    old = sign_discovery({"t": "hello", "ts": time.time() - 9999}, psk)
    assert not verify_discovery(dict(old), psk)


def test_encrypted_session_roundtrip(tmp_path):
    code = "123456"
    a = Identity(tmp_path / "a.json", tmp_path / "pa.json", "A")
    b = Identity(tmp_path / "b.json", tmp_path / "pb.json", "B")
    left, right = socket.socketpair()
    results = {}

    def client():
        results["client"] = SecureSession.handshake(left, a, code, is_client=True)

    def server():
        results["server"] = SecureSession.handshake(right, b, code, is_client=False)

    t1 = threading.Thread(target=client)
    t2 = threading.Thread(target=server)
    t1.start(); t2.start(); t1.join(5); t2.join(5)
    assert "client" in results and "server" in results
    cs, ss = results["client"].session, results["server"].session

    cs.send({"t": "chat", "text": "سلام"}, b"\x00\x01binary")
    msg, blob = ss.recv()
    assert msg["text"] == "سلام" and blob == b"\x00\x01binary"
    ss.send({"t": "chat", "text": "درود"})
    msg2, _ = cs.recv()
    assert msg2["text"] == "درود"
    cs.close(); ss.close()


def test_wrong_pairing_code_rejected(tmp_path):
    a = Identity(tmp_path / "a.json", tmp_path / "pa.json", "A")
    b = Identity(tmp_path / "b.json", tmp_path / "pb.json", "B")
    left, right = socket.socketpair()
    errors = []

    def client():
        try:
            SecureSession.handshake(left, a, "111111", is_client=True)
        except Exception as exc:
            errors.append(exc)

    def server():
        try:
            SecureSession.handshake(right, b, "222222", is_client=False)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=client); t2 = threading.Thread(target=server)
    t1.start(); t2.start(); t1.join(5); t2.join(5)
    assert errors


def test_file_id_and_hash(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc" * 1000)
    digest = P.sha256_file(p)
    fid = P.make_file_id("f.bin", 3000, digest)
    assert len(fid) == 24
    assert P.make_file_id("f.bin", 3000, digest) == fid
    assert P.verify_sha256(p, digest)
    assert not P.verify_sha256(p, "0" * 64)
    assert "f." in P.incoming_filename("f.bin", fid)


class DummySession:
    def __init__(self):
        self.sent = []
        self.peer_id = "peer1"
        self.peer_name = "B"

    def send(self, msg, blob=b""):
        self.sent.append((msg, blob))


def test_incoming_file_approval_and_resume(db, settings, paths):
    approved = []
    node = LanNode(settings, paths, db, callbacks={
        "on_offer": lambda offer: approved.append(offer) or True,
        "on_progress": lambda *a: None,
        "on_file_done": lambda *a: None,
    })
    payload = b"HELLO-FILE-CONTENT"
    digest = __import__("hashlib").sha256(payload).hexdigest()
    fid = P.make_file_id("data.bin", len(payload), digest)
    msg = {"t": P.FILE_OFFER, "id": fid, "name": "data.bin",
           "size": len(payload), "sha256": digest}
    session = DummySession()
    node._handle_offer(msg, session)
    assert len(approved) == 1
    assert session.sent[0][0]["t"] == P.FILE_ACCEPT
    assert session.sent[0][0]["offset"] == 0
    offer = node._incoming[fid]

    # فقط نصف فایل میرسد
    node._handle_chunk({"t": P.FILE_CHUNK, "id": fid}, payload[:9], session)
    part = Path(offer.path + ".part")
    assert part.read_bytes() == payload[:9]

    # ارتباط قطع و دوباره وصل میشود؛ فرستنده همان فایل را offer میکند
    node._handle_offer(msg, session)
    assert len(approved) == 1  # دیگر سؤال نمیکند
    assert session.sent[-1][0]["offset"] == 9
    node._handle_chunk({"t": P.FILE_CHUNK, "id": fid}, payload[9:], session)
    done = []
    node.cb["on_file_done"] = lambda offer, path: done.append(path)
    node._handle_done({"t": P.FILE_DONE, "id": fid}, session)
    assert done and Path(done[0]).read_bytes() == payload


def test_rejected_file_sends_no_bytes(db, settings, paths):
    node = LanNode(settings, paths, db, callbacks={"on_offer": lambda offer: False})
    session = DummySession()
    node._handle_offer({"t": P.FILE_OFFER, "id": "x", "name": "a", "size": 10, "sha256": ""},
                       session)
    assert session.sent[0][0]["t"] == P.FILE_REJECT
    assert "x" not in node._incoming
