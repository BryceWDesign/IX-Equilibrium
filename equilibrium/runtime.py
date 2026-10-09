"""Deterministic supervisor. Effects only pass the host authority/journal boundary."""
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from .adapters import Adapter
from .authority import Action, Authority
from .codec import normalize
from .compiler import CheckedProgram, compile_source
from .errors import BoundaryError, EquilibriumError
from .determinism import deterministic
from .evidence import Journal
from .expressions import evaluate, interval
from .robust import exact_ranges, predicate
from .sensors import Sensors
from .units import Quantity


@dataclass(frozen=True)
class Plan:
    action: Action
    active: frozenset[str]
    parameters: dict
    entered_ms: int
    diagnostics: dict
    revision: int


class Runtime:
    def __init__(self, checked: CheckedProgram, *, session: str, authority: Authority,
                 journal: Journal, adapter: Adapter):
        if not session or not isinstance(session, str):
            raise BoundaryError("runtime requires a host-assigned session")
        # Recheck the source; public Python dataclasses are not a security boundary.
        self.checked = compile_source(checked.source)
        if self.checked != checked:
            raise BoundaryError("checked program was modified")
        self.program = checked.program
        self.session, self.authority, self.journal, self.adapter = session, authority, journal, adapter
        self.sensors = Sensors(self.program.channels, self.program.meshes)
        self.parameters = {p.name: p.initial for p in self.program.parameters}
        self.state = next(s.name for s in self.program.states if s.kind == "initial")
        self.entered_ms = 0
        self.tick = 0
        self.at_ms = -1
        self.revision = 0
        self.previous_outputs = {a.name: a.safe for a in self.program.actuators}
        self.halted = False
        self._lock = threading.RLock()

    def ingest(self, sample: dict, now_ms: int) -> None:
        with self._lock:
            if type(now_ms) is not int or now_ms < self.at_ms:
                raise BoundaryError("ingestion clock regression")
            try:
                self.sensors.ingest(sample, now_ms)
            finally:
                self.revision += 1

    def _clock(self, at_ms):
        if type(at_ms) is not int or at_ms < 0:
            raise BoundaryError("clock must be a nonnegative integer millisecond timestamp")
        if self.at_ms == -1 and at_ms != 0:
            raise BoundaryError("first_tick_must_be_zero")
        if self.at_ms >= 0 and Decimal(at_ms - self.at_ms) / 1000 != self.program.tick.value:
            raise BoundaryError("missed_tick_deadline")

    @deterministic
    def plan(self, at_ms: int) -> Plan:
        with self._lock:
            self._clock(at_ms)
            if self.halted:
                raise BoundaryError("terminal_latched")
            values, ranges, diagnostics = self.sensors.snapshot(at_ms)
            values.update(self.parameters)
            ranges.update(exact_ranges(self.parameters))
            states = {s.name: s for s in self.program.states}
            current = states[self.state]
            for name, expr in self.program.invariants:
                if not predicate(expr, values, ranges):
                    raise BoundaryError(f"invariant:{name}")
            for expr in current.requirements:
                if not predicate(expr, values, ranges):
                    raise BoundaryError(f"require:{current.name}")
            enabled = []
            for transition in current.transitions:
                match = (Decimal(at_ms - self.entered_ms) / 1000 >= transition.after.value
                         if transition.after is not None else predicate(transition.condition, values, ranges))
                if match:
                    enabled.append(transition.target)
            if len(enabled) > 1:
                raise BoundaryError("transition_conflict")
            state = enabled[0] if enabled else self.state
            entered_ms = at_ms if enabled else self.entered_ms
            target = states[state]
            for expr in target.requirements:
                if not predicate(expr, values, ranges):
                    raise BoundaryError(f"require:{state}")
            parameters = dict(self.parameters)
            specs = {p.name: p for p in self.program.parameters}
            for name, expr in target.adaptations:
                desired = evaluate(expr, values)
                spec = specs[name]
                bound = interval(expr, ranges)
                if bound is None or not spec.low.value <= bound[0] <= bound[1] <= spec.high.value:
                    raise BoundaryError(f"adapt_bounds:{name}")
                delta = desired.value - self.parameters[name].value
                delta = max(-spec.rate.value, min(spec.rate.value, delta))
                parameters[name] = Quantity(self.parameters[name].value + delta, desired.dim)
            prospective = {**values, **parameters}
            prospective_ranges = {**ranges, **exact_ranges(parameters)}
            for name, expr in self.program.invariants:
                if not predicate(expr, prospective, prospective_ranges):
                    raise BoundaryError(f"adapt_invariant:{name}")
            for expr in target.requirements:
                if not predicate(expr, prospective, prospective_ranges):
                    raise BoundaryError(f"adapt_require:{state}")
            outputs = {a.name: a.safe for a in self.program.actuators}
            specs = {a.name: a for a in self.program.actuators}
            for name, expr in target.commands:
                desired = evaluate(expr, values)
                spec = specs[name]
                bound = interval(expr, ranges)
                if bound is None or not spec.low.value <= bound[0] <= bound[1] <= spec.high.value:
                    raise BoundaryError(f"command_bounds:{name}")
                # Slew applies to active commands. Independent stop bypasses slew.
                delta = spec.slew.value * self.program.tick.value
                previous = self.previous_outputs[name].value
                commanded = max(previous - delta, min(previous + delta, desired.value))
                outputs[name] = Quantity(commanded, desired.dim)
            action = Action(self.checked.source_sha256, self.session, self.tick, at_ms, state,
                            {n: q.payload() for n, q in outputs.items()})
            return Plan(action, frozenset(n for n, _ in target.commands), parameters,
                        entered_ms, diagnostics, self.revision)

    def _stop(self, reason: str, at_ms: int, action: Action | None = None) -> dict:
        self.state, self.halted = self.program.fault, True
        safe = {a.name: a.safe.payload() for a in self.program.actuators}
        try:
            observation = self.adapter.stop(safe)
            stop_ok = True
        except Exception:
            observation, stop_ok = {}, False
        record = {"kind": "stop", "session": self.session, "tick": self.tick, "at_ms": at_ms,
                  "state": self.state, "reason": reason, "stop_confirmed": stop_ok,
                  "observation": observation, "action_sha256": action.sha256 if action else None}
        try:
            self.journal.append(record)
            evidence_ok = True
        except Exception:
            evidence_ok = False
        self.revision += 1
        return {**record, "evidence_committed": evidence_ok, "authorized": False}

    def emergency_stop(self, reason: str, at_ms: int) -> dict:
        with self._lock:
            return self._stop(reason, at_ms)

    def execute(self, plan: Plan, *, grant: dict | None = None, review: dict | None = None) -> dict:
        with self._lock:
            action = plan.action
            try:
                # Recompute against current snapshot, never dispatch an externally altered plan.
                fresh = self.plan(action.at_ms)
                if fresh != plan:
                    raise BoundaryError("stale_or_modified_plan")
                if not plan.active:
                    states = {s.name: s for s in self.program.states}
                    terminal = states[action.state].kind == "terminal"
                    payload = {"kind": "decision", "authorized": False, "reason": "terminal" if terminal else "idle",
                               "action_sha256": action.sha256, "action": normalize(action), "diagnostics": plan.diagnostics}
                    self.journal.append(payload)
                    # Idle means explicit safe setpoints, never retain a previous active command.
                    observation = self.adapter.stop(action.outputs)
                    self.state, self.entered_ms = action.state, plan.entered_ms
                    self.parameters, self.halted = plan.parameters, terminal
                    self.previous_outputs = {a.name: a.safe for a in self.program.actuators}
                    self.at_ms, self.tick = action.at_ms, self.tick + 1
                    self.revision += 1
                    self.journal.append({"kind": "stop", "reason": payload["reason"], "session": self.session,
                                         "at_ms": action.at_ms, "stop_confirmed": True, "observation": observation})
                    return {**payload, "observation": observation, "stop_confirmed": True}
                authority = self.authority.authorize(action, grant, review, set(plan.active))
                payload = {"kind": "decision", "authorized": True, "reason": "allowed", "authority": authority,
                           "action_sha256": action.sha256, "action": normalize(action), "diagnostics": plan.diagnostics}
                self.journal.append(payload)  # synchronous durable commit before adapter invocation
                # Recheck revocation and grant validity immediately after the commit.
                # Review is already reserved, so this check does not consume it a second time.
                self.authority.check_grant(action, grant, set(plan.active))
                if self.plan(action.at_ms) != plan:
                    raise BoundaryError("snapshot_changed_after_commit")
                observation = self.adapter.apply(action)
                self.journal.append({"kind": "outcome", "action_sha256": action.sha256,
                                     "status": "observed", "observation": observation})
                self.state, self.entered_ms, self.parameters = action.state, plan.entered_ms, plan.parameters
                self.previous_outputs = {n: Quantity(Decimal(v["value"]), tuple(v["dimension"])) for n, v in action.outputs.items()}
                self.at_ms, self.tick = action.at_ms, self.tick + 1
                self.revision += 1
                return {**payload, "observation": observation}
            except Exception as exc:
                return self._stop(str(exc) if isinstance(exc, EquilibriumError) else "host_boundary_failure", action.at_ms, action)

    def step(self, at_ms: int, *, grant: dict | None = None,
             review_provider: Callable[[Action], dict | None] | None = None) -> dict:
        with self._lock:
            try:
                plan = self.plan(at_ms)
                review = review_provider(plan.action) if review_provider and plan.active else None
            except Exception as exc:
                return self._stop(str(exc) if isinstance(exc, EquilibriumError) else "review_provider_failure", at_ms)
            return self.execute(plan, grant=grant, review=review)
