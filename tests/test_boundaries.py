import tempfile
import threading
import unittest
from copy import deepcopy
from pathlib import Path

from equilibrium.authority import Authority, sign
from equilibrium.codec import digest
from equilibrium.errors import EquilibriumError
from equilibrium.evidence import Journal, verify_export
from tests.support import feed, fixture, review


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.rt, self.auth, self.journal, self.plant, self.grant = fixture()
        feed(self.rt)
        self.action = self.rt.plan(0).action
        self.token = review(self.auth)(self.action)

    def denied(self, grant=None, token=None, action=None):
        with self.assertRaises(EquilibriumError):
            self.auth.authorize(action or self.action, grant or self.grant, token or self.token, {"arm"})

    def test_keys_must_be_distinct_and_long(self):
        for g, r in [(b"x" * 32, b"x" * 32), (b"g", b"r" * 32)]:
            with self.assertRaises(EquilibriumError):
                Authority(g, r)

    def test_grant_tamper_rejected(self):
        self.grant["payload"]["principal"] = "intruder"
        self.denied()

    def test_review_tamper_rejected(self):
        self.token["payload"]["reviewer"] = "intruder"
        self.denied()

    def test_wrong_source_even_with_valid_mac(self):
        self.grant["payload"]["source"] = "f" * 64
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))

    def test_wrong_session_even_with_valid_mac(self):
        self.grant["payload"]["session"] = "other"
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))

    def test_scope_escape(self):
        self.grant["payload"]["actuators"] = ["other"]
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))

    def test_grant_expiration(self):
        self.grant["payload"]["expires_ms"] = 0
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))

    def test_grant_not_yet_valid(self):
        self.grant["payload"]["not_before_ms"] = 1
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))

    def test_review_expiration(self):
        self.token["payload"]["expires_ms"] = 0
        self.denied(token=sign(self.token["payload"], b"r" * 32))

    def test_exact_command_binding(self):
        action = deepcopy(self.action)
        action.outputs["arm"]["value"] = "0.1"
        self.denied(action=action)

    def test_review_single_use(self):
        self.auth.authorize(self.action, self.grant, self.token, {"arm"})
        self.denied()

    def test_review_atomic_single_use_under_contention(self):
        results = []
        def use():
            try:
                self.auth.authorize(self.action, self.grant, self.token, {"arm"})
                results.append(True)
            except EquilibriumError:
                results.append(False)
        threads = [threading.Thread(target=use) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 1)

    def test_grant_revocation(self):
        self.auth.revoke("grant")
        self.denied()

    def test_review_revocation(self):
        self.auth.revoke("review-0")
        self.denied()

    def test_host_may_explicitly_disable_review(self):
        grant = self.auth.issue_grant(source_sha256=self.rt.checked.source_sha256, session=self.rt.session,
            principal="service", actuators=["arm"], not_before_ms=0, expires_ms=100, nonce="no-review", review_required=False)
        result = self.auth.authorize(self.action, grant, None, {"arm"})
        self.assertIsNone(result["reviewer"])

    def test_signed_unknown_fields_rejected(self):
        self.grant["payload"]["extra"] = True
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))

    def test_bool_timestamp_not_integer(self):
        self.grant["payload"]["expires_ms"] = True
        self.denied(grant=sign(self.grant["payload"], b"g" * 32))


class EvidenceTests(unittest.TestCase):
    def record(self, j, n=0):
        return j.append({"kind": "decision", "authorized": False, "reason": "idle", "n": n})

    def test_receipt_edit_detected(self):
        j = Journal()
        self.record(j)
        data = j.export()
        data["records"][0]["payload"]["reason"] = "allowed"
        with self.assertRaises(EquilibriumError):
            verify_export(data)

    def test_receipt_reordering_detected(self):
        j = Journal()
        self.record(j, 0)
        self.record(j, 1)
        data = j.export()
        data["records"].reverse()
        with self.assertRaises(EquilibriumError):
            verify_export(data)

    def test_pinned_head_detects_rehashed_truncation(self):
        j = Journal()
        self.record(j, 0)
        head = self.record(j, 1)
        data = j.export()
        data["records"].pop()
        data["head"] = data["records"][-1]["sha256"]
        self.assertTrue(verify_export(data)["valid"])
        with self.assertRaises(EquilibriumError):
            verify_export(data, head)

    def test_unlinked_outcome_rejected(self):
        with self.assertRaises(EquilibriumError):
            Journal().append({"kind": "outcome", "action_sha256": "a" * 64})

    def test_duplicate_authorization_rejected_after_outcome(self):
        j = Journal()
        subject = {"source_sha256": "b" * 64, "session": "x", "tick": 0, "at_ms": 0,
                   "state": "motion", "outputs": {"arm": {"value": "0.1", "dimension": [1, 0, -1, 0]}}}
        sha = digest(subject)
        auth = {"kind": "decision", "authorized": True, "action_sha256": sha, "action": subject}
        j.append(auth)
        j.append({"kind": "outcome", "action_sha256": sha})
        with self.assertRaises(EquilibriumError):
            j.append(auth)

    def test_authorization_exact_action_digest_checked(self):
        j = Journal()
        with self.assertRaises(EquilibriumError):
            j.append({"kind": "decision", "authorized": True, "action_sha256": "a" * 64,
                      "action": {"source_sha256": "b" * 64, "session": "x", "tick": 0, "at_ms": 0,
                                 "state": "motion", "outputs": {"arm": {"value": "0.1", "dimension": [1, 0, -1, 0]}}}})

    def test_database_reopen_validates_persistent_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "journal.db"
            j = Journal(p)
            head = self.record(j)
            j.close()
            j = Journal(p)
            self.assertEqual(verify_export(j.export(), head)["records"], 1)
            j.close()

    def test_database_edit_detected_at_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "journal.db"
            j = Journal(p)
            self.record(j)
            j._db.execute("UPDATE receipts SET payload='{}'")
            j.close()
            with self.assertRaises(EquilibriumError):
                Journal(p)

    def test_independent_writers_keep_one_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "journal.db"
            a, b = Journal(p), Journal(p)
            errors = []
            def append(j, name):
                try:
                    for n in range(20):
                        j.append({"kind": "decision", "authorized": False, "writer": name, "n": n})
                except Exception as exc:
                    errors.append(exc)
            threads = [threading.Thread(target=append, args=(a, "a")), threading.Thread(target=append, args=(b, "b"))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            self.assertEqual(verify_export(a.export())["records"], 40)
            a.close()
            b.close()

    def test_sequence_gap_not_accepted(self):
        j = Journal()
        self.record(j)
        data = j.export()
        data["records"][0]["sequence"] = 2
        core = {k: data["records"][0][k] for k in ["sequence", "previous", "payload"]}
        data["records"][0]["sha256"] = digest(core)
        data["head"] = digest(core)
        with self.assertRaises(EquilibriumError):
            verify_export(data)

    def test_integrity_is_not_authentication(self):
        j = Journal()
        self.record(j)
        self.assertFalse(verify_export(j.export())["authenticated"])


if __name__ == "__main__":
    unittest.main()
