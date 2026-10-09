"""Conservative interval evaluation for uncertainty-bearing sensor predicates."""
from decimal import Decimal

from .errors import EquilibriumError
from .expressions import evaluate, interval
from .syntax import Expr
from .units import Quantity


def predicate(expr: Expr, values: dict, ranges: dict) -> bool:
    if expr.op in ("and", "or"):
        left = predicate(expr.args[0], values, ranges)
        if expr.op == "and":
            return left and predicate(expr.args[1], values, ranges)
        return left or predicate(expr.args[1], values, ranges)
    if expr.op == "not":
        return not predicate(expr.args[0], values, ranges)
    if expr.op in ("<", "<=", ">", ">=", "==", "!="):
        # Evaluate first to detect missing symbols, invalid clamp and division.
        evaluate(expr, values)
        if isinstance(evaluate(expr.args[0], values), bool):
            return evaluate(expr, values)
        a, b = interval(expr.args[0], ranges), interval(expr.args[1], ranges)
        if a is None or b is None:
            raise EquilibriumError("uncertainty_unbounded")
        if expr.op == "<":
            certain_true, certain_false = a[1] < b[0], a[0] >= b[1]
        elif expr.op == "<=":
            certain_true, certain_false = a[1] <= b[0], a[0] > b[1]
        elif expr.op == ">":
            certain_true, certain_false = a[0] > b[1], a[1] <= b[0]
        elif expr.op == ">=":
            certain_true, certain_false = a[0] >= b[1], a[1] < b[0]
        else:
            equal = a[0] == a[1] == b[0] == b[1]
            disjoint = a[1] < b[0] or a[0] > b[1]
            certain_true, certain_false = (equal, disjoint) if expr.op == "==" else (disjoint, equal)
        if certain_true:
            return True
        if certain_false:
            return False
        raise EquilibriumError("uncertain_predicate")
    result = evaluate(expr, values)
    if type(result) is not bool:
        raise EquilibriumError("predicate_not_boolean")
    return result


def exact_ranges(values: dict) -> dict[str, tuple[Decimal, Decimal]]:
    return {n: (v.value, v.value) for n, v in values.items() if isinstance(v, Quantity)}

