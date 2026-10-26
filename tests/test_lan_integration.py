"""تست یکپارچهسازی واقعی: دو گره روی TCP loopback چت و فایل ردوبدل میکنند."""
from __future__ import annotations

import hashlib
import threading
import time

from hamrah.core.config import Config
from hamrah.core.db import Database
from hamrah.core.lan.node import LanNode
from hamrah.core.paths import Paths


def _node(root, code: str, name: str, udp: int, tcp: int, callbacks=None):
    paths = Paths(root)
    cfg = Config(paths.config_path)
    cfg.update({
        "pairing_code": code, "device_name": name,
        "lan_udp_port": udp, "lan_tcp_port": tcp,
    })
    cfg.save()
    db = Database(paths.db_path)
    node = LanNode(cfg, paths, db, callbacks=callbacks or {})
    return node, paths, db


def test_two_nodes_chat_and_transfer_file(tmp_path):
    got_chat = threading.Event()
    got_file = threading.Event()
    chat_text: list[str] = []
    file_paths: list[str] = []
    approved: list[str] = []

    a, paths_a, _ = _node(
        tmp_path / "A", "123456", "دستگاه A", 54701, 54601,
        callbacks={
            "on_message": lambda pid, name, text: (chat_text.append(text), got_chat.set()),
            "on_offer": lambda offer: (approved.append(offer.name), True)[1],
            "on_file_done": lambda offer, path: (file_paths.append(path), got_file.set()),
            "on_progress": lambda *args: None,
            "on_error": lambda msg: None,
        },
    )
    b, paths_b, _ = _node(
        tmp_path / "B", "123456", "دستگاه B", 54702, 54602,
        callbacks={"on_message": lambda *args: None,
                   "on_error": lambda msg: None,
                   "on_progress": lambda *args: None},
    )
    try:
        a.start()
        b.start()
        peer_a = b.discovery.add_manual("127.0.0.1", 54601)
        assert b.connect(peer_a), "اتصال رمزنگاریشده برقرار نشد"

        assert b.send_chat(peer_a.device_id, "سلام آفلاین")
        assert got_chat.wait(10), "پیام به دستگاه A نرسید"
        assert chat_text == ["سلام آفلاین"]

        payload = ("دادهٔ فارسی آزمایشی " * 5000).encode("utf-8")
        source = paths_b.root / "testfile.txt"
        source.write_bytes(payload)
        b.send_file(peer_a.device_id, source)
        assert got_file.wait(20), "فایل به دستگاه A نرسید"
        assert approved and approved[0] == "testfile.txt"
        received = paths_a.incoming / __import__("pathlib").Path(file_paths[0]).name
        assert received.exists()
        assert hashlib.sha256(received.read_bytes()).digest() == hashlib.sha256(payload).digest()
    finally:
        a.stop()
        b.stop()
