"""صفحهٔ ۲ — کیف آمادگی: صف دانلود قابلادامه + چکلیست."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QHBoxLayout, QHeaderView,
    QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.downloader import STATUS_FA
from ..core.persian import human_size, to_persian_digits
from .common import Card, button, confirm, info, label, progress_bar, row, show_error, title_block


class ReadinessPage(QWidget):
    def __init__(self, ctx: Any, bridge: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.bridge = bridge
        self._bars: dict[int, QProgressBar] = {}
        tabs = QTabWidget()
        tabs.addTab(self._downloads_tab(), "صف دانلود")
        tabs.addTab(self._checklist_tab(), "چکلیست آمادگی")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.addWidget(title_block("کیف آمادگی",
                                    "هر چیزی که قبل از قطعی لازم داری اینجا جمع کن. دانلودها بعد از قطعی از همانجا ادامه پیدا میکنند."))
        outer.addWidget(tabs, 1)

    # ---------------- صف دانلود ----------------
    def _downloads_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        add_card = Card()
        add_card.add(label("افزودن به صف", bold=True))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip  یا آدرس یک صفحهٔ وب")
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["فایل", "صفحهٔ وب کامل (همراه عکسها)"])
        self.add_btn = button("افزودن", primary=True, on_click=self.add_item)
        add_card.add_layout(row(self.url_edit, self.kind_combo, self.add_btn))
        self.queue_hint = label("", name="muted")
        add_card.add(self.queue_hint)
        layout.addWidget(add_card)

        table_card = Card()
        head = row(label("لیست دانلودها", bold=True),
                   button("توقف صف", on_click=self.pause),
                   button("ادامهٔ صف", on_click=self.resume),
                   button("حذف انتخابشده", danger=True, on_click=self.remove_selected),
                   button("تلاش مجدد", on_click=self.retry_selected),
                   button("بروزرسانی", on_click=self.refresh), stretch=True)
        table_card.add_layout(head)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["نام", "نوع", "وضعیت", "حجم", "پیشرفت", "خطا"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        table_card.add(self.table)
        layout.addWidget(table_card, 1)
        self.refresh()
        return w

    def add_item(self) -> None:
        url = self.url_edit.text().strip()
        if not url.startswith(("http://", "https://")):
            show_error(self, "لطفاً یک آدرس معتبر با http یا https وارد کن.", self.ctx.logger)
            return
        try:
            if self.kind_combo.currentIndex() == 1:
                self.ctx.queue.add_page(url)
            else:
                self.ctx.queue.add_file(url)
            self.url_edit.clear()
            self.refresh()
            self.bridge.toast.emit("به صف دانلود اضافه شد.", "green")
        except Exception as exc:
            show_error(self, "افزودن به صف ممکن نشد.", self.ctx.logger, exc)

    def _selected_id(self) -> int | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row_idx = items[0].row()
        item = self.table.item(row_idx, 0)
        return int(item.data(Qt.UserRole)) if item else None

    def remove_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is None:
            return
        if not confirm(self, "این آیتم از صف حذف شود؟ فایل نیمهدانلودشده هم پاک میشود."):
            return
        self.ctx.queue.remove(item_id, delete_files=True)
        self.refresh()

    def retry_selected(self) -> None:
        item_id = self._selected_id()
        if item_id:
            self.ctx.queue.retry(item_id)
            self.refresh()

    def pause(self) -> None:
        self.ctx.queue.pause_all()
        self.bridge.toast.emit("صف دانلود توسط شما متوقف شد.", "yellow")
        self.refresh()

    def resume(self) -> None:
        self.ctx.queue.resume_all()
        self.bridge.toast.emit("صف دوباره فعال شد.", "green")
        self.refresh()

    def refresh(self) -> None:
        items = self.ctx.queue.list_items()
        self.table.setRowCount(len(items))
        self._bars.clear()
        for r, item in enumerate(items):
            name = QTableWidgetItem(item.name)
            name.setData(Qt.UserRole, item.id)
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem("صفحهٔ وب" if item.kind == "page" else "فایل"))
            self.table.setItem(r, 2, QTableWidgetItem(STATUS_FA.get(item.status, item.status)))
            total = human_size(item.bytes_total) if item.bytes_total else human_size(item.bytes_done)
            self.table.setItem(r, 3, QTableWidgetItem(total))
            bar = progress_bar()
            pct = int(100 * item.bytes_done / item.bytes_total) if item.bytes_total else (100 if item.status == "done" else 0)
            bar.setValue(max(0, min(100, pct)))
            self.table.setCellWidget(r, 4, bar)
            self._bars[item.id] = bar
            self.table.setItem(r, 5, QTableWidgetItem((item.error or "")[:80]))
        state = self.ctx.current_state.value
        if self.ctx.queue.user_paused:
            self.queue_hint.setText("صف توسط شما متوقف شده است.")
        elif state != "free" and self.ctx.config.get("auto_pause_on_national", True):
            self.queue_hint.setText("⏸ بهخاطر وضعیت اینترنت، صف متوقف است؛ با برگشتن نت آزاد خودکار ادامه میدهد.")
        else:
            self.queue_hint.setText("▶ صف فعال است.")

    def on_progress(self, item_id: int, done: int, total: int) -> None:
        bar = self._bars.get(item_id)
        if bar:
            bar.setValue(int(100 * done / total) if total else 0)

    def on_event(self, kind: str, payload: Any) -> None:
        if kind == "finished":
            item = self.ctx.queue.get(int(payload["id"]))
            if item and item.kind == "page":
                index_html = Path(item.dest) / "index.html"
                if index_html.is_file():
                    try:
                        self.ctx.library.index_file(index_html, source="page:" + str(index_html.parent))
                    except Exception:
                        pass
            self.bridge.toast.emit(f"دانلود «{payload.get('name', '')}» تمام شد.", "green")
        elif kind == "error":
            self.bridge.toast.emit("دانلود با خطا روبرو شد؛ دوباره تلاش میکنیم.", "red")
        self.refresh()

    # ---------------- چکلیست ----------------
    def _checklist_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        card = Card()
        card.add(label("چکلیست آمادگی", bold=True))
        card.add(label("موارد آماده را تیک بزن. میتوانی آیتم دلخواه اضافه یا حذف کنی.", name="muted"))
        self.check_edit = QLineEdit()
        self.check_edit.setPlaceholderText("مثلاً: دانلود دفترچهٔ راهنمای مودم")
        card.add_layout(row(self.check_edit,
                            button("افزودن آیتم", primary=True, on_click=self.add_check),
                            button("حذف آیتم انتخابشده", danger=True, on_click=self.remove_check),
                            button("کپی لینک", on_click=self.copy_link)))
        self.progress_label = label("", name="subtitle")
        card.add(self.progress_label)
        self.check_list = QListWidget()
        self.check_list.itemChanged.connect(self.on_check_changed)
        card.add(self.check_list)
        layout.addWidget(card, 1)
        self.refresh_checklist()
        return w

    def refresh_checklist(self) -> None:
        self.check_list.blockSignals(True)
        self.check_list.clear()
        for item in self.ctx.checklist.items():
            li = QListWidgetItem(f"[{item['category']}] {item['title']}")
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked if item["done"] else Qt.Unchecked)
            li.setData(Qt.UserRole, item["id"])
            if item["note"] or item["link"]:
                li.setToolTip((item["note"] + "\n" + item["link"]).strip())
            self.check_list.addItem(li)
        done, total = self.ctx.checklist.progress()
        self.progress_label.setText(to_persian_digits(
            f"انجامشده: {done} از {total} مورد" + (f"  ({int(100 * done / total)}٪)" if total else "")
        ))
        self.check_list.blockSignals(False)

    def on_check_changed(self, li: QListWidgetItem) -> None:
        try:
            self.ctx.checklist.toggle(int(li.data(Qt.UserRole)), li.checkState() == Qt.Checked)
        except Exception:
            pass
        done, total = self.ctx.checklist.progress()
        self.progress_label.setText(to_persian_digits(
            f"انجامشده: {done} از {total} مورد" + (f"  ({int(100 * done / total)}٪)" if total else "")
        ))

    def add_check(self) -> None:
        text = self.check_edit.text().strip()
        if not text:
            return
        self.ctx.checklist.add(text)
        self.check_edit.clear()
        self.refresh_checklist()

    def remove_check(self) -> None:
        li = self.check_list.currentItem()
        if not li:
            return
        if confirm(self, "این آیتم حذف شود؟"):
            self.ctx.checklist.remove(int(li.data(Qt.UserRole)))
            self.refresh_checklist()

    def copy_link(self) -> None:
        li = self.check_list.currentItem()
        if not li:
            return
        item_id = int(li.data(Qt.UserRole))
        item = next((x for x in self.ctx.checklist.items() if x["id"] == item_id), None)
        if item and item["link"]:
            QApplication.clipboard().setText(item["link"])
            self.bridge.toast.emit("لینک کپی شد.", "accent")
        else:
            info("برای این آیتم لینکی ثبت نشده است.", self)
