"""زمینهای که همهٔ بخشها از آن مشترک استفاده میکنند (بدون Qt)."""
from __future__ import annotations

import os
from typing import Any

from .core.checklist import Checklist
from .core.config import Config
from .core.db import Database
from .core.downloader import DownloadQueue
from .core.http import HttpClient
from .core.library import Library
from .core.llama import LlamaEngine
from .core.logging_setup import setup_logging
from .core.lan.crypto import code_to_psk
from .core.lan.node import LanNode
from .core.netcheck import NetState, StateTracker
from .core.netpolicy import NetworkGuard
from .core.pagesaver import PageSaver
from .core.paths import Paths


class AppContext:
    """ساخت تنها نمونهٔ هر سرویس و اتصال آنها به هم."""

    def __init__(self, data_dir: str | os.PathLike[str] | None = None) -> None:
        self.paths = Paths(data_dir)
        self.logger = setup_logging(self.paths.logs)
        self.config = Config(self.paths.config_path)
        self.db = Database(self.paths.db_path)
        self.guard = NetworkGuard()
        self.http = HttpClient(
            self.guard,
            user_agent=str(self.config.get("user_agent")),
            use_system_proxy=bool(self.config.get("use_system_proxy")),
        )
        self.current_state = NetState.UNKNOWN
        self.last_decision: dict[str, Any] | None = None

        self.tracker = StateTracker(self.db, self.config)
        self.page_saver = PageSaver(self.http, self.config, self.paths)
        self.queue = DownloadQueue(self.db, self.config, self.paths,
                                   self.http, self.page_saver)
        self.checklist = Checklist(self.db)
        self.library = Library(self.db, self.config, self.paths)
        self.llama = LlamaEngine(self.db, self.config, self.paths, guard=self.guard)
        self.lan = LanNode(self.config, self.paths, self.db)
        self.logger.info("زمینهٔ برنامه آماده شد: %s", self.paths.root)

    def settings(self) -> dict[str, Any]:
        return self.config.as_dict()

    def save_settings(self, values: dict[str, Any]) -> None:
        self.config.update(values)
        self.config.save()
        # نگهبان و کلاینت HTTP باید بلافاصله پروکسی جدید را ببینند
        self.http = HttpClient(
            self.guard,
            user_agent=str(self.config.get("user_agent")),
            use_system_proxy=bool(self.config.get("use_system_proxy")),
        )
        self.page_saver.http = self.http
        self.queue.http = self.http
        self.lan.code = str(self.config.get("pairing_code", ""))
        self.lan.tcp_port = int(self.config.get("lan_tcp_port", 54546))
        self.lan.discovery.code = self.lan.code
        self.lan.discovery.udp_port = int(self.config.get("lan_udp_port", 54545))
        self.lan.discovery.tcp_port = self.lan.tcp_port
        try:
            self.lan.discovery.psk = code_to_psk(self.lan.code) if self.lan.code else b""
        except Exception:
            self.lan.discovery.psk = b""
        self.logger.info("تنظیمات ذخیره شد")

    def shutdown(self) -> None:
        try:
            self.lan.stop()
        except Exception:
            pass
        try:
            self.llama.stop()
        except Exception:
            pass
        try:
            self.db.vacuum()
        except Exception:
            pass
