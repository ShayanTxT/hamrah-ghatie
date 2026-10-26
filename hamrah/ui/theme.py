"""حالت روشن/تیره + بارگذاری فونت فارسی باندلشده (وزیرمتن).

هیچ فونت یا استایلی از CDN/اینترنت بارگذاری نمیشود؛ فایلهای TTF کنار
برنامه هستند و با QFontDatabase.addApplicationFont ثبت میشوند.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#f4f6fa", "surface": "#ffffff", "surface2": "#eef1f7",
    "text": "#1e2430", "muted": "#6b7280", "border": "#dfe3ec",
    "accent": "#2f6fed", "accent_text": "#ffffff", "accent_soft": "#e5edff",
    "green": "#0f9d58", "yellow": "#e6a100", "red": "#dc3545",
    "green_soft": "#e4f6ec", "yellow_soft": "#fff4d9", "red_soft": "#fde7e9",
}
DARK = {
    "bg": "#151a22", "surface": "#1e2530", "surface2": "#273040",
    "text": "#e9edf5", "muted": "#9aa5b8", "border": "#334054",
    "accent": "#5b8cff", "accent_text": "#ffffff", "accent_soft": "#26375c",
    "green": "#3ddc84", "yellow": "#ffc857", "red": "#ff6b6b",
    "green_soft": "#173a2a", "yellow_soft": "#3b3218", "red_soft": "#3d2226",
}

QSS_TEMPLATE = """
* {{ font-family: "{font}"; }}
QWidget {{
    background: {bg};
    color: {text};
    font-size: {size}pt;
}}
QMainWindow, QDialog {{ background: {bg}; }}
QFrame#card {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}
QFrame#topbar {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
QLabel#title {{ font-size: {title}pt; font-weight: bold; color: {text}; }}
QLabel#subtitle, QLabel#muted {{ color: {muted}; font-size: {small}pt; }}
QLabel#badge {{
    background: {accent_soft}; color: {accent};
    border-radius: 10px; padding: 4px 12px; font-weight: bold;
}}
QLabel#badgeGreen {{ background: {green_soft}; color: {green}; border-radius: 10px; padding: 4px 12px; font-weight: bold; }}
QLabel#badgeYellow {{ background: {yellow_soft}; color: {yellow}; border-radius: 10px; padding: 4px 12px; font-weight: bold; }}
QLabel#badgeRed {{ background: {red_soft}; color: {red}; border-radius: 10px; padding: 4px 12px; font-weight: bold; }}
QPushButton {{
    background: {surface2}; color: {text}; border: 1px solid {border};
    border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ background: {accent_soft}; border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border: none; font-weight: bold; }}
QPushButton#danger {{ background: {red_soft}; color: {red}; border: 1px solid {red}; }}
QPushButton#nav {{
    text-align: right; padding: 10px 14px; border: none; border-radius: 9px;
    background: transparent;
}}
QPushButton#nav:hover {{ background: {accent_soft}; }}
QPushButton#nav:checked {{ background: {accent}; color: {accent_text}; font-weight: bold; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget {{
    background: {surface}; color: {text};
    border: 1px solid {border}; border-radius: 8px; padding: 6px;
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QTextEdit#chat {{ font-size: {size}pt; line-height: 160%; }}
QProgressBar {{
    border: 1px solid {border}; border-radius: 7px; text-align: center;
    background: {surface2}; color: {text}; min-height: 18px;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 6px; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QTableWidget {{ gridline-color: {border}; }}
QHeaderView::section {{ background: {surface2}; color: {text}; border: none; padding: 6px; }}
QScrollBar:vertical {{ background: {bg}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 24px; }}
QScrollBar:horizontal {{ background: {bg}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
QSplitter::handle {{ background: {border}; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 8px; }}
QTabBar::tab {{ background: {surface2}; color: {text}; padding: 7px 14px; border-radius: 6px; }}
QTabBar::tab:selected {{ background: {accent}; color: {accent_text}; }}
"""


def load_fonts(fonts_dir: Path) -> str:
    """ثبت فونت وزیرمتن و برگرداندن نام خانوادهٔ قابل استفاده در QSS."""
    family = "Vazirmatn"
    for filename in ("Vazirmatn-Variable.ttf", "Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
        path = fonts_dir / filename
        if path.is_file():
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    family = str(families[0])
                    break
    return family


def stylesheet(theme: str, family: str, font_size: int = 10) -> str:
    c = DARK if theme == "dark" else LIGHT
    return QSS_TEMPLATE.format(
        font=family, size=font_size, title=font_size + 5, small=max(8, font_size - 1), **c
    )


def apply_theme(app: QApplication, theme: str, family: str, font_size: int = 10) -> None:
    app.setStyleSheet(stylesheet(theme, family, font_size))
    font = QFont(family, font_size)
    app.setFont(font)
