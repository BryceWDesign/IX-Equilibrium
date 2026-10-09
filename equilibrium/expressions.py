"""Type checking and interpretation of the finite expression language."""
from decimal import Decimal

from .errors import Diagnostic, EquilibriumError
from .determinism import deterministic
from .syntax import Expr
from .units import Dim, Quantity

Type = Dim | str
Value = Quantity | bool


def type_of(expr: Expr, symbols: dict[str, Type]) -> Type:
    def fail(message: str):
        raise Diagnostic("E030", message, expr.span)

    if expr.op == "literal":
        return "bool" if isinstance(expr.value, bool) else expr.value.dim
    if expr.op == "name":
        if expr.value not in symbols:
            fail(f"unknown symbol {expr.value}")
        return symbols[expr.value]
    types = [type_of(a, symbols) for a in expr.args]
    if expr.op in ("and", "or", "not"):
        if any(t != "bool" for t in types):
            fail("logical operands must be bool")
        return "bool"
    if expr.op in ("==", "!=", "<", "<=", ">", ">="):
        if types[0] != types[1] or (types[0] == "bool" and expr.op not in ("==", "!=")):
            fail("comparison requires matching numeric dimensions (or boolean equality)")
        return "bool"
    if expr.op == "call":
        arities = {"abs": 1, "min": 2, "max": 2, "clamp": 3}
        if expr.value not in arities or len(types) != arities.get(expr.value):
            fail(f"unsupported function or arity {expr.value}")
        if types[0] == "bool" or any(t != types[0] for t in types):
            fail("numeric function arguments must have matching dimensions")
        return types[0]
    if any(t == "bool" for t in types):
        fail("arithmetic requires numeric operands")
    if expr.op in ("+", "-", "neg"):
        if len(types) == 2 and types[0] != types[1]:
            fail("addition/subtraction requires matching dimensions")
        return types[0]
    if expr.op in ("*", "/"):
        sign = -1 if expr.op == "/" else 1
        return tuple(a + sign * b for a, b in zip(types[0], types[1]))
    fail(f"unsupported expression {expr.op}")


@deterministic
def evaluate(expr: Expr, values: dict[str, Value]) -> Value:
    if expr.op == "literal":
        return expr.value
    if expr.op == "name":
        if expr.value not in values:
            raise EquilibriumError(f"unavailable:{expr.value}")
        return values[expr.value]
    if expr.op == "and":
        return evaluate(expr.args[0], values) and evaluate(expr.args[1], values)
    if expr.op == "or":
        return evaluate(expr.args[0], values) or evaluate(expr.args[1], values)
    args = [evaluate(a, values) for a in expr.args]
    if expr.op == "not":
        return not args[0]
    if expr.op == "neg":
        return Quantity(-args[0].value, args[0].dim)
    if expr.op in ("==", "!=", "<", "<=", ">", ">="):
        a, b = [v.value if isinstance(v, Quantity) else v for v in args]
        return {"==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b,
                "<=": lambda: a <= b, ">": lambda: a > b, ">=": lambda: a >= b}[expr.op]()
    if expr.op in ("+", "-"):
        return args[0].add(args[1], expr.op == "-")
    if expr.op in ("*", "/"):
        return args[0].mul(args[1], expr.op == "/")
    if expr.op == "call":
        if expr.value == "abs":
            return Quantity(abs(args[0].value), args[0].dim)
        if expr.value in ("min", "max"):
            return (min if expr.value == "min" else max)(args, key=lambda v: v.value)
        if expr.value == "clamp":
            value, low, high = args
            if low.value > high.value:
                raise EquilibriumError("inverted clamp bounds")
            return Quantity(max(low.value, min(high.value, value.value)), value.dim)
    raise EquilibriumError(f"unsupported expression {expr.op}")


def references(expr: Expr) -> set[str]:
    names = {expr.value} if expr.op == "name" else set()
    for arg in expr.args:
        names.update(references(arg))
    return names


@deterministic
def interval(expr: Expr, ranges: dict[str, tuple[Decimal, Decimal]]) -> tuple[Decimal, Decimal] | None:
    """Sound scalar interval approximation; None means no static bound proven."""
    if expr.op == "literal":
        return (expr.value.value, expr.value.value) if isinstance(expr.value, Quantity) else None
    if expr.op == "name":
        return ranges.get(expr.value)
    if expr.op == "call" and expr.value == "clamp":
        low, high = interval(expr.args[1], ranges), interval(expr.args[2], ranges)
        if low and high and low[0] == low[1] and high[0] == high[1] and low[0] <= high[0]:
            return low[0], high[0]
        return None
    parts = [interval(a, ranges) for a in expr.args]
    if any(p is None for p in parts):
        return None
    if expr.op == "neg":
        return -parts[0][1], -parts[0][0]
    if expr.op == "+":
        return parts[0][0] + parts[1][0], parts[0][1] + parts[1][1]
    if expr.op == "-":
        return parts[0][0] - parts[1][1], parts[0][1] - parts[1][0]
    if expr.op in ("*", "/"):
        a, b = parts
        if expr.op == "/" and b[0] <= 0 <= b[1]:
            return None
        values = [x * y if expr.op == "*" else x / y for x in a for y in b]
        return min(values), max(values)
    if expr.op == "call":
        a = parts[0]
        if expr.value == "abs":
            return (Decimal(0) if a[0] <= 0 <= a[1] else min(abs(x) for x in a), max(abs(x) for x in a))
        if expr.value in ("min", "max"):
            fn = min if expr.value == "min" else max
            return fn(p[0] for p in parts), fn(p[1] for p in parts)
    return None

