"""نخهای پسزمینهٔ UI (هیچکدام مستقیم ویجت دستکاری نمیکنند؛ فقط Signal میفرستند)."""
from __future__ import annotations

import threading
import time
from typing import Any

from PySide6.QtCore import QThread, Signal

from ..core.netcheck import NetState
from ..core.probes import ProbeBundle, ProbeResult, run_all_probes


class ProbeWorker(QThread):
    """هر چند ثانیه وضعیت اتصال را تست میکند. ``demo=True`` بدون شبکه کار میکند."""
    checked = Signal(object)   # dict: تصمیم + خلاصهٔ تستها
    changed = Signal(object)   # dict: تغییر وضعیت (برای اعلان)
    failed = Signal(str)

    def __init__(self, ctx: Any, *, demo: bool = False, parent: Any = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.demo = demo
        self._stop = threading.Event()
        self._demo_step = 0

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval = 3.0 if self.demo else max(3.0, float(self.ctx.config.get("check_interval", 10)))
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                if self.demo:
                    bundle = self._demo_bundle()
                else:
                    bundle = run_all_probes(self.ctx.config)
                decision, change = self.ctx.tracker.feed(bundle)
                self.ctx.current_state = self.ctx.tracker.state
                self.ctx.last_decision = decision.as_dict()
                payload = decision.as_dict()
                payload["bundle"] = bundle.summary()
                payload["datetime"] = time.time()
                self.checked.emit(payload)
                if change:
                    self.changed.emit({
                        "title": change.title, "message": change.message,
                        "state": change.new.value, "returned": change.returned,
                        "label": change.label,
                    })
            except Exception as exc:
                self.failed.emit(f"{type(exc).__name__}: {exc}")
            # فاصلهٔ واقعی بین دو شروع تست = interval (زمان تست کسر میشود)
            self._stop.wait(max(0.5, interval - (time.monotonic() - started)))

    def _demo_bundle(self) -> ProbeBundle:
        """چهار فاز: آزاد -> ملی -> قطع کامل -> برگشت. برای تست اعلانها."""
        self._demo_step += 1
        phase = (self._demo_step // 3) % 4
        results: list[ProbeResult] = []
        external_ok = phase in (0, 3)
        internal_ok = phase in (0, 3, 1)
        dns_ok = phase in (0, 3, 1)
        gw_ok = True
        for name, target, group, ok in [
            ("سایت خارجی google.com", "google.com", "external", external_ok),
            ("اتصال TCP 1.1.1.1", "1.1.1.1:443", "external", external_ok),
            ("سایت داخلی aparat.com", "aparat.com", "internal", internal_ok),
            ("سایت داخلی digikala.com", "digikala.com", "internal", internal_ok),
            ("DNS", "1.1.1.1", "dns", dns_ok),
            ("مودم/روتر", "192.168.1.1", "gateway", gw_ok),
            ("کارت شبکه", "لینک", "link", True),
        ]:
            results.append(ProbeResult(name, target, "demo", ok, 12.0,
                                       "" if ok else "شبیهسازی قطعی", group))
        return ProbeBundle(ts=time.time(), results=results)


class DownloadWorker(QThread):
    event = Signal(str, object)
    progress = Signal(int, int, int)   # item_id, done, total

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            self.ctx.queue.run_loop(
                lambda: self.ctx.current_state.value,
                stop_event=self._stop,
                on_event=lambda kind, payload: self.event.emit(kind, payload),
                progress=lambda i, d, t: self.progress.emit(i, d, t),
            )
        except Exception as exc:
            self.event.emit("error", {"error": str(exc)})


class IndexWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(object)

    def __init__(self, ctx: Any, task: str, path: str = "", parent: Any = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.task = task
        self.path = path
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            if self.task == "scan":
                result = self.ctx.library.scan_folder(
                    progress=lambda i, t, name: self.progress.emit(i, t, name),
                    should_continue=lambda: not self._stop.is_set(),
                )
                # صفحات ذخیرهشده را هم ایندکس میکنیم
                for index_html in self.ctx.paths.pages.rglob("index.html"):
                    try:
                        self.ctx.library.index_file(index_html, source="page:" + str(index_html.parent))
                    except Exception:
                        continue
                result["stats"] = self.ctx.library.stats()
                self.done.emit(result)
            elif self.task == "zim":
                from pathlib import Path
                result = self.ctx.library.index_zim(
                    Path(self.path),
                    progress=lambda i, t, name: self.progress.emit(i, t, name),
                    should_continue=lambda: not self._stop.is_set(),
                )
                result["stats"] = self.ctx.library.stats()
                self.done.emit(result)
        except Exception as exc:
            self.done.emit({"error": f"{type(exc).__name__}: {exc}"})


class ChatWorker(QThread):
    token = Signal(str)
    done = Signal(str, str)     # پاسخ کامل، منابع
    failed = Signal(str)

    def __init__(self, ctx: Any, messages: list[dict[str, str]], context: str,
                 sources: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.messages = messages
        self.context = context
        self.sources = sources
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            answer = self.ctx.llama.stream_chat(
                self.messages,
                on_token=lambda t: self.token.emit(t),
                context=self.context,
                stop_event=self._stop,
            )
            self.done.emit(answer, self.sources)
        except Exception as exc:
            self.failed.emit(str(exc))
