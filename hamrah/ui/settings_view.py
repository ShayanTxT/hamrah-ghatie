"""صفحهٔ تنظیمات — مقادیر در data/settings.json ذخیره میشوند."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QLineEdit, QPlainTextEdit,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .common import Card, button, info, label, row, show_error, title_block


class SettingsPage(QWidget):
    def __init__(self, ctx: Any, bridge: Any, on_theme: Callable[[], None],
                 on_saved: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.bridge = bridge
        self.on_theme = on_theme
        self.on_saved = on_saved
        self.widgets: dict[str, Any] = {}
        self._build()
        self.load()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.addWidget(title_block("تنظیمات", "همهٔ تنظیمات در پوشهٔ data کنار برنامه ذخیره میشوند."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(12)

        # ظاهر
        ui = Card()
        ui.add(label("ظاهر برنامه", bold=True))
        form = QFormLayout()
        self.widgets["theme"] = QComboBox()
        self.widgets["theme"].addItems(["روشن", "تیره"])
        self.widgets["font_size"] = QSpinBox()
        self.widgets["font_size"].setRange(8, 16)
        form.addRow("حالت رابط:", self.widgets["theme"])
        form.addRow("اندازهٔ فونت:", self.widgets["font_size"])
        ui.add_layout(form)
        layout.addWidget(ui)

        # وضعیت اتصال
        net = Card()
        net.add(label("تشخیص وضعیت اتصال", bold=True))
        form2 = QFormLayout()
        self.widgets["check_interval"] = QSpinBox()
        self.widgets["check_interval"].setRange(3, 300)
        self.widgets["check_interval"].setSuffix(" ثانیه")
        self.widgets["hysteresis_up"] = QSpinBox()
        self.widgets["hysteresis_up"].setRange(1, 10)
        self.widgets["hysteresis_down"] = QSpinBox()
        self.widgets["hysteresis_down"].setRange(1, 10)
        self.widgets["internal_hosts"] = QPlainTextEdit()
        self.widgets["internal_hosts"].setMaximumHeight(80)
        self.widgets["external_urls"] = QPlainTextEdit()
        self.widgets["external_urls"].setMaximumHeight(80)
        self.widgets["external_tcp"] = QPlainTextEdit()
        self.widgets["external_tcp"].setMaximumHeight(70)
        self.widgets["dns_servers"] = QPlainTextEdit()
        self.widgets["dns_servers"].setMaximumHeight(60)
        form2.addRow("فاصلهٔ تستها:", self.widgets["check_interval"])
        form2.addRow("نمونههای پیاپی (بهتر شدن):", self.widgets["hysteresis_up"])
        form2.addRow("نمونههای پیاپی (بدتر شدن):", self.widgets["hysteresis_down"])
        form2.addRow("سایتهای داخلی (هر خط یک آدرس):", self.widgets["internal_hosts"])
        form2.addRow("آدرسهای خارجی (هر خط یک آدرس):", self.widgets["external_urls"])
        form2.addRow("TCP خارجی (هر خط host:port):", self.widgets["external_tcp"])
        form2.addRow("سرورهای DNS (هر خط یک IP):", self.widgets["dns_servers"])
        net.add_layout(form2)
        layout.addWidget(net)

        # دانلود و AI
        tools = Card()
        tools.add(label("کیف آمادگی و دستیار", bold=True))
        form3 = QFormLayout()
        self.widgets["auto_pause_on_national"] = QCheckBox("توقف خودکار صف دانلود در حالت «فقط ملی»")
        self.widgets["ai_use_library"] = QCheckBox("دستیار از کتابخانهٔ آفلاین هم استفاده کند")
        self.widgets["llama_ctx"] = QSpinBox()
        self.widgets["llama_ctx"].setRange(1024, 32768)
        self.widgets["llama_ctx"].setSingleStep(512)
        self.widgets["llama_gpu_layers"] = QSpinBox()
        self.widgets["llama_gpu_layers"].setRange(-1, 200)
        self.widgets["llama_max_tokens"] = QSpinBox()
        self.widgets["llama_max_tokens"].setRange(64, 4096)
        self.widgets["use_system_proxy"] = QCheckBox("استفاده از پروکسی سیستم برای دانلودها")
        form3.addRow(self.widgets["auto_pause_on_national"])
        form3.addRow(self.widgets["ai_use_library"])
        form3.addRow("حافظهٔ زمینهٔ مدل (توکن):", self.widgets["llama_ctx"])
        form3.addRow("لایههای GPU (1- = خودکار):", self.widgets["llama_gpu_layers"])
        form3.addRow("حداکثر توکن پاسخ:", self.widgets["llama_max_tokens"])
        form3.addRow(self.widgets["use_system_proxy"])
        tools.add_layout(form3)
        layout.addWidget(tools)

        # شبکه محلی
        lan = Card()
        lan.add(label("شبکهٔ محلی", bold=True))
        form4 = QFormLayout()
        self.widgets["device_name"] = QLineEdit()
        self.widgets["pairing_code"] = QLineEdit()
        self.widgets["pairing_code"].setMaxLength(12)
        self.widgets["lan_udp_port"] = QSpinBox()
        self.widgets["lan_udp_port"].setRange(1024, 65535)
        self.widgets["lan_tcp_port"] = QSpinBox()
        self.widgets["lan_tcp_port"].setRange(1024, 65535)
        form4.addRow("نام این دستگاه:", self.widgets["device_name"])
        form4.addRow("کد جفتسازی (عدد ۴ تا ۱۲ رقم):", self.widgets["pairing_code"])
        form4.addRow("پورت کشف UDP:", self.widgets["lan_udp_port"])
        form4.addRow("پورت ارتباط TCP:", self.widgets["lan_tcp_port"])
        lan.add_layout(form4)
        lan.add(label("کد جفتسازی باید روی همهٔ دستگاهها یکی باشد. بعد از تغییر، شبکهٔ محلی دوباره راهاندازی میشود.",
                      name="muted"))
        layout.addWidget(lan)

        buttons = row(
            button("ذخیرهٔ تنظیمات", primary=True, on_click=self.save),
            button("پشتیبانگیری از پوشهٔ data (ZIP)", on_click=self.backup),
            button("بازگردانی تنظیمات پیشفرض", on_click=self.reset),
            stretch=True,
        )
        layout.addLayout(buttons)
        layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    # ---------- بارگذاری/ذخیره ----------
    def load(self) -> None:
        cfg = self.ctx.settings()
        self.widgets["theme"].setCurrentIndex(1 if cfg["theme"] == "dark" else 0)
        for key in ("font_size", "check_interval", "hysteresis_up", "hysteresis_down",
                    "llama_ctx", "llama_gpu_layers", "llama_max_tokens",
                    "lan_udp_port", "lan_tcp_port"):
            self.widgets[key].setValue(int(cfg.get(key, 0) or 0))
        for key in ("auto_pause_on_national", "ai_use_library", "use_system_proxy"):
            self.widgets[key].setChecked(bool(cfg.get(key)))
        for key in ("device_name", "pairing_code"):
            self.widgets[key].setText(str(cfg.get(key, "")))
        self.widgets["internal_hosts"].setPlainText("\n".join(cfg["internal_hosts"]))
        self.widgets["external_urls"].setPlainText("\n".join(cfg["external_urls"]))
        self.widgets["external_tcp"].setPlainText(
            "\n".join(f"{h}:{p}" for h, p in cfg["external_tcp"]))
        self.widgets["dns_servers"].setPlainText("\n".join(cfg["dns_servers"]))

    def collect(self) -> dict[str, Any]:
        def lines(key: str) -> list[str]:
            return [x.strip() for x in self.widgets[key].toPlainText().splitlines() if x.strip()]

        tcp: list[list[Any]] = []
        for line in lines("external_tcp"):
            host, _, port = line.rpartition(":")
            if host and port.isdigit():
                tcp.append([host, int(port)])
        code = self.widgets["pairing_code"].text().strip()
        return {
            "theme": "dark" if self.widgets["theme"].currentIndex() == 1 else "light",
            "font_size": self.widgets["font_size"].value(),
            "check_interval": self.widgets["check_interval"].value(),
            "hysteresis_up": self.widgets["hysteresis_up"].value(),
            "hysteresis_down": self.widgets["hysteresis_down"].value(),
            "internal_hosts": lines("internal_hosts") or ["https://www.aparat.com/"],
            "external_urls": lines("external_urls") or ["https://www.google.com/generate_204"],
            "external_tcp": tcp or [["1.1.1.1", 443]],
            "dns_servers": lines("dns_servers") or ["1.1.1.1"],
            "auto_pause_on_national": self.widgets["auto_pause_on_national"].isChecked(),
            "ai_use_library": self.widgets["ai_use_library"].isChecked(),
            "use_system_proxy": self.widgets["use_system_proxy"].isChecked(),
            "llama_ctx": self.widgets["llama_ctx"].value(),
            "llama_gpu_layers": self.widgets["llama_gpu_layers"].value(),
            "llama_max_tokens": self.widgets["llama_max_tokens"].value(),
            "device_name": self.widgets["device_name"].text().strip(),
            "pairing_code": code,
            "lan_udp_port": self.widgets["lan_udp_port"].value(),
            "lan_tcp_port": self.widgets["lan_tcp_port"].value(),
        }

    def save(self) -> None:
        values = self.collect()
        if values["pairing_code"] and not values["pairing_code"].isdigit():
            info("کد جفتسازی باید فقط عدد باشد.", self)
            return
        try:
            self.ctx.save_settings(values)
            self.ctx.tracker.cfg = self.ctx.config
            self.ctx.queue.cfg = self.ctx.config
            self.on_theme()
            self.on_saved()
            self.bridge.toast.emit("تنظیمات ذخیره شد.", "green")
        except Exception as exc:
            show_error(self, "ذخیرهٔ تنظیمات ممکن نشد.", self.ctx.logger, exc)

    def backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیرهٔ پشتیبان", str(self.ctx.paths.root.parent / "hamrah-backup.zip"),
            "ZIP (*.zip)")
        if not path:
            return
        try:
            root = self.ctx.paths.root
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for p in root.rglob("*"):
                    if p.is_file() and "tmp" not in p.parts:
                        z.write(p, p.relative_to(root.parent))
            self.bridge.toast.emit("پشتیبان ساخته شد.", "green")
        except Exception as exc:
            show_error(self, "پشتیبانگیری ممکن نشد.", self.ctx.logger, exc)

    def reset(self) -> None:
        from ..core.config import DEFAULTS
        self.ctx.save_settings(dict(DEFAULTS))
        self.load()
        self.on_theme()
        self.on_saved()
        self.bridge.toast.emit("تنظیمات به پیشفرض برگشت.", "accent")
