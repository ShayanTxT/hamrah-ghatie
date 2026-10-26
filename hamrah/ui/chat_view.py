"""صفحهٔ ۴ — دستیار هوش مصنوعی آفلاین ( GGUF + llama.cpp )."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ..core.persian import human_size
from ..core.sysinfo import PROFILES, detect, recommend
from .common import Card, button, confirm, info, label, row, show_error, title_block
from .workers import ChatWorker


class ChatPage(QWidget):
    def __init__(self, ctx: Any, bridge: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.bridge = bridge
        self.current_chat: int | None = None
        self.worker: ChatWorker | None = None
        self.streaming = False
        self._build()
        self.refresh_models()
        self.refresh_chats()
        self.refresh_system()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)
        outer.addWidget(title_block("دستیار هوش مصنوعی آفلاین",
                                    "مدل روی همان کامپیوتر اجرا میشود؛ فقط ارتباط داخلی 127.0.0.1 برقرار است."))

        setup = Card()
        self.system_label = label("در حال سنجش سختافزار...", name="subtitle")
        self.rec_label = label("", name="muted")
        setup.add(self.system_label)
        setup.add(self.rec_label)
        self.model_combo = QComboBox()
        self.start_btn = button("اجرای مدل", primary=True, on_click=self.toggle_model)
        setup.add_layout(row(
            label("مدل:"), self.model_combo,
            self.start_btn,
            button("وارد کردن مدل از فلش", on_click=self.import_model),
            button("وارد کردن llama-server", on_click=self.import_server),
            stretch=True,
        ))
        self.model_status = label("مدل اجرا نشده است.", name="muted")
        setup.add(self.model_status)
        outer.addWidget(setup)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addLayout(row(label("گفتگوها", bold=True), stretch=True))
        self.chat_list = QListWidget()
        self.chat_list.currentRowChanged.connect(self.load_chat)
        left_layout.addWidget(self.chat_list)
        left_layout.addLayout(row(
            button("گفتگوی جدید", primary=True, on_click=self.new_chat),
            button("حذف", danger=True, on_click=self.delete_chat),
        ))
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setObjectName("chat")
        right_layout.addWidget(self.chat_view, 1)
        self.sources_label = label("", name="muted")
        right_layout.addWidget(self.sources_label)
        self.use_library = QCheckBox("جستجو در کتابخانهٔ آفلاین برای پاسخ (ذکر منبع)")
        self.use_library.setChecked(bool(self.ctx.config.get("ai_use_library", True)))
        right_layout.addWidget(self.use_library)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("سوالت را اینجا بنویس... (Enter بفرست، Shift+Enter خط جدید)")
        self.input.setMaximumHeight(110)
        self.input.installEventFilter(self)
        self.send_btn = button("ارسال", primary=True, on_click=self.send)
        right_layout.addLayout(row(self.input, self.send_btn))
        splitter.addWidget(right)
        splitter.setSizes([260, 760])
        outer.addWidget(splitter, 1)

    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802 - امضای Qt
        from PySide6.QtCore import QEvent
        if obj is self.input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
                self.send()
                return True
        return super().eventFilter(obj, event)

    # ---------- سختافزار و مدل ----------
    def refresh_system(self) -> None:
        try:
            info_obj = detect()
            rec = recommend(info_obj)
            self.system_label.setText("سیستم شما: " + info_obj.summary_fa())
            p = rec["primary"]
            extra = (" " + rec["note"]) if rec.get("note") else ""
            self.rec_label.setText(
                f"پیشنهاد: {p['name']} — حجم {p['size_gb']} گیگ. {p['note']}{extra}\n"
                f"لینک دانلود در مرحلهٔ آمادهسازی: {p['url']}"
            )
        except Exception as exc:
            self.system_label.setText("سنجش سختافزار ممکن نشد.")
            self.rec_label.setText(str(exc))

    def refresh_models(self) -> None:
        self.model_combo.clear()
        models = self.ctx.llama.models()
        for m in models:
            self.model_combo.addItem(f"{m.name} ({human_size(m.stat().st_size)})", str(m))
        if not models:
            self.model_combo.addItem("هیچ مدلی پیدا نشد", "")
        self._sync_model_status()

    def _sync_model_status(self) -> None:
        running = self.ctx.llama.is_running()
        self.model_status.setText("🟢 مدل در حال اجراست." if running else "مدل اجرا نشده است.")
        self.start_btn.setText("توقف مدل" if running else "اجرای مدل")

    def toggle_model(self) -> None:
        if self.ctx.llama.is_running():
            self.ctx.llama.stop()
            self.bridge.toast.emit("مدل متوقف شد.", "accent")
        else:
            path = self.model_combo.currentData()
            if not path:
                show_error(self, "اول یک فایل GGUF در پوشهٔ data/models قرار بده.", self.ctx.logger)
                return
            try:
                self.model_status.setText("در حال بارگذاری مدل (ممکن است ۱ تا ۲ دقیقه طول بکشد)...")
                result = self.ctx.llama.start(Path(path))
                self.bridge.toast.emit("مدل آماده است.", "green")
                self.model_status.setText(
                    f"🟢 مدل اجرا شد — {result.get('gpu_layers')} لایه روی GPU، "
                    f"حافظهٔ زمینه {result.get('ctx')} توکن."
                )
            except Exception as exc:
                show_error(self, "اجرای مدل ممکن نشد.", self.ctx.logger, exc)
        self._sync_model_status()

    def import_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب مدل GGUF", "", "مدل GGUF (*.gguf)")
        if not path:
            return
        import shutil
        try:
            target = self.ctx.paths.models / Path(path).name
            self.bridge.toast.emit("در حال کپی مدل (ممکن است چند دقیقه طول بکشد)...", "accent")
            shutil.copy2(path, target)
            self.refresh_models()
            self.bridge.toast.emit("مدل وارد شد.", "green")
        except Exception as exc:
            show_error(self, "وارد کردن مدل ممکن نشد.", self.ctx.logger, exc)

    def import_server(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب llama-server.exe", "",
                                              "فایل اجرایی (*.exe);;همهٔ فایلها (*.*)")
        if not path:
            return
        import shutil
        try:
            target = self.ctx.paths.bin_dir / "llama-server.exe"
            shutil.copy2(path, target)
            self.bridge.toast.emit("llama-server.exe وارد شد.", "green")
        except Exception as exc:
            show_error(self, "وارد کردن فایل اجرایی ممکن نشد.", self.ctx.logger, exc)

    # ---------- تاریخچه ----------
    def refresh_chats(self) -> None:
        self.chat_list.clear()
        for chat in self.ctx.llama.list_chats():
            item = QListWidgetItem(f"{chat['title']}  ({chat['n']} پیام)")
            item.setData(Qt.UserRole, chat["id"])
            self.chat_list.addItem(item)

    def new_chat(self) -> None:
        model = self.model_combo.currentText() if self.model_combo.count() else ""
        self.current_chat = self.ctx.llama.create_chat("گفتگوی جدید", model)
        self.refresh_chats()
        self.chat_view.clear()
        self.sources_label.clear()

    def delete_chat(self) -> None:
        li = self.chat_list.currentItem()
        if not li or not confirm(self, "این گفتگو حذف شود؟"):
            return
        self.ctx.llama.delete_chat(int(li.data(Qt.UserRole)))
        self.current_chat = None
        self.refresh_chats()
        self.chat_view.clear()

    def load_chat(self, index: int) -> None:
        if index < 0 or index >= self.chat_list.count():
            return
        self.current_chat = int(self.chat_list.item(index).data(Qt.UserRole))
        self.chat_view.clear()
        for msg in self.ctx.llama.messages(self.current_chat):
            who = "🧑 شما" if msg.role == "user" else "🤖 همراه قطعی"
            self.chat_view.append(f"{who}:\n{msg.content}\n")
            if msg.sources:
                self.sources_label.setText("منابع: " + msg.sources)
        self.chat_view.moveCursor(QTextCursor.End)

    # ---------- ارسال ----------
    def send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.streaming:
            return
        if not self.ctx.llama.is_running():
            show_error(self, "اول مدل را اجرا کن (دکمهٔ «اجرای مدل»).", self.ctx.logger)
            return
        if self.current_chat is None:
            self.new_chat()
        assert self.current_chat is not None
        self.ctx.llama.add_message(self.current_chat, "user", text)
        self.chat_view.append(f"🧑 شما:\n{text}\n")
        self.input.clear()
        self.chat_view.append("🤖 همراه قطعی:\n")
        self.chat_view.moveCursor(QTextCursor.End)

        messages = [{"role": m.role, "content": m.content}
                    for m in self.ctx.llama.messages(self.current_chat)]
        context, sources = ("", "")
        if self.use_library.isChecked():
            context, source_list = self.ctx.llama.make_context(text, self.ctx.library)
            sources = " | ".join(source_list)
            self.sources_label.setText("منابع: " + sources if sources else "")

        self.streaming = True
        self.send_btn.setEnabled(False)
        self.worker = ChatWorker(self.ctx, messages, context, sources)
        self.worker.token.connect(self.on_token)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_token(self, token: str) -> None:
        self.chat_view.moveCursor(QTextCursor.End)
        self.chat_view.insertPlainText(token)
        self.chat_view.moveCursor(QTextCursor.End)

    def on_done(self, answer: str, sources: str) -> None:
        self.streaming = False
        self.send_btn.setEnabled(True)
        self.chat_view.append("\n")
        if self.current_chat:
            self.ctx.llama.add_message(self.current_chat, "assistant", answer, sources)
            if self.chat_list.count() and self.ctx.llama.messages(self.current_chat):
                first = self.ctx.llama.list_chats()
                for c in first:
                    if c["id"] == self.current_chat and c["title"] == "گفتگوی جدید":
                        self.ctx.llama.rename_chat(self.current_chat, answer[:40].replace("\n", " "))
                        self.refresh_chats()
                        break
        self.chat_view.moveCursor(QTextCursor.End)

    def on_failed(self, message: str) -> None:
        self.streaming = False
        self.send_btn.setEnabled(True)
        self.chat_view.append(f"\n❌ {message}\n")
