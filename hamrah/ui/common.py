"""ابزارکها و کمکتابعهای مشترک رابط کاربری."""
from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QProgressBar, QSizePolicy,
)

from ..core.errors import friendly
from ..core.jalali import format_datetime
from ..core.logging_setup import log_exception
from ..core.persian import human_size, to_persian_digits


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)

    def add(self, widget: Any) -> None:
        """هم QWidget و هم QLayout را میپذیرد (برای راحتی صفحهها)."""
        from PySide6.QtWidgets import QLayout
        if isinstance(widget, QLayout):
            self._layout.addLayout(widget)
        else:
            self._layout.addWidget(widget)

    def add_layout(self, layout: Any) -> None:
        self._layout.addLayout(layout)

    @property
    def body(self) -> QVBoxLayout:
        return self._layout


def label(text: str, *, name: str = "", bold: bool = False, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    if bold:
        lbl.setStyleSheet("font-weight: bold;")
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def button(text: str, *, primary: bool = False, danger: bool = False,
           on_click: Callable[[], None] | None = None) -> QPushButton:
    btn = QPushButton(text)
    if primary:
        btn.setObjectName("primary")
    if danger:
        btn.setObjectName("danger")
    btn.setCursor(Qt.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def row(*widgets: QWidget, stretch: bool = False) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for w in widgets:
        layout.addWidget(w)
    if stretch:
        layout.addStretch(1)
    return layout


def title_block(title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(label(title, name="title"))
    if subtitle:
        layout.addWidget(label(subtitle, name="subtitle"))
    return w


def badge(text: str, tone: str = "accent") -> QLabel:
    names = {"green": "badgeGreen", "yellow": "badgeYellow", "red": "badgeRed"}
    return label(text, name=names.get(tone, "badge"), wrap=False)


def progress_bar() -> QProgressBar:
    bar = QProgressBar()
    bar.setMinimum(0)
    bar.setMaximum(100)
    bar.setValue(0)
    bar.setTextVisible(True)
    bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return bar


def show_error(parent: QWidget, message: str, logger: Any | None = None,
               exc: BaseException | None = None) -> None:
    if exc is not None and logger is not None:
        message = log_exception(logger, message, exc)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("همراه قطعی — مشکل")
    box.setText(message)
    box.setStandardButtons(QMessageBox.Ok)
    box.setLayoutDirection(Qt.RightToLeft)
    box.exec()


def confirm(parent: QWidget, text: str, title: str = "تأیید") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.button(QMessageBox.Yes).setText("بله")
    box.button(QMessageBox.No).setText("خیر")
    box.setLayoutDirection(Qt.RightToLeft)
    return box.exec() == QMessageBox.Yes


def info(text: str, parent: QWidget | None = None) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Information)
    box.setWindowTitle("همراه قطعی")
    box.setText(text)
    box.setLayoutDirection(Qt.RightToLeft)
    box.exec()


class Bridge(QObject):
    """پلی برای اجرای امن کارهای UI از نخهای پسزمینه."""
    toast = Signal(str, str)            # (پیام، لحن: green/yellow/red/accent)
    offer = Signal(object, object)      # (FileOffer, (threading.Event, result_box))
    refresh = Signal()
    lan_message = Signal(str, str, str)      # peer_id, name, text
    lan_progress = Signal(object, int, int) # FileOffer, done, total
    lan_peers = Signal(object)
    lan_file_done = Signal(object, str)     # FileOffer, path
    net_checked = Signal(object)
    net_changed = Signal(object)
    download_event = Signal(str, object)
    download_progress = Signal(int, int, int)


def fmt_time(ts: float) -> str:
    from datetime import datetime
    return format_datetime(datetime.fromtimestamp(ts))


def fmt_size(n: float) -> str:
    return human_size(n)
