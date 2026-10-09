"""Immutable source tree and a token lexer with source positions."""
import re
from dataclasses import dataclass

from .errors import Diagnostic, Span
from .units import Quantity


@dataclass(frozen=True)
class Token:
    text: str
    span: Span


def lex(source: str) -> tuple[Token, ...]:
    if len(source.encode("utf-8")) > 1_000_000:
        raise Diagnostic("E001", "source exceeds 1 MB")
    pattern = re.compile(r"//[^\n]*|\s+|(?:\d+(?:\.\d+)?)|[A-Za-z_][A-Za-z_0-9]*|->|<=|>=|==|!=|[{}()\[\]:;,=+*/<>-]")
    out, pos, line, column = [], 0, 1, 1
    while pos < len(source):
        match = pattern.match(source, pos)
        if match is None:
            raise Diagnostic("E002", f"unexpected character {source[pos]!r}", Span(line, column))
        text = match.group()
        if not text.isspace() and not text.startswith("//"):
            out.append(Token(text, Span(line, column)))
            if len(out) > 50000:
                raise Diagnostic("E003", "source exceeds 50000 tokens", Span(line, column))
        if "\n" in text:
            line += text.count("\n")
            column = len(text.rsplit("\n", 1)[-1]) + 1
        else:
            column += len(text)
        pos = match.end()
    out.append(Token("<eof>", Span(line, column)))
    return tuple(out)


@dataclass(frozen=True)
class Expr:
    op: str
    args: tuple["Expr", ...] = ()
    value: Quantity | bool | str | None = None
    span: Span | None = None


@dataclass(frozen=True)
class Channel:
    name: str
    unit: str
    fresh: Quantity
    uncertainty: Quantity | None
    span: Span


@dataclass(frozen=True)
class Mesh:
    name: str
    unit: str
    members: tuple[str, ...]
    tolerance: Quantity
    quorum: int
    span: Span


@dataclass(frozen=True)
class Parameter:
    name: str
    unit: str
    initial: Quantity
    low: Quantity
    high: Quantity
    rate: Quantity  # maximum change per tick
    span: Span


@dataclass(frozen=True)
class Actuator:
    name: str
    unit: str
    low: Quantity
    high: Quantity
    safe: Quantity
    slew: Quantity
    span: Span


@dataclass(frozen=True)
class Transition:
    condition: Expr | None
    after: Quantity | None
    target: str
    span: Span


@dataclass(frozen=True)
class State:
    name: str
    kind: str
    requirements: tuple[Expr, ...]
    commands: tuple[tuple[str, Expr], ...]
    adaptations: tuple[tuple[str, Expr], ...]
    transitions: tuple[Transition, ...]
    span: Span


@dataclass(frozen=True)
class Program:
    name: str
    tick: Quantity
    channels: tuple[Channel, ...]
    meshes: tuple[Mesh, ...]
    parameters: tuple[Parameter, ...]
    actuators: tuple[Actuator, ...]
    capabilities: tuple[str, ...]
    states: tuple[State, ...]
    invariants: tuple[tuple[str, Expr], ...]
    fault: str

