from pathlib import Path

from equilibrium.adapters import VirtualPlant
from equilibrium.authority import Authority
from equilibrium.codec import read_json
from equilibrium.compiler import compile_source
from equilibrium.evidence import Journal
from equilibrium.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "examples/assist.eq").read_text()


def checked(source=SOURCE):
    return compile_source(source)


def fixture(source=SOURCE, journal=None, adapter=None):
    c = checked(source)
    authority = Authority(b"g" * 32, b"r" * 32)
    j = journal or Journal()
    plant = adapter or VirtualPlant(c.program.actuators, c.program.tick.value)
    runtime = Runtime(c, session="test-session", authority=authority, journal=j, adapter=plant)
    grant = authority.issue_grant(source_sha256=c.source_sha256, session=runtime.session,
        principal="operator", actuators=[a.name for a in c.program.actuators],
        not_before_ms=0, expires_ms=10000, nonce="grant")
    return runtime, authority, j, plant, grant


def sample(name, value, unit, at=0, sequence=0, uncertainty="0"):
    return dict(channel=name, value=value, unit=unit, at_ms=at, sequence=sequence, uncertainty=uncertainty)


def feed(runtime, at=0, intent=True, distance="0.7", load="1", sequence=None):
    seq = at // 20 if sequence is None else sequence
    for n in ["vision", "proximity", "tactile"]:
        runtime.ingest(sample(n, distance, "m", at, seq, "0.01"), at)
    runtime.ingest(sample("load", load, "N", at, seq, "0.1"), at)
    runtime.ingest(sample("intent", intent, "bool", at, seq), at)


def review(authority):
    return lambda action: authority.issue_review(action, reviewer="reviewer", expires_ms=action.at_ms + 100,
                                                 nonce=f"review-{action.tick}")


def scenario():
    return read_json(ROOT / "examples/assist.scenario.json")
