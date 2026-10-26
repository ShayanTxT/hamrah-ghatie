"""صفحهٔ ۱ — داشبورد وضعیت اتصال، جزئیات تستها، نمودار و تاریخچهٔ قطعیها."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHeaderView, QLabel, QListWidget,
    QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.jalali import format_datetime, format_duration
from ..core.netcheck import STATE_META, NetState
from .common import Card, badge, button, label, row, title_block


class TimelineChart(QWidget):
    """نمودار سادهٔ ۲۴ ساعت گذشته — فقط QPainter، بدون کتابخانهٔ خارجی."""

    COLORS = {
        0: ("#dc3545", "#ff6b6b"),
        1: ("#e6a100", "#ffc857"),
        2: ("#0f9d58", "#3ddc84"),
    }

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.data: list[dict[str, Any]] = []
        self.dark = False
        self.setMinimumHeight(120)
        self.refresh()

    def refresh(self) -> None:
        self.data = self.ctx.tracker.timeline(24, 72)
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - امضای Qt
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if not self.data:
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "هنوز اطلاعاتی ثبت نشده است")
            painter.end()
            return
        margin = 18
        baseline = h - margin
        usable_h = h - 2 * margin
        bw = max(1.0, (w - 2 * margin) / len(self.data))
        painter.setPen(QPen(QColor(120, 130, 150, 90), 1))
        for frac in (0, 0.5, 1.0):
            y = baseline - frac * usable_h
            painter.drawLine(margin, int(y), w - margin, int(y))
        for i, bucket in enumerate(self.data):
            avg = bucket["avg"]
            if avg is None:
                continue
            idx = 1 if self.dark else 0
            color = QColor(self.COLORS[min(2, max(0, round(avg)))][idx])
            bar_h = max(3, (avg / 2.0) * usable_h)
            painter.fillRect(
                QRectF(margin + i * bw, baseline - bar_h, max(1.0, bw - 1), bar_h), color
            )
        painter.setPen(QColor(110, 120, 140))
        painter.drawText(QRectF(0, 0, 70, 16), Qt.AlignLeft, "۲۴ ساعت قبل")
        painter.drawText(QRectF(w - 70, 0, 70, 16), Qt.AlignRight, "اکنون")
        painter.end()


class DashboardPage(QWidget):
    def __init__(self, ctx: Any, bridge: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.bridge = bridge
        self.chart = TimelineChart(ctx)
        self._build()
        self.refresh_history()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)
        outer.addWidget(title_block("داشبورد وضعیت اتصال",
                                    "نتایج تستهای جداگانه، نمودار ۲۴ ساعت و تاریخچهٔ قطعیها"))

        self.state_card = Card()
        self.state_label = label("⚪ در حال بررسی", name="title", wrap=False)
        self.state_label.setStyleSheet("font-size: 20pt; font-weight: bold;")
        self.state_badge = badge("وضعیت نامشخص")
        self.hint_label = label("اولین تست اتصال در حال انجام است...", name="subtitle")
        self.state_card.add(row(self.state_label, self.state_badge, stretch=True))
        self.state_card.add(self.hint_label)
        self.reasons_label = label("", name="muted")
        self.state_card.add(self.reasons_label)
        outer.addWidget(self.state_card)

        splitter = QSplitter(Qt.Horizontal)
        # تستها
        tests_card = Card()
        tests_card.add(label("تستهای اتصال", bold=True))
        self.tests = QTableWidget(0, 4)
        self.tests.setHorizontalHeaderLabels(["تست", "مقصد", "نتیجه", "زمان (ms)"])
        self.tests.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tests.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tests.setAlternatingRowColors(True)
        tests_card.add(self.tests)
        splitter.addWidget(tests_card)

        # نمودار + تاریخچه
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        chart_card = Card()
        chart_card.add(label("نمودار ۲۴ ساعت گذشته", bold=True))
        chart_card.add(self.chart)
        hint = label("سبز: آزاد  •  زرد: فقط ملی  •  قرمز: قطع کامل", name="muted")
        chart_card.add(hint)
        right_layout.addWidget(chart_card)

        history_card = Card()
        header = row(label("تاریخچهٔ قطعیها", bold=True),
                     button("بروزرسانی", on_click=self.refresh_history), stretch=True)
        history_card.add_layout(header)
        self.history = QListWidget()
        self.history.setAlternatingRowColors(True)
        history_card.add(self.history)
        right_layout.addWidget(history_card)
        splitter.addWidget(right)
        splitter.setSizes([520, 520])
        outer.addWidget(splitter, 1)

    # ---------- بهروزرسانی ----------
    def update_state(self, payload: dict[str, Any]) -> None:
        state = NetState(payload.get("state", "unknown"))
        meta = STATE_META[state]
        tone = {"free": "green", "national": "yellow", "down": "red"}.get(state.value, "accent")
        self.state_label.setText(f"{meta['emoji']} {meta['label']}")
        self.state_badge.setText(badge_text(payload))
        colors = {
            "free": ("#e4f6ec", "#0f9d58"), "national": ("#fff4d9", "#a57400"),
            "down": ("#fde7e9", "#c02c3a"),
        }
        bg, fg = colors.get(state.value, ("#e5edff", "#2f6fed"))
        self.state_badge.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:10px; padding:4px 12px; font-weight:bold;"
        )
        self.hint_label.setText(meta["hint"])
        self.reasons_label.setText(" • ".join(payload.get("reasons", [])))
        results = payload.get("bundle", {}).get("results", [])
        self.tests.setRowCount(len(results))
        for i, r in enumerate(results):
            status = "✅ موفق" if r["ok"] else "❌ ناموفق"
            values = [r["name"], r["target"], status, str(r["latency_ms"])]
            for j, val in enumerate(values):
                item = QTableWidgetItem(val)
                if j == 2:
                    item.setForeground(QColor("#0f9d58") if r["ok"] else QColor("#dc3545"))
                self.tests.setItem(i, j, item)
        self.chart.refresh()

    def refresh_history(self) -> None:
        self.history.clear()
        outages = self.ctx.tracker.outages(60)
        if not outages:
            self.history.addItem("هنوز قطعیی ثبت نشده است.")
            return
        for o in outages:
            state = NetState(o["worst_state"]) if o["worst_state"] in NetState._value2member_map_ else NetState.DOWN
            start = format_datetime(datetime.fromtimestamp(o["started_at"]))
            end = (format_datetime(datetime.fromtimestamp(o["ended_at"]))
                   if o["ended_at"] else "ادامه دارد")
            dur = format_duration(o["duration"])
            self.history.addItem(
                f"{STATE_META[state]['emoji']} {STATE_META[state]['label']}  |  "
                f"از {start} تا {end}  |  مدت: {dur}"
            )


def badge_text(payload: dict[str, Any]) -> str:
    p = payload.get("bundle", {})
    return (f"خارجی {p.get('external', '0/0')}  •  داخلی {p.get('internal', '0/0')}  •  "
            f"DNS {p.get('dns', '0/0')}  •  مودم {p.get('gateway', '0/0')}")
