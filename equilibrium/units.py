"""Exact decimal quantities with dimensional arithmetic, no Python eval."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from .errors import EquilibriumError
from .determinism import deterministic

Dim = tuple[int, int, int, int]  # length, mass, time, temperature
ZERO: Dim = (0, 0, 0, 0)
UNITS: dict[str, tuple[Dim, Decimal]] = {
    "scalar": (ZERO, Decimal(1)),
    "m": ((1, 0, 0, 0), Decimal(1)),
    "cm": ((1, 0, 0, 0), Decimal("0.01")),
    "mm": ((1, 0, 0, 0), Decimal("0.001")),
    "s": ((0, 0, 1, 0), Decimal(1)),
    "ms": ((0, 0, 1, 0), Decimal("0.001")),
    "kg": ((0, 1, 0, 0), Decimal(1)),
    "N": ((1, 1, -2, 0), Decimal(1)),
    "Pa": ((-1, 1, -2, 0), Decimal(1)),
    "kPa": ((-1, 1, -2, 0), Decimal(1000)),
    "mps": ((1, 0, -1, 0), Decimal(1)),
    "mps2": ((1, 0, -2, 0), Decimal(1)),
    "Hz": ((0, 0, -1, 0), Decimal(1)),
    "K": ((0, 0, 0, 1), Decimal(1)),
    "rad": (ZERO, Decimal(1)),
}


def decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise EquilibriumError("numbers must be integers or decimal strings, never bool/float")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise EquilibriumError("invalid decimal") from exc
    if not result.is_finite() or result.copy_abs() > Decimal("1e30"):
        raise EquilibriumError("nonfinite or excessive numeric magnitude")
    if result != 0 and result.copy_abs() < Decimal("1e-30") or len(result.as_tuple().digits) > 28:
        raise EquilibriumError("number exceeds 28 significant digits or minimum nonzero magnitude 1e-30")
    return result


@deterministic
def fmt(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    dim: Dim = ZERO

    def __post_init__(self):
        decimal(self.value)

    @classmethod
    @deterministic
    def of(cls, value: object, unit: str = "scalar") -> "Quantity":
        if unit not in UNITS:
            raise EquilibriumError(f"unknown unit {unit}")
        dim, scale = UNITS[unit]
        return cls(decimal(value) * scale, dim)

    def same(self, other: "Quantity") -> None:
        if self.dim != other.dim:
            raise EquilibriumError("incompatible physical dimensions")

    @deterministic
    def add(self, other: "Quantity", subtract: bool = False) -> "Quantity":
        self.same(other)
        return Quantity(self.value + (-other.value if subtract else other.value), self.dim)

    @deterministic
    def mul(self, other: "Quantity", divide: bool = False) -> "Quantity":
        sign = -1 if divide else 1
        dim = tuple(a + sign * b for a, b in zip(self.dim, other.dim))
        with localcontext() as ctx:
            ctx.prec = 28
            if divide and other.value == 0:
                raise EquilibriumError("division by zero")
            value = self.value / other.value if divide else self.value * other.value
        return Quantity(value, dim)

    def payload(self) -> dict:
        return {"value": fmt(self.value), "dimension": list(self.dim)}

