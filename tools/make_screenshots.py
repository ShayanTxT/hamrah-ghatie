"""ساخت اسکرینشاتهای واقعی رابط فارسی برای README گیتهاب (offscreen).

اجرا (لینوکس):
    QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py

خروجی: docs/screenshots/*.png
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hamrah.context import AppContext  # noqa: E402
from hamrah.core.netcheck import classify  # noqa: E402
from hamrah.core.probes import ProbeBundle, ProbeResult  # noqa: E402
from hamrah.ui.main_window import MainWindow  # noqa: E402


def fake_bundle(ts: float, external: bool, internal: bool, dns: bool = True) -> ProbeBundle:
    results = []
    for name, target, group, ok in [
        ("سایت خارجی google.com", "google.com", "external", external),
        ("اتصال TCP 1.1.1.1", "1.1.1.1:443", "external", external),
        ("سایت داخلی aparat.com", "aparat.com", "internal", internal),
        ("سایت داخلی digikala.com", "digikala.com", "internal", internal),
        ("DNS مستقیم", "1.1.1.1", "dns", dns),
        ("مودم/روتر", "192.168.1.1", "gateway", True),
        ("کارت شبکه", "لینک", "link", True),
    ]:
        results.append(ProbeResult(name, target, "tcp", ok, 14.0,
                                   "" if ok else "timeout", group))
    return ProbeBundle(ts=ts, results=results)


def seed_history(ctx: AppContext) -> None:
    """چند قطعی مصنوعی تا نمودار و تاریخچه پر شود."""
    now = time.time()
    tracker = ctx.tracker
    tracker.cfg.update({}) if hasattr(tracker.cfg, "update") else None
    tracker.cfg = ctx.config
    sequence = [
        (now - 9000, True, True), (now - 8900, True, True),
        (now - 8800, False, True), (now - 8700, False, True),
        (now - 8600, False, False), (now - 8500, False, False),
        (now - 8400, True, True), (now - 8300, True, True),
        (now - 3600, False, True), (now - 3500, False, True),
        (now - 3400, True, True), (now - 3300, True, True),
    ]
    for ts, external, internal in sequence:
        tracker.feed(fake_bundle(ts, external, internal))
    ctx.current_state = tracker.state
    d = classify(fake_bundle(now, False, True), ctx.config)
    ctx.last_decision = d.as_dict()


def main() -> None:
    app = QApplication([])
    ctx = AppContext(tempfile.mkdtemp(prefix="hamrah_shots_"))
    seed_history(ctx)
    window = MainWindow(ctx, stage=5, demo=True, app=app)
    window.resize(1280, 800)
    window.show()
    app.processEvents()

    pages = [
        ("01-dashboard", window.dashboard),
        ("02-readiness", window.readiness),
        ("03-library", window.library),
        ("04-assistant", window.chat),
        ("05-lan", window.lan),
        ("06-settings", window.settings),
    ]
    for name, page in pages:
        window.stack.setCurrentWidget(page)
        app.processEvents()
        window.grab().save(str(OUT / f"{name}.png"))
        print("✅", name)

    ctx.config.set("theme", "dark")
    window.apply_theme()
    window.stack.setCurrentWidget(window.dashboard)
    app.processEvents()
    window.grab().save(str(OUT / "01-dashboard-dark.png"))
    print("✅ 01-dashboard-dark")

    window.probe_worker.stop()
    window.download_worker.stop()
    window.probe_worker.wait(1000)
    window.download_worker.wait(1000)
    ctx.lan.stop()
    window.close()
    print("done")


if __name__ == "__main__":
    main()
