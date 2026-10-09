import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from equilibrium.adapters import VirtualPlant
from equilibrium.codec import read_json
from equilibrium.errors import EquilibriumError
from equilibrium.evidence import Journal, verify_export
from equilibrium.runtime import Runtime
from equilibrium.simulation import FaultJournal, campaign, explore, replay, simulate
from tests.support import ROOT, SOURCE, checked, feed, fixture, review, sample, scenario


class RuntimeTests(unittest.TestCase):
    def test_authorized_command_moves_virtual_plant(self):
        rt, auth, j, plant, grant = fixture()
        feed(rt)
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertTrue(result["authorized"])
        self.assertEqual(result["action"]["outputs"]["arm"]["value"], "0.02")
        self.assertEqual(plant.observe()["positions_m"]["arm"], "0.0004")
        self.assertEqual(verify_export(j.export())["unresolved_authorizations"], [])

    def test_no_grant_no_dispatch(self):
        rt, auth, _, plant, _ = fixture()
        feed(rt)
        self.assertFalse(rt.step(0, review_provider=review(auth))["authorized"])
        self.assertEqual(plant.calls, [])
        self.assertTrue(rt.halted)

    def test_no_review_no_dispatch(self):
        rt, _, _, plant, grant = fixture()
        feed(rt)
        self.assertFalse(rt.step(0, grant=grant)["authorized"])
        self.assertEqual(plant.calls, [])

    def test_source_declarations_cannot_grant_authority(self):
        rt, _, _, plant, _ = fixture()
        feed(rt)
        rt.step(0)
        self.assertEqual(len(plant.calls), 0)

    def test_host_cannot_receive_out_of_range_command(self):
        source = SOURCE.replace("gain * 0.2 mps", "clearance / 1 s")
        rt, auth, _, plant, grant = fixture(source)
        feed(rt)
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertIn("command_bounds", result["reason"])
        self.assertEqual(plant.calls, [])

    def test_uncertainty_crossing_guard_denied(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt, distance="0.205")
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(result["reason"], "uncertain_predicate")
        self.assertEqual(plant.calls, [])

    def test_invariant_stops_before_dispatch(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt, load="5")
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(plant.calls, [])
        self.assertIn(result["reason"], ["uncertain_predicate", "invariant:contact_load"])

    def test_stale_sensor_stops_running_plant(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        for at in [0, 20, 40, 60]:
            self.assertTrue(rt.step(at, grant=grant, review_provider=review(auth))["authorized"])
        result = rt.step(80, grant=grant, review_provider=review(auth))
        self.assertIn("unavailable:load", result["reason"])
        self.assertEqual(len(plant.calls), 4)
        self.assertEqual(plant.observe()["setpoints"]["arm"]["value"], "0")

    def test_freshness_boundary_inclusive(self):
        rt, _, _, _, _ = fixture()
        feed(rt)
        self.assertIn("load", rt.sensors.snapshot(60)[0])
        self.assertNotIn("load", rt.sensors.snapshot(61)[0])

    def test_mesh_quorum_tolerates_missing_member(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        del rt.sensors.readings["tactile"]
        self.assertTrue(rt.step(0, grant=grant, review_provider=review(auth))["authorized"])
        self.assertEqual(len(plant.calls), 1)

    def test_mesh_quorum_missing_stops(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        for name in ["tactile", "proximity"]:
            del rt.sensors.readings[name]
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertIn("clearance", result["reason"])
        self.assertEqual(plant.calls, [])

    def test_mesh_dissent_is_not_silently_discarded(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        rt.ingest(sample("tactile", "0.1", "m", sequence=1), 0)
        self.assertEqual(rt.sensors.snapshot(0)[2]["clearance"], "mesh_disagreement")
        rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(plant.calls, [])

    def test_sample_replay_invalidates_channel(self):
        rt, _, _, _, _ = fixture()
        feed(rt)
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("load", "1", "N", sequence=0), 0)
        self.assertNotIn("load", rt.sensors.snapshot(0)[0])

    def test_sample_future_timestamp(self):
        rt, _, _, _, _ = fixture()
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("load", "1", "N", at=20), 0)

    def test_sample_timestamp_regression(self):
        rt, _, _, _, _ = fixture()
        rt.ingest(sample("load", "1", "N", at=20), 20)
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("load", "1", "N", at=10, sequence=1), 20)

    def test_sample_wrong_units(self):
        rt, _, _, _, _ = fixture()
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("load", "1", "m"), 0)

    def test_sample_uncertainty_ceiling(self):
        rt, _, _, _, _ = fixture()
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("load", "1", "N", uncertainty="0.2"), 0)

    def test_sample_bool_type_strict(self):
        rt, _, _, _, _ = fixture()
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("intent", 1, "bool"), 0)

    def test_unknown_sample_channel(self):
        rt, _, _, _, _ = fixture()
        with self.assertRaises(EquilibriumError):
            rt.ingest(sample("unknown", "1", "N"), 0)

    def test_bad_sample_schema(self):
        rt, _, _, _, _ = fixture()
        with self.assertRaises(EquilibriumError):
            rt.ingest({"channel": "load"}, 0)

    def test_bad_sample_schema_invalidates_previous_reading(self):
        rt, _, _, _, _ = fixture()
        feed(rt)
        with self.assertRaises(EquilibriumError):
            rt.ingest({"channel": "load"}, 0)
        self.assertNotIn("load", rt.sensors.snapshot(0)[0])

    def test_parameter_adaptation_rate_limited(self):
        rt, auth, _, _, grant = fixture()
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(str(rt.parameters["gain"].value), "0.6")
        feed(rt, at=20)
        rt.step(20, grant=grant, review_provider=review(auth))
        self.assertEqual(str(rt.parameters["gain"].value), "0.7")

    def test_adaptation_uses_previous_snapshot_for_command(self):
        rt, auth, _, _, grant = fixture(SOURCE.replace("slew 1 mps2", "slew 100 mps2"))
        feed(rt)
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(result["action"]["outputs"]["arm"]["value"], "0.1")
        self.assertEqual(str(rt.parameters["gain"].value), "0.6")

    def test_unsafe_adaptation_denied_without_parameter_commit(self):
        rt, auth, _, plant, grant = fixture(SOURCE.replace("clamp(clearance / 1 m, 0.1, 1.0)", "clearance / 0.1 m"))
        feed(rt)
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertIn("adapt_bounds", result["reason"])
        self.assertEqual(rt.parameters["gain"].value, checked().program.parameters[0].initial.value)
        self.assertEqual(plant.calls, [])

    def test_idle_returns_to_safe_setpoint(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        feed(rt, at=20, intent=False)
        result = rt.step(20)
        self.assertEqual(result["reason"], "idle")
        self.assertEqual(plant.observe()["setpoints"]["arm"]["value"], "0")

    def test_terminal_state_latched(self):
        rt, auth, _, plant, grant = fixture(SOURCE.replace("after 2 s", "after 20 ms"))
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        feed(rt, at=20)
        self.assertEqual(rt.step(20)["reason"], "terminal")
        self.assertTrue(rt.halted)
        rt.step(40, grant=grant, review_provider=review(auth))
        self.assertEqual(len(plant.calls), 1)

    def test_transition_conflict_denied(self):
        rt, auth, _, plant, grant = fixture(SOURCE.replace("when intent -> moving;", "when intent -> moving; when true -> complete;"))
        feed(rt)
        self.assertEqual(rt.step(0, grant=grant, review_provider=review(auth))["reason"], "transition_conflict")
        self.assertEqual(plant.calls, [])

    def test_tick_deadline_miss_stops(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        feed(rt, at=40)
        self.assertEqual(rt.step(40, grant=grant, review_provider=review(auth))["reason"], "missed_tick_deadline")
        self.assertEqual(len(plant.calls), 1)

    def test_first_tick_not_zero(self):
        rt, _, _, _, _ = fixture()
        self.assertEqual(rt.step(20)["reason"], "first_tick_must_be_zero")

    def test_modified_plan_denied(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        plan = rt.plan(0)
        plan.action.outputs["arm"]["value"] = "0.2"
        token = review(auth)(plan.action)
        self.assertEqual(rt.execute(plan, grant=grant, review=token)["reason"], "stale_or_modified_plan")
        self.assertEqual(plant.calls, [])

    def test_stale_sensor_revision_plan_denied(self):
        rt, auth, _, plant, grant = fixture()
        feed(rt)
        plan = rt.plan(0)
        rt.ingest(sample("vision", "0.7", "m", sequence=1), 0)
        rt.execute(plan, grant=grant, review=review(auth)(plan.action))
        self.assertEqual(plant.calls, [])

    def test_pre_dispatch_evidence_failure_blocks(self):
        j = FaultJournal()
        j.failure = "before"
        rt, auth, _, plant, grant = fixture(journal=j)
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(plant.calls, [])

    def test_post_dispatch_evidence_failure_reports_unresolved(self):
        j = FaultJournal()
        j.failure = "after"
        rt, auth, _, plant, grant = fixture(journal=j)
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(len(plant.calls), 1)
        self.assertEqual(len(verify_export(j.export())["unresolved_authorizations"]), 1)
        self.assertTrue(rt.halted)

    def test_stop_still_requested_when_all_evidence_fails(self):
        j = FaultJournal()
        j.failure = "all"
        rt, _, _, plant, _ = fixture(journal=j)
        feed(rt)
        result = rt.step(0)
        self.assertTrue(plant.stops)
        self.assertFalse(result["evidence_committed"])

    def test_failed_stop_never_claimed_successful(self):
        rt, _, _, plant, _ = fixture()
        plant.fail_stop = True
        feed(rt)
        self.assertFalse(rt.step(0)["stop_confirmed"])

    def test_adapter_failure_latches_and_records_unresolved(self):
        rt, auth, j, plant, grant = fixture()
        plant.fail_apply = True
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        self.assertTrue(rt.halted)
        self.assertEqual(len(verify_export(j.export())["unresolved_authorizations"]), 1)

    def test_revoke_after_commit_blocks_adapter(self):
        class RevokingJournal(Journal):
            def append(self, payload):
                sha = super().append(payload)
                if payload["kind"] == "decision" and payload.get("authorized"):
                    self.authority.revoke("grant")
                return sha
        j = RevokingJournal()
        rt, auth, _, plant, grant = fixture(journal=j)
        j.authority = auth
        feed(rt)
        rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(plant.calls, [])

    def test_sensor_change_after_commit_blocks_adapter(self):
        class MutatingJournal(Journal):
            def append(self, payload):
                sha = super().append(payload)
                if payload["kind"] == "decision" and payload.get("authorized"):
                    self.runtime.ingest(sample("load", "1", "N", sequence=1), 0)
                return sha
        j = MutatingJournal()
        rt, auth, _, plant, grant = fixture(journal=j)
        j.runtime = rt
        feed(rt)
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(plant.calls, [])
        self.assertEqual(result["reason"], "snapshot_changed_after_commit")

    def test_adaptation_cannot_break_invariant(self):
        source = SOURCE.replace("invariant contact_load : load < 5 N;", "invariant gain_limit : gain < 0.55;")
        rt, auth, _, plant, grant = fixture(source)
        feed(rt)
        result = rt.step(0, grant=grant, review_provider=review(auth))
        self.assertEqual(plant.calls, [])
        self.assertEqual(result["reason"], "adapt_invariant:gain_limit")
        self.assertEqual(str(rt.parameters["gain"].value), "0.5")

    def test_independent_connection_witnesses_committed_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "journal.sqlite"
            target = Path(tmp) / "effect.json"
            class Witness(VirtualPlant):
                def apply(self, action):
                    reader = Journal(database)
                    receipts = reader.export()["records"]
                    reader.close()
                    if not any(r["payload"].get("action_sha256") == action.sha256 and r["payload"].get("authorized") for r in receipts):
                        raise AssertionError("authorization not independently visible")
                    target.write_text(action.sha256)
                    return super().apply(action)
            c = checked()
            plant = Witness(c.program.actuators, c.program.tick.value)
            j = Journal(database)
            rt, auth, _, _, grant = fixture(journal=j, adapter=plant)
            feed(rt)
            result = rt.step(0, grant=grant, review_provider=review(auth))
            self.assertTrue(result["authorized"])
            self.assertEqual(target.read_text(), result["action_sha256"])
            j.close()

    def test_compiled_dataclass_forgery_rejected(self):
        c = checked()
        forged = replace(c, program=replace(c.program, capabilities=()))
        with self.assertRaises(EquilibriumError):
            Runtime(forged, session="x", authority=fixture()[1], journal=Journal(),
                    adapter=VirtualPlant(c.program.actuators, c.program.tick.value))

    def test_two_actuator_batch(self):
        c = checked((ROOT / "examples/shared_control.eq").read_text())
        b = simulate(c, read_json(ROOT / "examples/shared_control.scenario.json"))
        self.assertEqual(b["final"]["adapter_calls"], 12)
        self.assertEqual(set(b["steps"][0]["result"]["action"]["outputs"]), {"left", "right"})

    def test_all_scenarios_replay_exactly(self):
        for path in ROOT.glob("examples/*.eq"):
            with self.subTest(path=path):
                b = simulate(checked(path.read_text()), read_json(path.with_suffix(".scenario.json")))
                self.assertTrue(replay(b)["reproduced"])

    def test_replay_tampered_outcome_rejected(self):
        b = simulate(checked(), scenario())
        b["final"]["adapter_calls"] = 999
        with self.assertRaises(EquilibriumError):
            replay(b)

    def test_fault_campaign(self):
        result = campaign(checked(), scenario())
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["cases"]), 13)

    def test_finite_exploration_includes_safe_and_stop_paths(self):
        result = explore(checked(), read_json(ROOT / "examples/assist.choices.json"), 3)
        self.assertEqual(result["runs"], 27)
        self.assertTrue(result["counterexamples"])
        self.assertIn("allowed", result["outcomes"])
        self.assertFalse(result["general_safety_proof"])

    def test_finite_exploration_budget(self):
        with self.assertRaises(EquilibriumError):
            explore(checked(), read_json(ROOT / "examples/assist.choices.json"), 8, max_runs=100)


if __name__ == "__main__":
    unittest.main()
