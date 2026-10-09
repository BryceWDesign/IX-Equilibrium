"""Source validation, dimensional checking and revision-bound checked IR."""
from dataclasses import dataclass

from .codec import digest, normalize, source_digest
from .errors import Diagnostic, EquilibriumError
from .determinism import deterministic
from .expressions import interval, type_of
from .parser import parse
from .syntax import Program
from .units import UNITS

IR_VERSION = "equilibrium.ir/1"


@dataclass(frozen=True)
class CheckedProgram:
    source: str
    source_sha256: str
    program: Program
    bounds: tuple[dict, ...]

    def artifact(self) -> dict:
        payload = {"format": IR_VERSION, "source": self.source,
                   "source_sha256": self.source_sha256, "ir": normalize(self.program),
                   "bounds": list(self.bounds)}
        return {**payload, "artifact_sha256": digest(payload)}


@deterministic
def compile_source(source: str) -> CheckedProgram:
    try:
        program = parse(source)
    except RecursionError as exc:
        raise Diagnostic("E020", "source complexity exceeds parser limit") from exc
    symbols = {}
    names = set()
    time = UNITS["s"][0]

    def fail(message, span=None):
        raise Diagnostic("E040", message, span)

    def add(name, unit, span):
        if name in names or name in ("true", "false", "and", "or", "not", "abs", "min", "max", "clamp"):
            fail(f"duplicate or reserved symbol {name}", span)
        if unit not in UNITS and unit != "bool":
            fail(f"unknown unit {unit}", span)
        names.add(name)
        symbols[name] = "bool" if unit == "bool" else UNITS[unit][0]

    def dimension(q, dim, span, positive=False, nonnegative=False):
        if q.dim != dim:
            fail("literal has wrong physical dimensions", span)
        if positive and q.value <= 0 or nonnegative and q.value < 0:
            fail("literal violates positivity requirement", span)

    dimension(program.tick, time, None, positive=True)
    if program.tick.value < UNITS["ms"][1] or program.tick.value > 60:
        fail("tick must be within [1 ms, 60 s]")
    if program.tick.value * 1000 != (program.tick.value * 1000).to_integral_value():
        fail("tick must be a whole number of milliseconds")
    for channel in program.channels:
        add(channel.name, channel.unit, channel.span)
        dimension(channel.fresh, time, channel.span, positive=True)
        if channel.unit == "bool" and channel.uncertainty is not None:
            fail("boolean channels do not accept numeric uncertainty", channel.span)
        if channel.unit != "bool":
            if channel.uncertainty is None:
                fail("numeric channels require an uncertainty ceiling", channel.span)
            dimension(channel.uncertainty, symbols[channel.name], channel.span, nonnegative=True)
    channel_names = {c.name for c in program.channels}
    for mesh in program.meshes:
        add(mesh.name, mesh.unit, mesh.span)
        if mesh.unit == "bool" or not 1 <= mesh.quorum <= len(mesh.members):
            fail("numeric mesh requires a valid positive quorum", mesh.span)
        if len(set(mesh.members)) != len(mesh.members):
            fail("mesh members must be distinct channels", mesh.span)
        for member in mesh.members:
            if member not in channel_names or symbols[member] != symbols[mesh.name]:
                fail(f"mesh member {member} is missing or has different dimensions", mesh.span)
        dimension(mesh.tolerance, symbols[mesh.name], mesh.span, nonnegative=True)
    ranges = {}
    for param in program.parameters:
        add(param.name, param.unit, param.span)
        if param.unit == "bool":
            fail("parameters must be numeric", param.span)
        for q in (param.initial, param.low, param.high, param.rate):
            dimension(q, symbols[param.name], param.span)
        if not param.low.value <= param.initial.value <= param.high.value or param.rate.value <= 0:
            fail("invalid parameter initial value, bounds or per-tick rate", param.span)
        ranges[param.name] = (param.low.value, param.high.value)
    for actuator in program.actuators:
        if actuator.name in names or actuator.unit not in UNITS:
            fail("actuator requires a unique name and numeric unit", actuator.span)
        names.add(actuator.name)
        dim = UNITS[actuator.unit][0]
        for q in (actuator.low, actuator.high, actuator.safe):
            dimension(q, dim, actuator.span)
        if not actuator.low.value <= actuator.safe.value <= actuator.high.value:
            fail("invalid actuator range or safe command", actuator.span)
        derivative = tuple(a - b for a, b in zip(dim, time))
        dimension(actuator.slew, derivative, actuator.span, positive=True)
    actuators = {a.name: a for a in program.actuators}
    params = {p.name: p for p in program.parameters}
    if len(set(program.capabilities)) != len(program.capabilities):
        fail("duplicate command capability")
    if any(c not in actuators for c in program.capabilities):
        fail("capability references unknown actuator")
    if not program.states or len(program.states) > 256:
        fail("system must have 1..256 states")
    states = {s.name: s for s in program.states}
    if len(states) != len(program.states) or any(s.name in names for s in program.states):
        fail("duplicate state or collision with value name")
    initial = [s for s in program.states if s.kind == "initial"]
    if len(initial) != 1:
        fail("exactly one initial state required")
    if program.fault not in states or states[program.fault].kind != "terminal":
        fail("fault handler must target a terminal state")
    bounds = []
    all_expressions = [e for _, e in program.invariants]
    for state in program.states:
        all_expressions.extend(state.requirements)
        all_expressions.extend(e for _, e in state.commands + state.adaptations)
        all_expressions.extend(t.condition for t in state.transitions if t.condition is not None)
    for expr in all_expressions:
        stack, count = [(expr, 1)], 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if depth > 64 or count > 256:
                fail("expression exceeds depth 64 or 256 nodes", expr.span)
            stack.extend((a, depth + 1) for a in node.args)
    for state in program.states:
        if state.kind == "terminal" and (state.commands or state.adaptations or state.transitions):
            fail("terminal states cannot command, adapt or transition", state.span)
        for expression in state.requirements:
            if type_of(expression, symbols) != "bool":
                fail("require expects bool", expression.span)
        for assignments, targets, is_command in ((state.commands, actuators, True), (state.adaptations, params, False)):
            if len({a[0] for a in assignments}) != len(assignments):
                fail("duplicate assignment in state", state.span)
            for target, expression in assignments:
                if target not in targets:
                    fail(f"unknown assignment target {target}", expression.span)
                if is_command and target not in program.capabilities:
                    fail(f"missing declared capability for {target}", expression.span)
                spec = targets[target]
                if type_of(expression, symbols) != UNITS[spec.unit][0]:
                    fail(f"assignment to {target} has wrong dimensions", expression.span)
                bound = interval(expression, ranges)
                proven = bound is not None and spec.low.value <= bound[0] <= bound[1] <= spec.high.value
                # A definitely out-of-range constant is a compile error, not a latent runtime fault.
                if bound is not None and bound[0] == bound[1] and not proven:
                    fail(f"constant assignment to {target} exceeds bounds", expression.span)
                bounds.append({"state": state.name, "target": target, "static_range_proven": proven,
                               "interval": None if bound is None else [str(x) for x in bound]})
        for transition in state.transitions:
            if transition.target not in states:
                fail(f"unknown transition target {transition.target}", transition.span)
            if transition.condition is not None and type_of(transition.condition, symbols) != "bool":
                fail("when expects bool", transition.span)
            if transition.after is not None:
                dimension(transition.after, time, transition.span, positive=True)
    if len({n for n, _ in program.invariants}) != len(program.invariants):
        fail("duplicate invariant name")
    for name, expression in program.invariants:
        if type_of(expression, symbols) != "bool":
            fail(f"invariant {name} expects bool", expression.span)
    reachable = {initial[0].name, program.fault}
    while True:
        expanded = reachable | {t.target for n in reachable for t in states[n].transitions}
        if expanded == reachable:
            break
        reachable = expanded
    if reachable != set(states):
        fail(f"unreachable states: {', '.join(sorted(set(states) - reachable))}")
    return CheckedProgram(source, source_digest(source), program, tuple(bounds))


def load_artifact(data: dict) -> CheckedProgram:
    if not isinstance(data, dict) or data.get("format") != IR_VERSION:
        raise EquilibriumError("unsupported IR format")
    if not isinstance(data.get("source"), str):
        raise EquilibriumError("IR missing source")
    checked = compile_source(data["source"])
    if checked.artifact() != data:
        raise EquilibriumError("IR does not match recompiled source and artifact digest")
    return checked
