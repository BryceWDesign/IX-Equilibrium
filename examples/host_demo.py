"""Real loopback sensor I/O and witnessed file effects, with synthetic reviews.

This command sink writes setpoints to a local file. It is not a robot adapter.
"""
import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from equilibrium.authority import Authority
from equilibrium.codec import read_json, write_json
from equilibrium.compiler import compile_source
from equilibrium.evidence import Journal, verify_export
from equilibrium.runtime import Runtime
from equilibrium.transport import SensorBridge, send_sample


class WitnessedFileSink:
    def __init__(self, folder, database):
        self.folder, self.database = folder, database

    def apply(self, action):
        observer = Journal(self.database)
        records = observer.export()["records"]
        observer.close()
        if not any(r["payload"].get("authorized") is True and r["payload"].get("action_sha256") == action.sha256 for r in records):
            raise RuntimeError("no independently visible committed authorization")
        write_json(self.folder / "command.json", {"action_sha256": action.sha256, "setpoints": action.outputs})
        return {"command_file_written": True, "physical_motion_observed": False}

    def stop(self, safe_outputs):
        write_json(self.folder / "stop.json", {"requested_fallback": safe_outputs})
        return {"fallback_file_written": True, "physical_stop_observed": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="out/host-demo")
    parser.add_argument("--deny-review", action="store_true")
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / "journal.sqlite"
    if database.exists() or (folder / "command.json").exists():
        raise SystemExit("Choose a fresh output directory")
    c = compile_source((ROOT / "examples/assist.eq").read_bytes().decode("utf-8"))
    session = "host-demo-" + secrets.token_hex(16)
    authority = Authority(secrets.token_bytes(32), secrets.token_bytes(32))
    sensor_key = secrets.token_bytes(32)
    journal = Journal(database)
    sink = WitnessedFileSink(folder, database)
    runtime = Runtime(c, session=session, authority=authority, journal=journal, adapter=sink)
    grant = authority.issue_grant(source_sha256=c.source_sha256, session=session, principal="local-demo-fixture",
                                  actuators=["arm"], not_before_ms=0, expires_ms=1000, nonce=secrets.token_hex(16))
    try:
        with SensorBridge(session=session, source_sha256=c.source_sha256,
                          producers={"fixture": {"key": sensor_key, "channels": [ch.name for ch in c.program.channels]}}) as bridge:
            samples = read_json(ROOT / "examples/assist.scenario.json")["events"][2]["samples"]
            for sample in samples:
                sample["at_ms"], sample["sequence"] = 0, 0
                send_sample(bridge.address, producer="fixture", key=sensor_key, session=session,
                            source_sha256=c.source_sha256, sample=sample)
                bridge.receive(runtime, now_ms=0)
        def review(action):
            return None if args.deny_review else authority.issue_review(action, reviewer="synthetic-local-review",
                                                                       expires_ms=100, nonce=secrets.token_hex(16))
        result = runtime.step(0, grant=grant, review_provider=review)
        runtime.emergency_stop("host_demo_cleanup", 0)
        evidence = journal.export()
        write_json(folder / "evidence.json", evidence)
        print({"authorized": result["authorized"], "file_effect": (folder / "command.json").exists(),
               "verification": verify_export(evidence), "review_is_synthetic": True})
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
