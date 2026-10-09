"""Recursive descent declarations and precedence expressions."""
from .errors import Diagnostic, EquilibriumError
from .syntax import (Actuator, Channel, Expr, Mesh, Parameter, Program, State,
                     Token, Transition, lex)
from .units import UNITS, Quantity

PRECEDENCE = {"or": 1, "and": 2, "==": 3, "!=": 3, "<": 4, "<=": 4,
              ">": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6}


class Parser:
    def __init__(self, source: str):
        self.tokens, self.index, self.depth = lex(source), 0, 0

    @property
    def token(self) -> Token:
        return self.tokens[self.index]

    def take(self, text: str | None = None) -> Token:
        token = self.token
        if text is not None and token.text != text:
            raise Diagnostic("E010", f"expected {text!r}, found {token.text!r}", token.span)
        if token.text == "<eof>":
            raise Diagnostic("E010", "unexpected end of source", token.span)
        self.index += 1
        return token

    def accept(self, text: str) -> bool:
        if self.token.text == text:
            self.take()
            return True
        return False

    def name(self) -> Token:
        token = self.take()
        if not token.text.isidentifier():
            raise Diagnostic("E011", "expected identifier", token.span)
        return token

    def quantity(self) -> Quantity:
        negative = self.accept("-")
        token = self.take()
        if not token.text[0].isdigit():
            raise Diagnostic("E012", "expected numeric literal", token.span)
        unit = self.take().text if self.token.text in UNITS else "scalar"
        try:
            return Quantity.of(("-" if negative else "") + token.text, unit)
        except EquilibriumError as exc:
            raise Diagnostic("E012", str(exc), token.span) from exc

    def expr(self, minimum: int = 0) -> Expr:
        self.depth += 1
        if self.depth > 64:
            raise Diagnostic("E013", "expression nesting exceeds 64", self.token.span)
        token = self.token
        if token.text in ("-", "not"):
            self.take()
            result = Expr(token.text if token.text == "not" else "neg", (self.expr(7),), span=token.span)
        elif self.accept("("):
            result = self.expr()
            self.take(")")
        elif token.text[0].isdigit():
            result = Expr("literal", value=self.quantity(), span=token.span)
        elif token.text in ("true", "false"):
            self.take()
            result = Expr("literal", value=token.text == "true", span=token.span)
        else:
            name = self.name()
            if self.accept("("):
                args = []
                if self.token.text != ")":
                    args.append(self.expr())
                    while self.accept(","):
                        args.append(self.expr())
                self.take(")")
                result = Expr("call", tuple(args), name.text, name.span)
            else:
                result = Expr("name", value=name.text, span=name.span)
        while self.token.text in PRECEDENCE and PRECEDENCE[self.token.text] >= minimum:
            op = self.take()
            right = self.expr(PRECEDENCE[op.text] + 1)
            result = Expr(op.text, (result, right), span=op.span)
        self.depth -= 1
        return result

    def bounds(self) -> tuple[Quantity, Quantity]:
        self.take("[")
        low = self.quantity()
        self.take(",")
        high = self.quantity()
        self.take("]")
        return low, high

    def state(self) -> State:
        name = self.name()
        kind = self.take().text if self.token.text in ("initial", "terminal") else "normal"
        self.take("{")
        requirements, commands, adaptations, transitions = [], [], [], []
        while not self.accept("}"):
            token = self.take()
            if token.text == "require":
                requirements.append(self.expr())
            elif token.text in ("command", "adapt"):
                target = self.name().text
                self.take("=")
                (commands if token.text == "command" else adaptations).append((target, self.expr()))
            elif token.text in ("when", "after"):
                cond = self.expr() if token.text == "when" else None
                after = self.quantity() if token.text == "after" else None
                self.take("->")
                transitions.append(Transition(cond, after, self.name().text, token.span))
            else:
                raise Diagnostic("E014", f"unsupported state statement {token.text}", token.span)
            self.take(";")
        return State(name.text, kind, tuple(requirements), tuple(commands),
                     tuple(adaptations), tuple(transitions), name.span)

    def parse(self) -> Program:
        self.take("system")
        name = self.name().text
        self.take("{")
        channels, meshes, parameters, actuators, capabilities, states, invariants = [], [], [], [], [], [], []
        tick, fault = None, None
        while not self.accept("}"):
            token = self.take()
            if token.text == "state":
                states.append(self.state())
                continue
            if token.text == "tick":
                if tick is not None:
                    raise Diagnostic("E015", "duplicate tick", token.span)
                tick = self.quantity()
            elif token.text in ("sensor", "input"):
                n = self.name()
                self.take(":")
                unit = self.name().text
                self.take("fresh")
                fresh = self.quantity()
                uncertainty = self.quantity() if self.accept("uncertainty") else None
                channels.append(Channel(n.text, unit, fresh, uncertainty, n.span))
            elif token.text == "mesh":
                n = self.name()
                self.take(":")
                unit = self.name().text
                self.take("=")
                self.take("quorum")
                self.take("(")
                members = [self.name().text]
                while self.accept(","):
                    members.append(self.name().text)
                self.take(")")
                self.take("tolerance")
                tolerance = self.quantity()
                self.take("require")
                count = self.take()
                if not count.text.isdigit():
                    raise Diagnostic("E016", "quorum must be an integer", count.span)
                meshes.append(Mesh(n.text, unit, tuple(members), tolerance, int(count.text), n.span))
            elif token.text == "param":
                n = self.name()
                self.take(":")
                unit = self.name().text
                self.take("=")
                initial = self.quantity()
                self.take("within")
                low, high = self.bounds()
                self.take("rate")
                parameters.append(Parameter(n.text, unit, initial, low, high, self.quantity(), n.span))
            elif token.text == "actuator":
                n = self.name()
                self.take(":")
                unit = self.name().text
                self.take("range")
                low, high = self.bounds()
                self.take("safe")
                safe = self.quantity()
                self.take("slew")
                actuators.append(Actuator(n.text, unit, low, high, safe, self.quantity(), n.span))
            elif token.text == "capability":
                self.take("command")
                capabilities.append(self.name().text)
            elif token.text == "invariant":
                n = self.name().text
                self.take(":")
                invariants.append((n, self.expr()))
            elif token.text == "on":
                self.take("fault")
                self.take("->")
                if fault is not None:
                    raise Diagnostic("E015", "duplicate fault handler", token.span)
                fault = self.name().text
            else:
                raise Diagnostic("E017", f"unsupported declaration {token.text}", token.span)
            self.take(";")
        if self.token.text != "<eof>":
            raise Diagnostic("E018", "trailing source", self.token.span)
        if tick is None or fault is None:
            raise Diagnostic("E019", "system requires tick and on fault declarations")
        return Program(name, tick, tuple(channels), tuple(meshes), tuple(parameters),
                       tuple(actuators), tuple(capabilities), tuple(states), tuple(invariants), fault)


def parse(source: str) -> Program:
    return Parser(source).parse()
