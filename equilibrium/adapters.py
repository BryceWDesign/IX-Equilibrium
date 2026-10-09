"""Trusted adapter protocol and a deterministic first-order virtual plant."""
from decimal import Decimal
from typing import Protocol

from .authority import Action
from .errors import BoundaryError
from .determinism import deterministic
from .syntax import Actuator
from .units import Quantity, fmt


class Adapter(Protocol):
    @deterministic
    def apply(self, action: Action) -> dict:
        """Host-enforced atomic batch or raise; partial physical effects may exist."""
        ...

    def stop(self, safe_outputs: dict) -> dict:
        """Independent best-effort stop, even when authorization/evidence is unavailable."""
        ...


class VirtualPlant:
    """Velocity actuators integrate position; other quantities remain setpoints.

    This is an exact discrete-time kinematic model, not robot dynamics or a
    stability proof. No force, contact, inertia or hardware physics is inferred.
    """
    def __init__(self, actuators: tuple[Actuator, ...], tick_s: Decimal):
        self.specs = {a.name: a for a in actuators}
        self.tick_s = tick_s
        self.outputs = {a.name: a.safe for a in actuators}
        self.positions = {a.name: Decimal(0) for a in actuators if a.unit == "mps"}
        self.calls = []
        self.stops = []
        self.fail_apply = False
        self.fail_stop = False

    @deterministic
    def apply(self, action: Action) -> dict:
        if self.fail_apply:
            raise BoundaryError("injected adapter failure")
        if set(action.outputs) != set(self.specs):
            raise BoundaryError("adapter batch scope mismatch")
        checked = {}
        for name, data in action.outputs.items():
            spec = self.specs[name]
            value = Quantity.of(data["value"], "scalar")
            value = Quantity(value.value, tuple(data["dimension"]))
            spec.low.same(value)
            if not spec.low.value <= value.value <= spec.high.value:
                raise BoundaryError("adapter range violation")
            checked[name] = value
        self.outputs = checked
        self.calls.append(action.sha256)
        for name in self.positions:
            self.positions[name] += self.outputs[name].value * self.tick_s
        return self.observe()

    def stop(self, safe_outputs: dict) -> dict:
        self.stops.append(safe_outputs)
        if self.fail_stop:
            raise BoundaryError("injected stop failure")
        self.outputs = {a.name: a.safe for a in self.specs.values()}
        return self.observe()

    def observe(self) -> dict:
        return {"setpoints": {n: q.payload() for n, q in self.outputs.items()},
                "positions_m": {n: fmt(p) for n, p in self.positions.items()}}

