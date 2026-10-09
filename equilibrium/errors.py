"""Source diagnostics and controlled boundary failures."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    line: int
    column: int


class EquilibriumError(ValueError):
    pass


class Diagnostic(EquilibriumError):
    def __init__(self, code: str, message: str, span: Span | None = None):
        self.code, self.message, self.span = code, message, span
        prefix = f"{span.line}:{span.column}: " if span else ""
        super().__init__(f"{prefix}{code}: {message}")


class BoundaryError(EquilibriumError):
    pass

