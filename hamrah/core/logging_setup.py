"""لاگ فنی جداگانه + تبدیل خطا به پیام کاربرپسند."""
from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Any

from .errors import friendly

_LOGGER_NAME = "hamrah"
_configured = False


def setup_logging(log_dir: Path, *, level: int = logging.INFO) -> logging.Logger:
    """لاگ چرخشی ۲ مگابایتی (۳ نسخه) در ``data/logs/app.log``."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(threadName)-18s | %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console فقط در حالت توسعه (در نسخهٔ --windowed بستهبندی، stdout ممکن است None باشد)
    if sys.stdout is not None:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    _configured = True
    logger.info("برنامه شروع شد — لاگ فنی در %s", log_dir)
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME + ("." + name if name else ""))


def log_exception(logger: logging.Logger, context: str, exc: BaseException) -> str:
    """traceback کامل را مینویسد و پیام فارسی قابل نمایش برمیگرداند."""
    logger.error("%s: %s: %s", context, type(exc).__name__, exc)
    logger.debug("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return friendly(exc, context)


def log_message(logger: logging.Logger, msg: str, *args: Any) -> None:
    logger.info(msg, *args)
