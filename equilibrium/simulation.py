"""Explicitly synthetic authority, deterministic scenarios, replay and fault campaigns."""
from copy import deepcopy
from itertools import product

from .adapters import VirtualPlant
from .authority import Authority
from .codec import digest, normalize
from .compiler import CheckedProgram, compile_source
from .errors import BoundaryError, EquilibriumError
from .evidence import Journal, verify_export
from .runtime import Runtime

SCENARIO_FORMAT = "equilibrium.scenario/1"
BUNDLE_FORMAT = "equilibrium.simulation/1"


class FaultJournal(Journal):
    def __init__(self, path=":memory:"):
        self.failure = None
        super().__init__(path)

    def append(self, payload):
        if (self.failure == "before" and payload["kind"] == "decision"
            or self.failure == "after" and payload["kind"] == "outcome"
            or self.failure == "all"):
            raise BoundaryError("injected evidence failure")
        return super().append(payload)


def validate_scenario(scenario):
    if not isinstance(scenario, dict) or set(scenario) != {"format", "name", "events"} or scenario["format"] != SCENARIO_FORMAT:
        raise EquilibriumError("invalid scenario envelope")
    if not isinstance(scenario["name"], str) or not scenario["name"]:
        raise EquilibriumError("scenario requires a nonempty name")
    if not isinstance(scenario["events"], list) or not 1 <= len(scenario["events"]) <= 10000:
        raise EquilibriumError("scenario requires 1..10000 events")
    allowed = {"at_ms", "samples", "simulation_grant", "simulation_review", "revoke_grant",
               "adapter_failure", "stop_failure", "journal_failure"}
    for event in scenario["events"]:
        if not isinstance(event, dict) or not {"at_ms", "samples"} <= set(event) <= allowed:
            raise EquilibriumError("invalid scenario event schema")
        if type(event["at_ms"]) is not int or event["at_ms"] < 0 or not isinstance(event["samples"], list):
            raise EquilibriumError("invalid event time or samples")
        for key in allowed - {"at_ms", "samples", "journal_failure"}:
            if key in event and type(event[key]) is not bool:
                raise EquilibriumError(f"{key} must be bool")
        if event.get("journal_failure") not in (None, "before", "after", "all"):
            raise EquilibriumError("invalid journal failure mode")


def simulate(checked: CheckedProgram, scenario: dict, *, database: str = ":memory:") -> dict:
    validate_scenario(scenario)
    # These PUBLIC fixed fixture keys confer no real-world identity or authority.
    authority = Authority(b"simulation-grant-key-public-only!", b"simulation-review-key-public-only")
    journal = FaultJournal(database)
    if journal.export()["records"]:
        journal.close()
        raise EquilibriumError("simulation database must be empty for reproducible replay")
    plant = VirtualPlant(checked.program.actuators, checked.program.tick.value)
    session = "simulation-" + digest({"source": checked.source_sha256, "scenario": scenario})[:20]
    runtime = Runtime(checked, session=session, authority=authority, journal=journal, adapter=plant)
    grant = authority.issue_grant(source_sha256=checked.source_sha256, session=session,
                                  principal="synthetic-operator", actuators=[a.name for a in checked.program.actuators] or ["unused"],
                                  not_before_ms=0, expires_ms=1_000_000_000, nonce="synthetic-grant")
    steps = []
    try:
        for index, event in enumerate(scenario["events"]):
            if runtime.halted:
                break
            journal.failure = event.get("journal_failure")
            plant.fail_apply = event.get("adapter_failure", False)
            plant.fail_stop = event.get("stop_failure", False)
            if event.get("revoke_grant", False):
                authority.revoke("synthetic-grant")
            ingestion_errors = []
            for sample in event["samples"]:
                try:
                    runtime.ingest(sample, event["at_ms"])
                except EquilibriumError as exc:
                    ingestion_errors.append(str(exc))
            if ingestion_errors:
                result = runtime.emergency_stop("sample_rejected:" + ";".join(ingestion_errors), event["at_ms"])
            else:
                def review(action):
                    return authority.issue_review(action, reviewer="synthetic-reviewer", expires_ms=event["at_ms"] + 1000,
                                                  nonce=f"synthetic-review-{index}") if event.get("simulation_review", False) else None
                result = runtime.step(event["at_ms"], grant=grant if event.get("simulation_grant", False) else None,
                                      review_provider=review)
            steps.append({"event": index, "at_ms": event["at_ms"], "result": normalize(result),
                          "parameters": {n: q.payload() for n, q in runtime.parameters.items()},
                          "adapter_calls": len(plant.calls)})
        evidence = journal.export()
        verification = verify_export(evidence)
        body = {"format": BUNDLE_FORMAT, "authority_mode": "synthetic_simulation_only",
                "source": checked.source, "source_sha256": checked.source_sha256, "scenario": scenario,
                "steps": steps, "evidence": evidence, "verification": verification,
                "final": {"state": runtime.state, "halted": runtime.halted,
                          "adapter_calls": len(plant.calls), "stop_requests": len(plant.stops),
                          "observation": plant.observe()}}
        return {**body, "bundle_sha256": digest(body)}
    finally:
        journal.close()


def replay(bundle: dict) -> dict:
    if (not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT
        or not isinstance(bundle.get("source"), str) or not isinstance(bundle.get("scenario"), dict)):
        raise EquilibriumError("invalid simulation bundle")
    actual = simulate(compile_source(bundle["source"]), bundle["scenario"])
    if actual != bundle:
        raise BoundaryError("simulation replay differs from recorded bundle")
    return {"reproduced": True, "steps": len(actual["steps"]), "bundle_sha256": actual["bundle_sha256"]}


def campaign(checked: CheckedProgram, baseline: dict) -> dict:
    """Inject boundary faults at the first commanded event, assert dispatch isolation."""
    baseline_result = simulate(checked, baseline)
    candidates = [s["event"] for s in baseline_result["steps"] if s["result"].get("authorized")]
    if not candidates:
        raise EquilibriumError("campaign baseline must execute at least one authorized command")
    index = candidates[0]
    mutations = {"missing_grant": ("simulation_grant", False),
                 "missing_review": ("simulation_review", False),
                 "revoked_grant": ("revoke_grant", True),
                 "pre_evidence_failure": ("journal_failure", "before"),
                 "post_evidence_failure": ("journal_failure", "after"),
                 "adapter_failure": ("adapter_failure", True),
                 "stop_failure": ("stop_failure", True)}
    if {"load", "vision", "proximity", "tactile"} <= {c.name for c in checked.program.channels}:
        mutations.update({
                 "sensor_future": ("sample_mutation", ("load", "at_ms", 100000)),
                 "sensor_replay": ("sample_mutation", ("load", "sequence", -1)),
                 "sensor_uncertainty": ("sample_mutation", ("load", "uncertainty", "0.2")),
                 "mesh_disagreement": ("sample_mutation", ("tactile", "value", "0.1")),
                 "load_veto": ("sample_mutation", ("load", "value", "6")),
                 "uncertain_clearance": ("all_distances", "0.205")})
    cases = []
    for name, (key, value) in mutations.items():
        scenario = deepcopy(baseline)
        scenario["name"] = name
        if key == "sample_mutation":
            channel, field, replacement = value
            samples = scenario["events"][index]["samples"]
            matches = [s for s in samples if s["channel"] == channel]
            if not matches:
                raise EquilibriumError(f"assist campaign requires channel {channel}")
            matches[0][field] = replacement
        elif key == "all_distances":
            for sample in scenario["events"][index]["samples"]:
                if sample["channel"] in {"vision", "proximity", "tactile"}:
                    sample["value"] = value
        else:
            scenario["events"][index][key] = value
        if name == "stop_failure":
            scenario["events"][index]["simulation_review"] = False
        result = simulate(checked, scenario)
        final = result["final"]
        expected_calls = baseline_result["steps"][index - 1]["adapter_calls"] if index else 0
        if name == "post_evidence_failure":
            expected_calls += 1  # effect occurred; cannot claim rollback
        passed = final["halted"] and final["adapter_calls"] == expected_calls
        if name == "stop_failure":
            passed = passed and result["steps"][-1]["result"].get("stop_confirmed") is False
        cases.append({"name": name, "passed": passed, "reason": result["steps"][-1]["result"]["reason"],
                      "adapter_calls": final["adapter_calls"], "unresolved": result["verification"]["unresolved_authorizations"]})
    return {"format": "equilibrium.campaign/1", "passed": all(c["passed"] for c in cases), "cases": cases}


def explore(checked: CheckedProgram, choices: dict, depth: int, max_runs: int = 10000) -> dict:
    """Exhaustive finite sample-choice enumeration, NOT a general formal proof."""
    if not isinstance(choices, dict) or set(choices) != {"choices"} or not isinstance(choices["choices"], list):
        raise EquilibriumError("exploration input requires a choices array")
    options = choices["choices"]
    if not options or type(depth) is not int or not 1 <= depth <= 8 or len(options) ** depth > max_runs:
        raise EquilibriumError("exploration exceeds depth or run budget")
    outcomes, counterexamples = {}, []
    for indexes in product(range(len(options)), repeat=depth):
        events = []
        for step, option in enumerate(indexes):
            if not isinstance(options[option], list):
                raise EquilibriumError("each exploration choice must be a sample array")
            at_ms = int(checked.program.tick.value * 1000) * step
            samples = deepcopy(options[option])
            for sample in samples:
                sample["at_ms"], sample["sequence"] = at_ms, step
            events.append({"at_ms": at_ms, "samples": samples, "simulation_grant": True, "simulation_review": True})
        bundle = simulate(checked, {"format": SCENARIO_FORMAT, "name": "finite-exploration", "events": events})
        reason = bundle["steps"][-1]["result"]["reason"]
        outcomes[reason] = outcomes.get(reason, 0) + 1
        if bundle["final"]["halted"] and len(counterexamples) < 20:
            counterexamples.append({"choices": list(indexes), "reason": reason})
    return {"format": "equilibrium.exploration/1", "scope": "finite synthetic input enumeration",
            "runs": len(options) ** depth, "depth": depth, "outcomes": outcomes,
            "counterexamples": counterexamples, "general_safety_proof": False}
