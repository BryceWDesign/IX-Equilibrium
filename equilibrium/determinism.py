"""Numeric context isolated from application-wide Decimal settings."""
from decimal import Context, ROUND_HALF_EVEN, localcontext
from functools import wraps

CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999, Emax=999)


def deterministic(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with localcontext(CONTEXT):
            return function(*args, **kwargs)
    return wrapped
