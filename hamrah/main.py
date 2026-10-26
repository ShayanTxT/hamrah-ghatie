"""نقطهٔ ورود برنامه (پرتابل ویندوزی).

گزینهها:
    --stage N      فقط N مرحلهٔ اول نمایش داده شود (۱..۵) — برای تست مرحلهبهمرحله
    --demo         شبیهسازی چرخهٔ قطعی بدون هیچ درخواست شبکهای
    --data-dir P   استفاده از پوشهٔ دادهای دیگر (پیشفرض data کنار exe)
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--stage", type=int, default=5)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--offscreen", action="store_true",
                        help="فقط برای تست توسعهدهنده (نمایش بدون پنجره)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # در ویندوز، جلوگیری از مقیاسگذاری تار فونتهای فارسی
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)
    app.setApplicationName("همراه قطعی")
    app.setLayoutDirection(Qt.RightToLeft)

    try:
        from .context import AppContext
        from .ui.main_window import MainWindow
        ctx = AppContext(args.data_dir or None)
        window = MainWindow(ctx, stage=args.stage, demo=args.demo, app=app)
        window.show()
    except Exception as exc:  # خطای راهاندازی: فارسی به کاربر، کامل در لاگ
        try:
            from .core.logging_setup import setup_logging, log_exception
            from .core.paths import Paths
            paths = Paths(args.data_dir or None)
            logger = setup_logging(paths.logs)
            logger.error("خطای مرگبار هنگام راهاندازی:\n%s", traceback.format_exc())
            message = log_exception(logger, "برنامه اجرا نشد.", exc)
        except Exception:
            message = "برنامه اجرا نشد. پوشهٔ data/logs را بررسی کنید."
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("همراه قطعی — خطا")
        box.setText(message)
        box.setLayoutDirection(Qt.RightToLeft)
        box.exec()
        return 1

    def excepthook(exc_type: Any, exc: BaseException, tb: Any) -> None:
        try:
            from .core.logging_setup import get_logger
            get_logger().error("خطای پیشبینینشده:\n%s",
                               "".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass

    sys.excepthook = excepthook
    # فقط برای تست خودکار: بعد از N میلیثانیه خارج شو (هیچ تأثیری در استفادهٔ عادی ندارد)
    autoquit = os.environ.get("HAMRAH_AUTOQUIT_MS")
    if autoquit:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(int(autoquit), app.quit)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
