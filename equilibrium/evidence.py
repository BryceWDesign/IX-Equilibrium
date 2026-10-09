"""Durable SQLite pre-dispatch journal with canonical hash-linked receipts."""
import sqlite3
import threading
from pathlib import Path

from .codec import digest, loads, canonical
from .errors import BoundaryError

GENESIS = "0" * 64


def verify_export(data: dict, expected_head: str | None = None) -> dict:
    if not isinstance(data, dict) or set(data) != {"format", "records", "head"} or data["format"] != "equilibrium.evidence/1":
        raise BoundaryError("invalid evidence envelope")
    previous = GENESIS
    pending = set()
    seen_actions = set()
    if not isinstance(data["records"], list):
        raise BoundaryError("records must be an array")
    for sequence, record in enumerate(data["records"], 1):
        if not isinstance(record, dict) or set(record) != {"sequence", "previous", "payload", "sha256"}:
            raise BoundaryError("invalid receipt schema")
        core = {k: record[k] for k in ("sequence", "previous", "payload")}
        if type(record["sequence"]) is not int or record["sequence"] != sequence or record["previous"] != previous or digest(core) != record["sha256"]:
            raise BoundaryError("evidence sequence, chain or digest mismatch")
        payload = record["payload"]
        if not isinstance(payload, dict) or payload.get("kind") not in {"decision", "outcome", "stop"}:
            raise BoundaryError("unknown evidence event")
        if payload["kind"] == "decision" and payload.get("authorized") is True:
            action = payload.get("action_sha256")
            if not isinstance(action, str) or action in seen_actions:
                raise BoundaryError("invalid or duplicate authorization")
            subject = payload.get("action")
            if (not isinstance(subject, dict) or set(subject) != {"source_sha256", "session", "tick", "at_ms", "state", "outputs"}
                or digest(subject) != action or type(subject["tick"]) is not int or subject["tick"] < 0
                or type(subject["at_ms"]) is not int or subject["at_ms"] < 0
                or not isinstance(subject["outputs"], dict) or not subject["outputs"]
                or not isinstance(subject["session"], str) or not subject["session"]
                or not isinstance(subject["state"], str) or not subject["state"]):
                raise BoundaryError("authorization action binding mismatch")
            seen_actions.add(action)
            pending.add(action)
        if payload["kind"] == "outcome":
            action = payload.get("action_sha256")
            if action not in pending:
                raise BoundaryError("outcome lacks preceding authorization")
            pending.remove(action)
        previous = record["sha256"]
    if previous != data["head"] or expected_head is not None and previous != expected_head:
        raise BoundaryError("evidence head mismatch or truncation")
    return {"valid": True, "records": len(data["records"]), "head": previous,
            "unresolved_authorizations": sorted(pending), "authenticated": False}


class Journal:
    def __init__(self, path: str | Path = ":memory:"):
        self._lock = threading.RLock()
        try:
            self._db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("CREATE TABLE IF NOT EXISTS receipts (sequence INTEGER PRIMARY KEY, previous TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE)")
            verify_export(self.export())  # full startup validation, never a silent cache trust
        except Exception as exc:
            if hasattr(self, "_db"):
                self._db.close()
            if isinstance(exc, BoundaryError):
                raise
            raise BoundaryError("journal open or startup validation failed") from exc

    def append(self, payload: dict) -> str:
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                rows = self._db.execute("SELECT sequence, previous, payload, sha256 FROM receipts ORDER BY sequence").fetchall()
                # Full replay deliberately retained in v0.1.0, including independent writers.
                records = [dict(sequence=s, previous=p, payload=loads(v), sha256=h) for s, p, v, h in rows]
                head = rows[-1][3] if rows else GENESIS
                verify_export({"format": "equilibrium.evidence/1", "records": records, "head": head})
                record = {"sequence": len(rows) + 1, "previous": head, "payload": payload}
                sha = digest(record)
                # Validate event semantics before committing the next receipt.
                verify_export({"format": "equilibrium.evidence/1", "records": records + [{**record, "sha256": sha}], "head": sha})
                self._db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?)", (record["sequence"], head, canonical(payload), sha))
                self._db.execute("COMMIT")
                return sha
            except Exception as exc:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                if isinstance(exc, BoundaryError):
                    raise
                raise BoundaryError("evidence append failed") from exc

    def export(self) -> dict:
        with self._lock:
            rows = self._db.execute("SELECT sequence, previous, payload, sha256 FROM receipts ORDER BY sequence").fetchall()
            records = [dict(sequence=s, previous=p, payload=loads(v), sha256=h) for s, p, v, h in rows]
            return {"format": "equilibrium.evidence/1", "records": records, "head": rows[-1][3] if rows else GENESIS}

    def close(self):
        self._db.close()

