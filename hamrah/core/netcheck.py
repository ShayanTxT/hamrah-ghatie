"""مرحلهٔ ۱ — تشخیص وضعیت اتصال، هیسترزیس، تاریخچه و اعلان تغییر.

منطق خالص است (هیچ Qt/networkای اینجا import نشده) تا بتوان آن را با
ProbeRunner قلابی روی لینوکس تست کرد.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .db import Database
from .probes import ProbeBundle


class NetState(str, Enum):
    FREE = "free"          # 🟢 اینترنت آزاد
    NATIONAL = "national"  # 🟡 فقط اینترنت ملی
    DOWN = "down"          # 🔴 قطع کامل
    UNKNOWN = "unknown"    # قبل از اولین تست


STATE_META: dict[NetState, dict[str, str]] = {
    NetState.FREE: {"emoji": "🟢", "label": "اینترنت آزاد",
                    "hint": "دسترسی به اینترنت جهانی برقرار است."},
    NetState.NATIONAL: {"emoji": "🟡", "label": "فقط اینترنت ملی",
                        "hint": "فقط سایتهای داخلی در دسترساند. دانلودها متوقف شدهاند."},
    NetState.DOWN: {"emoji": "🔴", "label": "قطع کامل",
                    "hint": "هیچ دسترسی به اینترنت نیست. کتابخانه و شبکهٔ محلی همچنان کار میکنند."},
    NetState.UNKNOWN: {"emoji": "⚪", "label": "در حال بررسی",
                       "hint": "اولین تست اتصال در حال انجام است..."},
}

RANK: dict[NetState, int] = {
    NetState.DOWN: 0, NetState.NATIONAL: 1, NetState.FREE: 2, NetState.UNKNOWN: -1,
}

# بدترین حالت برای خلاصه کردن یک دورهٔ قطعی
WORST = {NetState.DOWN: 0, NetState.NATIONAL: 1, NetState.FREE: 2}


@dataclass
class Decision:
    state: NetState
    reasons: list[str] = field(default_factory=list)
    external_ok: int = 0
    internal_ok: int = 0
    dns_ok: int = 0
    gateway_ok: int = 0
    link_ok: bool = False
    confidence: float = 0.0

    @property
    def label(self) -> str:
        return STATE_META[self.state]["label"]

    @property
    def emoji(self) -> str:
        return STATE_META[self.state]["emoji"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value, "label": self.label, "emoji": self.emoji,
            "reasons": self.reasons, "external_ok": self.external_ok,
            "internal_ok": self.internal_ok, "dns_ok": self.dns_ok,
            "gateway_ok": self.gateway_ok, "link_ok": self.link_ok,
            "confidence": round(self.confidence, 2),
        }


def classify(bundle: ProbeBundle, cfg: dict[str, Any] | None = None, *, lan_peers: int = 0) -> Decision:
    """تبدیل نتایج خام تستها به یکی از سه وضعیت.

    ترتیب اهمیت:
    ۱. اگر حتی یک مسیر خارجی جواب داد -> 🟢 آزاد.
    ۲. اگر سایتها/پورتهای داخلی جواب دادند -> 🟡 فقط ملی.
    ۳. اگر DNS داخلی نام سایتهای ایرانی را حل کرد و مودم وصل است -> 🟡 (احتمال ملی).
    ۴. در غیر این صورت -> 🔴 قطع کامل (ولی LAN ممکن است همچنان وصل باشد).
    """
    cfg = cfg or {}
    ext = bundle.external_ok
    internal = bundle.internal_ok
    dns = bundle.dns_ok
    gw = bundle.gateway_ok
    link = bundle.link_ok
    reasons: list[str] = []

    if ext:
        reasons.append(f"{ext} مسیر خارجی پاسخ داد (نمونه: {_first_ok(bundle, 'external')}).")
        state = NetState.FREE
    elif internal:
        reasons.append(f"{internal} سایت/پورت داخلی در دسترس است (نمونه: {_first_ok(bundle, 'internal')}).")
        if not dns:
            reasons.append("حل نام خارجی کار نمیکند، ولی سایتهای داخلی باز میشوند.")
        state = NetState.NATIONAL
    elif dns and gw:
        # DNS داخلی ممکن است فقط نامهای ایرانی را حل کند؛ با احتیاط «ملی» اعلام میکنیم
        reasons.append("سایتهای داخلی پاسخ ندادند ولی DNS و مودم وصلاند؛ احتمالاً اینترنت ملی با اختلال.")
        state = NetState.NATIONAL
    else:
        reasons.append("هیچکدام از مقصدهای داخلی و خارجی پاسخ ندادند.")
        if gw or link:
            reasons.append("مودم/کارت شبکه وصل است؛ یعنی شبکهٔ محلی همچنان قابل استفاده است.")
        else:
            reasons.append("حتی ارتباط با مودم/روتر هم برقرار نیست.")
        state = NetState.DOWN

    if lan_peers and state is NetState.DOWN:
        reasons.append(f"{lan_peers} کامپیوتر دیگر در شبکهٔ محلی پیدا شدند؛ اشتراک فایل همچنان کار میکند.")

    total = len(bundle.results) or 1
    succeeded = sum(1 for r in bundle.results if r.ok)
    d = Decision(state, reasons, ext, internal, dns, gw, link, succeeded / total)
    return d


def _first_ok(bundle: ProbeBundle, group: str) -> str:
    for r in bundle.results:
        if r.group == group and r.ok:
            return r.target
    return "—"


@dataclass
class StateChange:
    ts: float
    old: NetState
    new: NetState
    decision: Decision
    returned: bool = False       # اولین لحظهٔ برگشتن اینترنت جهانی
    message: str = ""

    @property
    def title(self) -> str:
        if self.returned:
            return "🟢 اینترنت جهانی برگشت!"
        return f"{STATE_META[self.new]['emoji']} تغییر وضعیت: {self.label}"

    @property
    def label(self) -> str:
        return STATE_META[self.new]["label"]


class StateTracker:
    """نگهداری وضعیت پایدار با هیسترزیس + ثبت تاریخچه در SQLite.

    هیسترزیس باعث میشود یک خطای لحظهای (مثلاً timeout یک تست) اعلان دروغین
    نفرستد. تغییر به وضعیت بهتر و بدتر هرکدام آستانهٔ جداگانهای دارند.
    """

    def __init__(
        self,
        db: Database,
        cfg: dict[str, Any] | None = None,
        *,
        on_change: Callable[[StateChange], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.cfg = cfg or {}
        self.on_change = on_change
        self.clock = clock
        self.state = NetState.UNKNOWN
        self.last_decision: Decision | None = None
        self._pending: NetState | None = None
        self._pending_count = 0
        self._open_outage_id: int | None = None
        self._restore_open_outage()

    # ---------- تشخیص ----------
    def _threshold(self, candidate: NetState) -> int:
        if self.state is NetState.UNKNOWN:
            return 1
        if RANK[candidate] > RANK[self.state]:
            return max(1, int(self.cfg.get("hysteresis_up", 2)))
        return max(1, int(self.cfg.get("hysteresis_down", 2)))

    def feed(self, bundle: ProbeBundle, *, lan_peers: int = 0) -> tuple[Decision, StateChange | None]:
        """یک نمونهٔ جدید را وارد میکند. برمیگرداند: (تصمیم خام، تغییر وضعیت یا None)."""
        decision = classify(bundle, self.cfg, lan_peers=lan_peers)
        self.last_decision = decision
        self._record_sample(bundle, decision)

        if decision.state is self._pending:
            self._pending_count += 1
        else:
            self._pending = decision.state
            self._pending_count = 1

        change: StateChange | None = None
        if self.state is NetState.UNKNOWN:
            change = self._apply(decision, bundle.ts)
        elif decision.state is not self.state and self._pending_count >= self._threshold(decision.state):
            change = self._apply(decision, bundle.ts)
        else:
            # بهروزرسانی بدترین حالت دورهٔ قطعی جاری
            if self._open_outage_id and decision.state is not NetState.FREE:
                self._note_worst(decision.state)
        return decision, change

    def _apply(self, decision: Decision, ts: float) -> StateChange:
        old = self.state
        self.state = decision.state
        self._pending = decision.state
        self._pending_count = 0
        returned = (old in (NetState.NATIONAL, NetState.DOWN)
                    and decision.state is NetState.FREE)
        message = (
            "الان کارهای عقبافتادهات رو انجام بده: صف دانلود ادامه پیدا میکند، "
            "آپدیتها و پیامها را چک کن."
            if returned else STATE_META[decision.state]["hint"]
        )
        change = StateChange(ts=ts, old=old, new=decision.state,
                             decision=decision, returned=returned, message=message)
        self.db.execute(
            "INSERT INTO state_events(ts, state, detail) VALUES(?, ?, ?)",
            (ts, decision.state.value, " | ".join(decision.reasons)),
        )
        if decision.state is NetState.FREE:
            self._close_outage(ts)
        else:
            self._open_or_update_outage(decision.state, ts)
        if self.on_change:
            try:
                self.on_change(change)
            except Exception:
                # اعلان نباید چرخهٔ تست را متوقف کند؛ جزئیات در لاگ UI نوشته میشود
                pass
        return change

    # ---------- تاریخچه ----------
    def _record_sample(self, bundle: ProbeBundle, decision: Decision) -> None:
        self.db.execute(
            "INSERT INTO probe_samples(ts, state, external_ok, internal_ok, dns_ok, gateway_ok, detail) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (bundle.ts, decision.state.value, decision.external_ok, decision.internal_ok,
             decision.dns_ok, decision.gateway_ok, " | ".join(decision.reasons[:2])),
        )
        # نگهداری حداکثر ۳۰ روز نمونه (برنامه ممکن است ماهها روشن باشد)
        cutoff = bundle.ts - 30 * 86400
        self.db.execute("DELETE FROM probe_samples WHERE ts < ?", (cutoff,))

    def _restore_open_outage(self) -> None:
        row = self.db.query("SELECT id, state FROM outages WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1")
        if row:
            self._open_outage_id = int(row[0]["id"])
            self.state = NetState(row[0]["state"]) if row[0]["state"] in NetState._value2member_map_ else NetState.DOWN
        else:
            last = self.db.query("SELECT state FROM state_events ORDER BY id DESC LIMIT 1")
            if last and last[0]["state"] in NetState._value2member_map_:
                self.state = NetState(last[0]["state"])

    def _open_or_update_outage(self, state: NetState, ts: float) -> None:
        if self._open_outage_id:
            self._note_worst(state)
            return
        self._open_outage_id = self.db.execute(
            "INSERT INTO outages(state, worst_state, started_at) VALUES(?, ?, ?)",
            (state.value, state.value, ts),
        )

    def _note_worst(self, state: NetState) -> None:
        if not self._open_outage_id:
            return
        rows = self.db.query("SELECT worst_state FROM outages WHERE id = ?", (self._open_outage_id,))
        if rows and WORST.get(state, 1) < WORST.get(rows[0]["worst_state"], 1):
            self.db.execute("UPDATE outages SET worst_state = ? WHERE id = ?",
                            (state.value, self._open_outage_id))

    def _close_outage(self, ts: float) -> None:
        if self._open_outage_id:
            self.db.execute("UPDATE outages SET ended_at = ? WHERE id = ?", (ts, self._open_outage_id))
            self._open_outage_id = None

    def outages(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT id, state, worst_state, started_at, ended_at FROM outages ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        now = self.clock()
        return [{
            "id": r["id"], "state": r["state"], "worst_state": r["worst_state"],
            "started_at": r["started_at"], "ended_at": r["ended_at"],
            "duration": (r["ended_at"] or now) - r["started_at"],
        } for r in rows]

    def events(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT ts, state, detail FROM state_events ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def timeline(self, hours: float = 24.0, buckets: int = 72) -> list[dict[str, Any]]:
        """دادهٔ آماده برای نمودار ساده: میانگین وضعیت در هر بازهٔ زمانی."""
        now = self.clock()
        start = now - hours * 3600
        width = (now - start) / max(1, buckets)
        rows = self.db.query(
            "SELECT ts, state FROM probe_samples WHERE ts >= ? ORDER BY ts", (start,)
        )
        result: list[dict[str, Any]] = []
        idx = 0
        for b in range(buckets):
            lo, hi = start + b * width, start + (b + 1) * width
            vals: list[int] = []
            while idx < len(rows) and rows[idx]["ts"] < hi:
                if rows[idx]["ts"] >= lo:
                    state = rows[idx]["state"]
                    vals.append(RANK.get(NetState(state) if state in NetState._value2member_map_ else NetState.DOWN, 0))
                idx += 1
            result.append({
                "ts": lo, "avg": (sum(vals) / len(vals)) if vals else None,
                "count": len(vals),
            })
        return result
