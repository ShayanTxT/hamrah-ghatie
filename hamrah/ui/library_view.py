"""صفحهٔ ۳ — کتابخانهٔ آفلاین (فایلهای شخصی + ZIM ویکیپدیا)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ..core.persian import truncate
from .common import Card, button, confirm, info, label, row, show_error, title_block
from .workers import IndexWorker


class CopyWorker(QThread):
    progress = Signal(int, int)
    done = Signal(str, str)

    def __init__(self, source: Path, target: Path) -> None:
        super().__init__()
        self.source, self.target = source, target

    def run(self) -> None:
        try:
            total = self.source.stat().st_size
            done = 0
            with open(self.source, "rb") as src, open(self.target, "wb") as dst:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    dst.write(block)
                    done += len(block)
                    self.progress.emit(done, total)
            self.done.emit(str(self.target), "")
        except Exception as exc:
            self.done.emit("", str(exc))


class LibraryPage(QWidget):
    def __init__(self, ctx: Any, bridge: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.bridge = bridge
        self.results: list[Any] = []
        self.worker: IndexWorker | None = None
        self.copier: CopyWorker | None = None
        self._build()
        self.refresh_stats()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)
        outer.addWidget(title_block("کتابخانهٔ آفلاین",
                                    "ویکیپدیای ZIM، PDFها، صفحههای ذخیرهشده و فایلهای متنی — همه با جستجوی تماممتن فارسی"))

        actions = Card()
        actions.add_layout(row(
            button("اسکن پوشهٔ کتابخانه", primary=True, on_click=self.scan),
            button("وارد کردن فایل ZIM", on_click=self.import_zim),
            button("وارد کردن فایل از فلش", on_click=self.import_file),
            button("باز کردن پوشهٔ data", on_click=self.open_data_dir),
            stretch=True,
        ))
        self.stats_label = label("", name="subtitle")
        actions.add(self.stats_label)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        actions.add(self.progress)
        self.status_label = label("", name="muted")
        actions.add(self.status_label)
        outer.addWidget(actions)

        search_card = Card()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("مثلاً: اینترنت ملی  یا  قطعی شبکه  (ی/ي، ک/ك و نیمفاصله یکی حساب میشوند)")
        self.search_edit.returnPressed.connect(self.search)
        search_card.add_layout(row(self.search_edit, button("جستجو", primary=True, on_click=self.search)))
        outer.addWidget(search_card)

        splitter = QSplitter(Qt.Horizontal)
        self.result_list = QListWidget()
        self.result_list.currentRowChanged.connect(self.show_preview)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        splitter.addWidget(self.result_list)
        splitter.addWidget(self.preview)
        splitter.setSizes([420, 620])
        outer.addWidget(splitter, 1)

        zim_card = Card()
        zim_card.add_layout(row(label("فایلهای ZIM اضافهشده", bold=True), stretch=True))
        self.zim_combo = QComboBox()
        zim_card.add(self.zim_combo)
        zim_card.add_layout(row(
            button("حذف ایندکس ZIM انتخابشده", danger=True, on_click=self.remove_zim),
            button("جستجوی عنوان در ZIM", on_click=self.search_zim_titles),
            stretch=True,
        ))
        outer.addWidget(zim_card)
        self.refresh_zim_list()

    # ---------- اسکن و وارد کردن ----------
    def _start_worker(self, task: str, path: str = "") -> None:
        if self.worker and self.worker.isRunning():
            info("یک کار ایندکسگذاری در حال انجام است.", self)
            return
        self.worker = IndexWorker(self.ctx, task, path)
        self.worker.progress.connect(self.on_index_progress)
        self.worker.done.connect(self.on_index_done)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.worker.start()

    def scan(self) -> None:
        self.status_label.setText("در حال اسکن فایلها...")
        self._start_worker("scan")

    def on_index_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)
        self.status_label.setText(f"{done}/{total} — {name}")

    def on_index_done(self, result: Any) -> None:
        self.progress.setVisible(False)
        if isinstance(result, dict) and result.get("error"):
            self.status_label.setText("خطا در ایندکسگذاری.")
            show_error(self, "ایندکسگذاری انجام نشد.", self.ctx.logger,
                       RuntimeError(result["error"]))
            return
        self.status_label.setText("انجام شد.")
        self.refresh_stats()
        self.refresh_zim_list()
        self.search()
        self.bridge.toast.emit("کتابخانه بهروز شد.", "green")

    def import_zim(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل ZIM", "",
                                             "فایلهای ZIM (*.zim);;همهٔ فایلها (*.*)")
        if not path:
            return
        source = Path(path)
        box = QMessageBox(self)
        box.setWindowTitle("وارد کردن ZIM")
        box.setText("فایل را به پوشهٔ data کپی کنیم (تا با کپی کردن برنامه منتقل شود) یا فقط مسیرش را ثبت کنیم؟")
        copy_btn = box.addButton("کپی به data (پیشنهادی)", QMessageBox.AcceptRole)
        link_btn = box.addButton("فقط ثبت مسیر", QMessageBox.DestructiveRole)
        box.addButton("انصراف", QMessageBox.RejectRole)
        box.setLayoutDirection(Qt.RightToLeft)
        box.exec()
        clicked = box.clickedButton()
        if clicked is copy_btn:
            target = self.ctx.paths.zim / source.name
            if target.exists() and target.stat().st_size == source.stat().st_size:
                self._index_zim(target)
                return
            self.progress.setVisible(True)
            self.progress.setMaximum(100)
            self.copier = CopyWorker(source, target)
            self.copier.progress.connect(
                lambda d, t: (self.progress.setValue(int(100 * d / t) if t else 0),
                              self.status_label.setText(f"در حال کپی: {int(100 * d / t) if t else 0}٪"))
            )
            self.copier.done.connect(lambda p, err: self._on_copy_done(p, err))
            self.status_label.setText("در حال کپی فایل ZIM...")
            self.copier.start()
        elif clicked is link_btn:
            self._index_zim(source)

    def _on_copy_done(self, path: str, error: str) -> None:
        self.progress.setVisible(False)
        if error or not path:
            show_error(self, "کپی فایل ZIM ممکن نشد.", self.ctx.logger, RuntimeError(error or "خطای نامشخص"))
            return
        self._index_zim(Path(path))

    def _index_zim(self, path: Path) -> None:
        self.status_label.setText("در حال ایندکس کردن مقالههای ZIM (ممکن است چند دقیقه طول بکشد)...")
        self._start_worker("zim", str(path))

    def import_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "انتخاب فایلها", "",
            "فایلهای پشتیبانیشده (*.pdf *.html *.htm *.txt *.md *.docx *.epub *.csv *.json);;همهٔ فایلها (*.*)"
        )
        if not paths:
            return
        target_dir = self.ctx.paths.library / "فایلهای من"
        target_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for p in paths:
            try:
                shutil.copy2(p, target_dir / Path(p).name)
                count += 1
            except OSError as exc:
                show_error(self, f"کپی {Path(p).name} انجام نشد.", self.ctx.logger, exc)
        self.bridge.toast.emit(f"{count} فایل وارد شد. حالا «اسکن پوشهٔ کتابخانه» را بزن.", "green")

    def open_data_dir(self) -> None:
        path = str(self.ctx.paths.root)
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            show_error(self, "باز کردن پوشه ممکن نشد.", self.ctx.logger, exc)

    def remove_zim(self) -> None:
        path = self.zim_combo.currentData()
        if not path:
            return
        if not confirm(self, "ایندکس این ZIM حذف شود؟ (خود فایل ZIM پاک نمیشود)"):
            return
        try:
            n = self.ctx.library.remove_zim(Path(path))
            self.bridge.toast.emit(f"ایندکس {n} مقاله حذف شد.", "accent")
        except Exception as exc:
            show_error(self, "حذف ایندکس ممکن نشد.", self.ctx.logger, exc)
        self.refresh_zim_list()
        self.refresh_stats()

    def search_zim_titles(self) -> None:
        query = self.search_edit.text().strip()
        if not query:
            info("اول یک عبارت در کادر جستجو بنویس.", self)
            return
        from ..core.zim_reader import open_zim
        path = self.zim_combo.currentData()
        if not path:
            info("اول یک فایل ZIM وارد کن.", self)
            return
        try:
            archive = open_zim(path)
            hits = archive.search_titles(query, limit=30)
            archive.close()
            self.result_list.clear()
            for e in hits:
                self.result_list.addItem(QListWidgetItem(f"📖 {e.title} — {e.full_path}"))
            self.status_label.setText(f"{len(hits)} عنوان در ZIM پیدا شد.")
        except Exception as exc:
            show_error(self, "جستجو در ZIM ممکن نشد.", self.ctx.logger, exc)

    # ---------- جستجو ----------
    def search(self) -> None:
        query = self.search_edit.text().strip()
        try:
            self.results = self.ctx.library.search(query, limit=50)
        except Exception as exc:
            show_error(self, "جستجو انجام نشد.", self.ctx.logger, exc)
            return
        self.result_list.clear()
        for hit in self.results:
            item = QListWidgetItem(f"{hit.title}\n   {truncate(hit.snippet, 110)}")
            item.setToolTip(f"{hit.source_label} — {hit.path}")
            self.result_list.addItem(item)
        self.status_label.setText(f"{len(self.results)} نتیجه پیدا شد.")

    def show_preview(self, index: int) -> None:
        if index < 0 or index >= len(self.results):
            self.preview.clear()
            return
        hit = self.results[index]
        doc = self.ctx.library.get_by_path(hit.path) or {}
        body = doc.get("content") or hit.content or hit.snippet
        self.preview.setPlainText(
            f"{hit.title}\nمنبع: {hit.source_label}\nمسیر: {hit.path}\n\n"
            + "─" * 50 + "\n\n" + body[:20000]
        )

    def refresh_stats(self) -> None:
        stats = self.ctx.library.stats()
        self.stats_label.setText(
            f"اسناد ایندکسشده: {stats['documents']}  •  فایلهای ZIM: {stats['zim_files']}"
        )

    def refresh_zim_list(self) -> None:
        self.zim_combo.clear()
        for z in self.ctx.library.zim_list():
            self.zim_combo.addItem(f"{z['title']} — {z['indexed_count']} مقاله", z["path"])
