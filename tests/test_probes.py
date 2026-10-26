"""تست اجرای پروبها با Runner قلابی (هیچ سوکتی باز نمیشود)."""
from __future__ import annotations

from hamrah.core.probes import ProbeResult, run_all_probes


class FakeRunner:
    def __init__(self, *, external: bool, internal: bool, dns: bool, gateway: bool = True):
        self.external, self.internal = external, internal
        self.dns, self.gateway = dns, gateway
        self.calls: list[tuple] = []

    def https(self, name, url, group):
        self.calls.append(("https", url, group))
        ok = self.external if group == "external" else self.internal
        return ProbeResult(name, url, "https", ok, 12, "" if ok else "fail", group)

    def tcp(self, name, host, port, group):
        self.calls.append(("tcp", host, port, group))
        ok = self.external if group == "external" else self.internal
        return ProbeResult(name, f"{host}:{port}", "tcp", ok, 10, group=group)

    def dns_system(self, name, host):
        self.calls.append(("dns_system", host))
        return ProbeResult(name, host, "dns", self.dns, 4, group="dns")

    def dns_udp(self, name, server, domain):
        self.calls.append(("dns_udp", server))
        return ProbeResult(name, server, "dns", self.dns, 5, group="dns")

    def gateway_probe(self):
        self.calls.append(("gateway",))
        return ProbeResult("مودم/روتر", "192.168.1.1", "gateway", self.gateway, 3,
                           group="gateway")

    def link_probe(self):
        return ProbeResult("کارت شبکه", "link", "link", True, 1, group="link")


def test_run_all_probes_executes_every_category(settings):
    runner = FakeRunner(external=True, internal=True, dns=True)
    bundle = run_all_probes(settings, runner, clock=lambda: 123.0, parallel=False)
    assert bundle.ts == 123.0
    assert bundle.external_ok > 0 and bundle.internal_ok > 0 and bundle.dns_ok > 0
    assert bundle.gateway_ok == 1 and bundle.link_ok is True
    kinds = {call[0] for call in runner.calls}
    assert {"https", "tcp", "dns_system", "dns_udp", "gateway"} <= kinds
    summary = bundle.summary()
    assert summary["external"].endswith("/5") or "/" in summary["external"]
    assert len(summary["results"]) == len(bundle.results)


def test_run_all_probes_blackout(settings):
    runner = FakeRunner(external=False, internal=False, dns=False, gateway=False)
    bundle = run_all_probes(settings, runner, clock=lambda: 1.0, parallel=False)
    assert bundle.external_ok == 0 and bundle.internal_ok == 0 and bundle.dns_ok == 0
    assert bundle.gateway_ok == 0


def test_one_broken_probe_does_not_crash(settings):
    class Broken(FakeRunner):
        def https(self, *a, **kw):
            raise RuntimeError("boom")

    bundle = run_all_probes(settings, Broken(external=True, internal=True, dns=True),
                            clock=lambda: 2.0, parallel=False)
    assert any(not r.ok for r in bundle.results)
    assert bundle.link_ok is True
