"""پنجرهٔ اصلی — ناوبری راستبهچپ، اعلانهای ویندوز و اتصال نخها به صفحهها."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .. import APP_NAME_FA
from ..core.jalali import format_date
from ..core.logging_setup import log_exception
from ..core.persian import human_size
from .common import Bridge, badge, button, label
from .dashboard import DashboardPage
from .readiness import ReadinessPage
from .library_view import LibraryPage
from .chat_view import ChatPage
from .lan_view import LanPage
from .settings_view import SettingsPage
from .theme import apply_theme, load_fonts
from .workers import DownloadWorker, ProbeWorker

NAV = [
    ("📊", "داشبورد وضعیت", 1),
    ("🎒", "کیف آمادگی", 2),
    ("📚", "کتابخانهٔ آفلاین", 3),
    ("🤖", "دستیار آفلاین", 4),
    ("🖧", "شبکهٔ محلی", 5),
    ("⚙️", "تنظیمات", 5),
]


def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor("#2f6fed"))
    painter = QPainter(pix)
    painter.setPen(QColor("white"))
    font = QFont()
    font.setPointSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, "ه")
    painter.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self, ctx: Any, *, stage: int = 5, demo: bool = False,
                 app: QApplication | None = None) -> None:
        super().__init__()
        self.ctx = ctx
        self.app = app or QApplication.instance()
        self.stage = max(1, min(5, stage))
        self.demo = demo
        self.bridge = Bridge()
        self.font_family = load_fonts(self.ctx.paths.fonts)
        self.pages: dict[str, QWidget] = {}
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self.toast_label.hide())

        self.setWindowTitle(APP_NAME_FA + " — همراه روزهای قطعی اینترنت")
        self.setWindowIcon(make_icon())
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1180, 760)
        self._build()
        self._connect_bridge()
        self.apply_theme()
        self._start_workers()
        self._start_tray()
        if self.ctx.config.get("start_minimized"):
            self.hide()

    # ---------- ساخت رابط ----------
    def _build(self) -> None:
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # نوار بالا
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(58)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(16, 6, 16, 6)
        title = label("همراه قطعی", bold=True)
        title.setStyleSheet("font-size: 15pt; font-weight: bold;")
        self.state_badge = badge("⚪ در حال بررسی")
        self.date_label = label(format_date(datetime.now(), with_weekday=True), name="muted")
        self.theme_btn = button("🌙", on_click=self.toggle_theme)
        self.theme_btn.setFixedWidth(42)
        top_layout.addWidget(title)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.state_badge)
        top_layout.addStretch(1)
        top_layout.addWidget(self.date_label)
        top_layout.addWidget(self.theme_btn)
        main_layout.addWidget(topbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(215)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 14, 10, 14)
        side_layout.setSpacing(6)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.stack = QStackedWidget()

        self.dashboard = DashboardPage(self.ctx, self.bridge)
        self.readiness = ReadinessPage(self.ctx, self.bridge)
        self.library = LibraryPage(self.ctx, self.bridge)
        self.chat = ChatPage(self.ctx, self.bridge)
        self.lan = LanPage(self.ctx, self.bridge)
        self.settings = SettingsPage(self.ctx, self.bridge,
                                     on_theme=self.apply_theme,
                                     on_saved=self.restart_lan)
        self.pages = {
            "داشبورد وضعیت": self.dashboard, "کیف آمادگی": self.readiness,
            "کتابخانهٔ آفلاین": self.library, "دستیار آفلاین": self.chat,
            "شبکهٔ محلی": self.lan, "تنظیمات": self.settings,
        }
        for idx, (emoji, name, min_stage) in enumerate(NAV):
            if min_stage > self.stage:
                continue
            btn = QPushButton(f"  {emoji}   {name}")
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setCursor(Qt.PointingHandCursor)
            page_index = self.stack.addWidget(self.pages[name])
            btn.clicked.connect(lambda _checked=False, i=page_index: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(btn)
            side_layout.addWidget(btn)
        side_layout.addStretch(1)
        version = label("نسخهٔ ۱٫۰ — آفلاین", name="muted")
        side_layout.addWidget(version)
        body.addWidget(sidebar)
        body.addWidget(self.stack, 1)
        main_layout.addLayout(body, 1)

        self.toast_label = label("", name="badge")
        self.toast_label.setAlignment(Qt.AlignCenter)
        self.toast_label.setVisible(False)
        main_layout.addWidget(self.toast_label)
        self.setCentralWidget(central)

        self.date_timer = QTimer(self)
        self.date_timer.timeout.connect(
            lambda: self.date_label.setText(format_date(datetime.now(), with_weekday=True)))
        self.date_timer.start(60_000)

    def _connect_bridge(self) -> None:
        self.bridge.toast.connect(self.show_toast)
        self.bridge.offer.connect(self.ask_offer)
        self.bridge.net_checked.connect(self.dashboard.update_state)
        self.bridge.download_event.connect(self.readiness.on_event)
        self.bridge.download_progress.connect(self.readiness.on_progress)

    def _start_workers(self) -> None:
        self.probe_worker = ProbeWorker(self.ctx, demo=self.demo)
        self.probe_worker.checked.connect(self.on_checked)
        self.probe_worker.changed.connect(self.on_changed)
        self.probe_worker.failed.connect(
            lambda msg: self.ctx.logger.error("خطای تست اتصال: %s", msg))
        self.probe_worker.start()

        self.download_worker = DownloadWorker(self.ctx)
        self.download_worker.event.connect(self.readiness.on_event)
        self.download_worker.progress.connect(self.readiness.on_progress)
        self.download_worker.start()
        self.lan.start_lan()

    def _start_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.ctx.logger.info("سینی سیستم در دسترس نیست؛ فقط اعلان درونبرنامهای نشان داده میشود.")
            return
        from PySide6.QtWidgets import QMenu
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME_FA)
        menu = QMenu()
        menu.setLayoutDirection(Qt.RightToLeft)
        show_action = menu.addAction("نمایش برنامه")
        show_action.triggered.connect(self.showNormal)
        quit_action = menu.addAction("خروج")
        quit_action.triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.showNormal() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    # ---------- اعلانها ----------
    def show_toast(self, text: str, tone: str = "accent") -> None:
        colors = {
            "green": ("#e4f6ec", "#0f9d58"), "yellow": ("#fff4d9", "#a57400"),
            "red": ("#fde7e9", "#c02c3a"), "accent": ("#e5edff", "#2f6fed"),
        }
        bg, fg = colors.get(tone, colors["accent"])
        self.toast_label.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:8px; padding:8px; font-weight:bold;")
        self.toast_label.setText(text)
        self.toast_label.setVisible(True)
        self._toast_timer.start(5000)

    def on_checked(self, payload: dict[str, Any]) -> None:
        self.state_badge.setText(f"{payload['emoji']} {payload['label']}")
        self.bridge.net_checked.emit(payload)

    def on_changed(self, change: dict[str, Any]) -> None:
        self.show_toast(f"{change['title']} — {change['message']}",
                        "green" if change.get("returned") else "yellow")
        self.dashboard.refresh_history()
        if self.tray and self.ctx.config.get("notify_on_change", True):
            self.tray.showMessage(change["title"], change["message"],
                                  QSystemTrayIcon.Information, 12000)
        if change.get("returned") and self.ctx.config.get("notify_on_return", True):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("اینترنت جهانی برگشت")
            box.setText("🟢 اینترنت آزاد شد!\n\n" + change["message"] +
                        "\n\nصف دانلود را همین الان بررسی کنی؟")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.button(QMessageBox.Yes).setText("بله، برو به کیف آمادگی")
            box.button(QMessageBox.No).setText("بعداً")
            box.setLayoutDirection(Qt.RightToLeft)
            if box.exec() == QMessageBox.Yes and self.stage >= 2:
                self.stack.setCurrentWidget(self.readiness)

    def ask_offer(self, offer: Any, box: Any) -> None:
        """تأیید دریافت فایل — حتماً در نخ اصلی اجرا میشود."""
        event, result = box
        try:
            reply = QMessageBox.question(
                self, "دریافت فایل",
                f"دستگاه مقابل میخواهد فایلی بفرستد:\n\n"
                f"نام: {offer.name}\nحجم: {human_size(offer.size)}\n"
                f"شناسه: {offer.file_id[:12]}\n\nآیا دریافت شود؟",
                QMessageBox.Yes | QMessageBox.No,
            )
            result.append(reply == QMessageBox.Yes)
        except Exception:
            result.append(False)
        finally:
            event.set()

    # ---------- تم و چرخهٔ حیات ----------
    def apply_theme(self) -> None:
        theme = str(self.ctx.config.get("theme", "light"))
        size = int(self.ctx.config.get("font_size", 10))
        apply_theme(self.app, theme, self.font_family, size)
        self.dashboard.chart.dark = theme == "dark"
        self.dashboard.chart.update()
        self.theme_btn.setText("☀️" if theme == "dark" else "🌙")

    def toggle_theme(self) -> None:
        new_theme = "dark" if self.ctx.config.get("theme") == "light" else "light"
        self.ctx.save_settings({"theme": new_theme})
        self.settings.load()
        self.apply_theme()

    def restart_lan(self) -> None:
        try:
            self.ctx.lan.stop()
            self.lan.start_lan()
        except Exception as exc:
            log_exception(self.ctx.logger, "راهاندازی مجدد شبکهٔ محلی", exc)

    def quit_app(self) -> None:
        self._really_quit = True
        self.close()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - امضای Qt
        if (not getattr(self, "_really_quit", False)
                and self.ctx.config.get("minimize_to_tray", True)
                and self.tray is not None):
            event.ignore()
            self.hide()
            self.tray.showMessage(APP_NAME_FA, "برنامه همچنان در پسزمینه وضعیت اینترنت را بررسی میکند.",
                                  QSystemTrayIcon.Information, 4000)
            return
        try:
            self.probe_worker.stop()
            self.download_worker.stop()
            self.probe_worker.wait(3000)
            self.download_worker.wait(3000)
            self.ctx.shutdown()
        except Exception as exc:
            log_exception(self.ctx.logger, "بستن برنامه", exc)
        event.accept()
