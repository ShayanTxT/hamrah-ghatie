"""صفحهٔ ۵ — اشتراک در شبکهٔ محلی (پیام و فایل، بدون اینترنت)."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ..core.persian import human_size, to_persian_digits
from .common import Card, button, info, label, row, show_error, title_block


class LanPage(QWidget):
    def __init__(self, ctx: Any, bridge: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.bridge = bridge
        self.peers: list[Any] = []
        self._transfers: dict[str, QListWidgetItem] = {}
        self._build()
        bridge.lan_message.connect(self.on_message)
        bridge.lan_progress.connect(self.on_progress)
        bridge.lan_peers.connect(self.on_peers)
        bridge.lan_file_done.connect(self.on_file_done)
        self.refresh_messages()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)
        outer.addWidget(title_block("شبکهٔ محلی بدون اینترنت",
                                    "کامپیوترهای وصل به یک مودم/وایفای همدیگر را پیدا میکنند؛ ارتباط رمزنگاریشده است."))

        top = Card()
        self.fingerprint_label = label("", name="subtitle")
        top.add(self.fingerprint_label)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("کد جفتسازی ۶رقمی (باید روی همهٔ دستگاهها یکی باشد)")
        self.code_edit.setMaxLength(12)
        self.code_edit.setText(str(self.ctx.config.get("pairing_code", "")))
        top.add_layout(row(
            label("کد جفتسازی:"), self.code_edit,
            button("ذخیره و راهاندازی مجدد", primary=True, on_click=self.restart),
            button("اتصال دستی به IP", on_click=self.manual_connect),
            stretch=True,
        ))
        self.manual_edit = QLineEdit()
        self.manual_edit.setPlaceholderText("مثلاً 192.168.1.25 (وقتی broadcast مسدود است)")
        top.add(self.manual_edit)
        self.lan_status = label("", name="muted")
        top.add(self.lan_status)
        outer.addWidget(top)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(label("دستگاههای پیداشده", bold=True))
        self.peer_list = QListWidget()
        self.peer_list.currentRowChanged.connect(self.on_peer_selected)
        left_layout.addWidget(self.peer_list)
        left_layout.addLayout(row(
            button("بروزرسانی", on_click=self.refresh_peers),
            button("وصل شدن", on_click=self.connect_selected),
        ))
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        right_layout.addWidget(self.chat_view, 1)
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("پیامت را بنویس و Enter بزن...")
        self.msg_input.returnPressed.connect(self.send_chat)
        right_layout.addLayout(row(self.msg_input,
                                   button("ارسال پیام", primary=True, on_click=self.send_chat),
                                   button("ارسال فایل", on_click=self.send_file)))
        self.transfer_list = QListWidget()
        self.transfer_list.setMaximumHeight(130)
        right_layout.addWidget(label("انتقال فایلها", bold=True))
        right_layout.addWidget(self.transfer_list)
        splitter.addWidget(right)
        splitter.setSizes([320, 720])
        outer.addWidget(splitter, 1)

    # ---------- راهاندازی ----------
    def start_lan(self) -> None:
        code = str(self.ctx.config.get("pairing_code", "")).strip()
        self.ctx.lan.cb = {
            "on_message": lambda pid, name, text: self.bridge.lan_message.emit(pid, name, text),
            "on_offer": self._ask_offer,
            "on_progress": lambda offer, done, total: self.bridge.lan_progress.emit(offer, done, total),
            "on_peers": lambda peers: self.bridge.lan_peers.emit(peers),
            "on_file_done": lambda offer, path: self.bridge.lan_file_done.emit(offer, path),
            "on_error": lambda msg: self.bridge.toast.emit(msg, "red"),
            "on_new_peer": lambda name, fp: self.bridge.toast.emit(
                f"دستگاه جدید: {name} — اثر انگشت {fp}", "accent"),
        }
        self.fingerprint_label.setText(f"اثر انگشت این دستگاه: {self.ctx.lan.own_fingerprint}")
        if not code:
            self.lan_status.setText("برای شروع، یک کد جفتسازی ۶رقمی وارد کن و دکمهٔ «ذخیره و راهاندازی مجدد» را بزن.")
            return
        try:
            self.ctx.lan.start()
            self.lan_status.setText(f"در حال گوش دادن روی پورت {self.ctx.lan.tcp_port} — در جستجوی همسایهها...")
        except Exception as exc:
            self.lan_status.setText("راهاندازی شبکهٔ محلی ممکن نشد.")
            self.bridge.toast.emit(str(exc), "red")

    def restart(self) -> None:
        code = self.code_edit.text().strip()
        if code and not code.isdigit():
            info("کد جفتسازی فقط باید عدد باشد.", self)
            return
        try:
            self.ctx.save_settings({"pairing_code": code})
            self.ctx.lan.stop()
            self.start_lan()
            self.bridge.toast.emit("شبکهٔ محلی دوباره راهاندازی شد.", "green")
        except Exception as exc:
            show_error(self, "راهاندازی شبکهٔ محلی ممکن نشد.", self.ctx.logger, exc)

    def _ask_offer(self, offer: Any) -> bool:
        """از نخ شبکه فراخوانی میشود؛ دیالوگ را به نخ اصلی منتقل میکند."""
        import threading
        event = threading.Event()
        result: list[bool] = [False]
        self.bridge.offer.emit(offer, (event, result))
        event.wait(300)
        return bool(result and result[0])

    # ---------- همسایهها ----------
    def refresh_peers(self) -> None:
        self.on_peers(self.ctx.lan.peers())

    def on_peers(self, peers: Any) -> None:
        self.peers = list(peers or [])
        current = self.peer_list.currentRow()
        self.peer_list.clear()
        for p in self.peers:
            item = QListWidgetItem(f"💻 {p.name} — {p.host}:{p.port}")
            item.setData(Qt.UserRole, p.device_id)
            self.peer_list.addItem(item)
        if 0 <= current < self.peer_list.count():
            self.peer_list.setCurrentRow(current)
        self.lan_status.setText(f"{len(self.peers)} دستگاه در شبکه پیدا شد.")

    def _current_peer(self) -> Any:
        idx = self.peer_list.currentRow()
        return self.peers[idx] if 0 <= idx < len(self.peers) else None

    def on_peer_selected(self, index: int) -> None:
        peer = self._current_peer()
        if peer and not self.ctx.lan._session_for(peer.device_id):
            self.ctx.lan.connect(peer)

    def connect_selected(self) -> None:
        peer = self._current_peer()
        if not peer:
            info("اول یک دستگاه از لیست انتخاب کن.", self)
            return
        ok = self.ctx.lan.connect(peer)
        self.bridge.toast.emit("اتصال برقرار شد." if ok else "اتصال برقرار نشد.",
                               "green" if ok else "red")

    def manual_connect(self) -> None:
        host = self.manual_edit.text().strip()
        if not host:
            return
        peer = self.ctx.lan.discovery.add_manual(host)
        self.refresh_peers()
        if self.ctx.lan.connect(peer):
            self.bridge.toast.emit(f"به {host} وصل شدیم.", "green")
        else:
            self.bridge.toast.emit(f"اتصال به {host} ممکن نشد.", "red")

    # ---------- پیام و فایل ----------
    def send_chat(self) -> None:
        text = self.msg_input.text().strip()
        peer = self._current_peer()
        if not text or not peer:
            return
        ok = self.ctx.lan.send_chat(peer.device_id, text)
        if ok:
            self.on_message(peer.device_id, "شما", text)
            self.msg_input.clear()
        else:
            self.bridge.toast.emit("ارسال پیام ممکن نشد؛ دوباره وصل شو.", "red")

    def send_file(self) -> None:
        peer = self._current_peer()
        if not peer:
            info("اول دستگاه مقصد را انتخاب کن.", self)
            return
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل برای ارسال", "")
        if not path:
            return
        self.ctx.lan.send_file(peer.device_id, path)
        self.bridge.toast.emit("فایل در صف ارسال قرار گرفت.", "accent")

    def on_message(self, peer_id: str, name: str, text: str) -> None:
        from datetime import datetime
        from ..core.jalali import format_datetime
        clock = format_datetime(datetime.now()).split("—")[-1].strip()
        self.chat_view.append(f"{clock} — {name}: {text}\n")
        self.refresh_messages()

    def refresh_messages(self) -> None:
        # خلاصهٔ پیامهای ذخیرهشده را در ابتدای نمایش میگذاریم
        try:
            rows = self.ctx.lan.messages(30)
            if rows and not self.chat_view.toPlainText().strip():
                for r in rows:
                    who = "شما" if r["direction"] == "out" else "طرف مقابل"
                    self.chat_view.append(f"{who}: {r['content']}")
        except Exception:
            pass

    def on_progress(self, offer: Any, done: int, total: int) -> None:
        key = f"{offer.file_id}:{offer.direction}"
        item = self._transfers.get(key)
        if item is None:
            item = QListWidgetItem()
            self._transfers[key] = item
            self.transfer_list.addItem(item)
        pct = int(100 * done / total) if total else 0
        arrow = "📥" if offer.direction == "in" else "📤"
        item.setText(f"{arrow} {offer.name} — {pct}٪ ({human_size(done)} / {human_size(total)})")

    def on_file_done(self, offer: Any, path: str) -> None:
        self.bridge.toast.emit(f"فایل دریافت شد: {path}", "green")
        key = f"{offer.file_id}:in"
        if key in self._transfers:
            self._transfers[key].setText(f"✅ {offer.name} — انجام شد")
