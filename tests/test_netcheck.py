"""تست تشخیص وضعیت اتصال، هیسترزیس، تاریخچه و اعلان برگشت اینترنت."""
from __future__ import annotations

import time

from hamrah.core.netcheck import NetState, StateTracker, classify
from hamrah.core.probes import ProbeBundle, ProbeResult


def bundle(*, external: int = 0, internal: int = 0, dns: int = 0,
           gateway: int = 0, link: bool = True, ts: float | None = None) -> ProbeBundle:
    results: list[ProbeResult] = []
    for group, count in (("external", external), ("internal", internal),
                         ("dns", dns), ("gateway", gateway)):
        for i in range(count):
            results.append(ProbeResult(f"{group}{i}", f"t{i}", "tcp", True, 5, group=group))
        # اضافه کردن چند تست ناموفق برای واقعیتر شدن confidence
        for i in range(2):
            results.append(ProbeResult(f"{group}-fail{i}", "x", "tcp", False, 5,
                                       "timeout", group))
    results.append(ProbeResult("کارت شبکه", "link", "link", link, 1, group="link"))
    return ProbeBundle(ts=ts or time.time(), results=results)


def test_classify_free():
    d = classify(bundle(external=2, dns=1, gateway=1))
    assert d.state is NetState.FREE
    assert d.external_ok == 2


def test_classify_national_when_only_internal_works():
    d = classify(bundle(internal=2, gateway=1))
    assert d.state is NetState.NATIONAL
    assert d.external_ok == 0


def test_classify_down_but_lan_alive():
    d = classify(bundle(gateway=0, link=True), lan_peers=3)
    assert d.state is NetState.DOWN
    assert any("محلی" in r for r in d.reasons)


def test_classify_total_blackout():
    d = classify(bundle(link=False))
    assert d.state is NetState.DOWN
    assert any("مودم" in r for r in d.reasons)


def test_external_wins_over_internal():
    d = classify(bundle(external=1, internal=2, dns=1))
    assert d.state is NetState.FREE


def test_first_sample_applies_immediately(db, settings):
    changes = []
    tracker = StateTracker(db, settings, on_change=changes.append)
    decision, change = tracker.feed(bundle(external=2, ts=1000))
    assert decision.state is NetState.FREE
    assert change is not None and change.old is NetState.UNKNOWN
    assert tracker.state is NetState.FREE
    assert len(changes) == 1


def test_hysteresis_prevents_flapping(db, settings):
    settings["hysteresis_down"] = 3
    settings["hysteresis_up"] = 2
    changes = []
    tracker = StateTracker(db, settings, on_change=changes.append)
    tracker.feed(bundle(external=2, ts=1000))
    assert len(changes) == 1
    # یک نمونهٔ خراب نباید وضعیت را عوض کند
    _, change = tracker.feed(bundle(internal=2, ts=1001))
    assert change is None and tracker.state is NetState.FREE
    _, change = tracker.feed(bundle(internal=2, ts=1002))
    assert change is None
    _, change = tracker.feed(bundle(internal=2, ts=1003))
    assert change is not None and tracker.state is NetState.NATIONAL


def test_outage_history_and_return_notification(db, settings):
    settings["hysteresis_down"] = 1
    settings["hysteresis_up"] = 1
    changes = []
    tracker = StateTracker(db, settings, on_change=changes.append)
    tracker.feed(bundle(external=2, ts=1000))       # آزاد
    tracker.feed(bundle(internal=2, ts=1010))       # ملی -> شروع قطعی
    tracker.feed(bundle(link=False, ts=1020))       # قطع کامل
    tracker.feed(bundle(external=2, dns=1, ts=1030))  # برگشت

    outages = tracker.outages()
    assert len(outages) == 1
    assert outages[0]["worst_state"] == NetState.DOWN.value
    assert outages[0]["ended_at"] is not None
    assert abs(outages[0]["duration"] - 20) < 0.01

    returns = [c for c in changes if c.returned]
    assert len(returns) == 1
    assert "برگشت" in returns[0].title
    assert "عقب" in returns[0].message


def test_outage_restored_after_restart(db, settings):
    settings["hysteresis_down"] = 1
    a = StateTracker(db, settings)
    a.feed(bundle(external=2, ts=1000))
    a.feed(bundle(internal=2, ts=1010))
    b = StateTracker(db, settings)
    assert b.state is NetState.NATIONAL
    assert b._open_outage_id is not None


def test_timeline_shape(db, settings):
    tracker = StateTracker(db, settings)
    tracker.feed(bundle(external=2, ts=time.time() - 3600))
    data = tracker.timeline(24, 24)
    assert len(data) == 24
    assert sum(1 for x in data if x["count"]) >= 1
