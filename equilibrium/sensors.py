"""Freshness, anti-replay, bounded uncertainty and conservative mesh fusion."""
from dataclasses import dataclass
from decimal import Decimal

from .errors import EquilibriumError
from .determinism import deterministic
from .syntax import Channel, Mesh
from .units import Quantity


@dataclass(frozen=True)
class Reading:
    value: Quantity | bool
    uncertainty: Decimal
    at_ms: int
    sequence: int


class Sensors:
    def __init__(self, channels: tuple[Channel, ...], meshes: tuple[Mesh, ...]):
        self.channels = {c.name: c for c in channels}
        self.meshes = meshes
        self.readings: dict[str, Reading] = {}
        self.sequences: dict[str, int] = {}
        self.invalid: dict[str, str] = {}

    @deterministic
    def ingest(self, data: dict, now_ms: int) -> None:
        if not isinstance(data, dict) or set(data) != {"channel", "value", "unit", "at_ms", "sequence", "uncertainty"}:
            if isinstance(data, dict) and isinstance(data.get("channel"), str) and data["channel"] in self.channels:
                self.invalid[data["channel"]] = "sample schema mismatch"
            raise EquilibriumError("sample schema mismatch")
        name = data["channel"]
        if not isinstance(name, str) or name not in self.channels:
            raise EquilibriumError("unknown sample channel")
        spec = self.channels[name]
        try:
            if type(data["at_ms"]) is not int or type(data["sequence"]) is not int:
                raise EquilibriumError("sample time and sequence must be integers")
            if data["at_ms"] < 0 or data["at_ms"] > now_ms:
                raise EquilibriumError("sample timestamp is negative or in the future")
            if data["sequence"] <= self.sequences.get(name, -1):
                raise EquilibriumError("sample sequence replay")
            if name in self.readings and data["at_ms"] < self.readings[name].at_ms:
                raise EquilibriumError("sample timestamp regression")
            if spec.unit == "bool":
                if data["unit"] != "bool" or type(data["value"]) is not bool or data["uncertainty"] != "0":
                    raise EquilibriumError("invalid bool sample")
                value, uncertainty = data["value"], Decimal(0)
            else:
                value = Quantity.of(data["value"], data["unit"])
                bound = Quantity.of(data["uncertainty"], data["unit"])
                if value.dim != spec.uncertainty.dim or bound.dim != spec.uncertainty.dim:
                    raise EquilibriumError("sample unit mismatch")
                if not 0 <= bound.value <= spec.uncertainty.value:
                    raise EquilibriumError("sample uncertainty exceeds ceiling")
                uncertainty = bound.value
            self.readings[name] = Reading(value, uncertainty, data["at_ms"], data["sequence"])
            self.sequences[name] = data["sequence"]
            self.invalid.pop(name, None)
        except (EquilibriumError, TypeError, KeyError) as exc:
            self.invalid[name] = str(exc)
            raise EquilibriumError(f"invalid sample {name}: {exc}") from exc

    @deterministic
    def snapshot(self, now_ms: int) -> tuple[dict, dict, dict]:
        values, intervals, diagnostics = {}, {}, {}
        for name, spec in self.channels.items():
            reading = self.readings.get(name)
            if name in self.invalid:
                diagnostics[name] = self.invalid[name]
            elif reading is None:
                diagnostics[name] = "missing"
            elif Decimal(now_ms - reading.at_ms) / 1000 > spec.fresh.value:
                diagnostics[name] = "stale"
            else:
                values[name] = reading.value
                if isinstance(reading.value, Quantity):
                    intervals[name] = (reading.value.value - reading.uncertainty,
                                       reading.value.value + reading.uncertainty)
        for mesh in self.meshes:
            members = [n for n in mesh.members if n in values]
            if len(members) < mesh.quorum:
                diagnostics[mesh.name] = "quorum_missing"
                continue
            low = min(intervals[n][0] for n in members)
            high = max(intervals[n][1] for n in members)
            # All available valid members must agree; no silent majority outlier discard.
            if high - low > mesh.tolerance.value:
                diagnostics[mesh.name] = "mesh_disagreement"
                continue
            ordered = sorted(values[n].value for n in members)
            mid = len(ordered) // 2
            median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
            values[mesh.name] = Quantity(median, mesh.tolerance.dim)
            intervals[mesh.name] = (low, high)
        return values, intervals, diagnostics
