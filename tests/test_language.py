import unittest
from decimal import Decimal, localcontext

from equilibrium.codec import loads
from equilibrium.compiler import compile_source, load_artifact
from equilibrium.errors import Diagnostic, EquilibriumError
from equilibrium.expressions import evaluate
from equilibrium.parser import Parser
from equilibrium.syntax import lex
from equilibrium.units import Quantity
from tests.support import SOURCE, ROOT, checked


class LanguageTests(unittest.TestCase):
    def bad(self, old, new):
        with self.assertRaises(EquilibriumError):
            compile_source(SOURCE.replace(old, new))

    def test_examples_compile_and_have_proven_bounds(self):
        for path in ROOT.glob("examples/*.eq"):
            with self.subTest(path=path):
                c = compile_source(path.read_text())
                self.assertTrue(c.bounds)
                self.assertTrue(all(b["static_range_proven"] for b in c.bounds))

    def test_source_positions(self):
        with self.assertRaises(Diagnostic) as ctx:
            compile_source("system X {\n @ }")
        self.assertEqual((ctx.exception.span.line, ctx.exception.span.column), (2, 2))

    def test_source_size_limit(self):
        with self.assertRaises(Diagnostic):
            lex(" " * 1_000_001)

    def test_nesting_limit(self):
        self.bad("gain * 0.2 mps", "(" * 70 + "0.1 mps" + ")" * 70)

    def test_long_binary_expression_fails_cleanly(self):
        self.bad("gain * 0.2 mps", " + ".join(["0.001 mps"] * 100))

    def test_numeric_domain_rejects_excessive_precision_and_tiny_values(self):
        for value in ["1e-31", "0.12345678901234567890123456789"]:
            with self.subTest(value=value), self.assertRaises(EquilibriumError):
                Quantity.of(value)

    def test_missing_tick(self):
        self.bad("tick 20 ms;", "")

    def test_fractional_millisecond_tick(self):
        self.bad("tick 20 ms", "tick 1.5 ms")

    def test_wrong_tick_dimension(self):
        self.bad("tick 20 ms", "tick 20 m")

    def test_duplicate_tick(self):
        self.bad("tick 20 ms;", "tick 20 ms; tick 30 ms;")

    def test_duplicate_sensor(self):
        self.bad("input intent : bool fresh 100 ms;", "input vision : bool fresh 100 ms;")

    def test_unknown_units(self):
        self.bad("sensor load : N", "sensor load : lbs")

    def test_missing_numeric_uncertainty(self):
        self.bad("fresh 60 ms uncertainty 0.1 N", "fresh 60 ms")

    def test_negative_uncertainty(self):
        self.bad("uncertainty 0.1 N", "uncertainty -0.1 N")

    def test_bool_uncertainty(self):
        self.bad("input intent : bool fresh 100 ms", "input intent : bool fresh 100 ms uncertainty 1")

    def test_zero_freshness(self):
        self.bad("fresh 60 ms", "fresh 0 ms")

    def test_mesh_duplicate_member(self):
        self.bad("vision, proximity, tactile", "vision, vision, tactile")

    def test_mesh_unknown_member(self):
        self.bad("vision, proximity, tactile", "vision, proximity, unknown")

    def test_mesh_wrong_dimension(self):
        self.bad("vision, proximity, tactile", "vision, proximity, load")

    def test_mesh_quorum_exceeds_members(self):
        self.bad("require 2;", "require 4;")

    def test_mesh_negative_tolerance(self):
        self.bad("tolerance 0.08 m", "tolerance -0.08 m")

    def test_parameter_initial_outside_bounds(self):
        self.bad("= 0.5 within", "= 1.5 within")

    def test_parameter_zero_rate(self):
        self.bad("rate 0.1;", "rate 0;")

    def test_parameter_wrong_dimension(self):
        self.bad("rate 0.1;", "rate 0.1 N;")

    def test_actuator_inverted_range(self):
        self.bad("[-0.2 mps, 0.2 mps]", "[0.2 mps, -0.2 mps]")

    def test_actuator_safe_outside_range(self):
        self.bad("safe 0 mps", "safe 1 mps")

    def test_actuator_slew_dimension(self):
        self.bad("slew 1 mps2", "slew 1 mps")

    def test_missing_declared_capability(self):
        self.bad("capability command arm;", "")

    def test_unknown_capability(self):
        self.bad("capability command arm;", "capability command unknown;")

    def test_duplicate_capability(self):
        self.bad("capability command arm;", "capability command arm; capability command arm;")

    def test_command_dimension(self):
        self.bad("gain * 0.2 mps", "gain * 0.2 N")

    def test_command_constant_outside_range(self):
        self.bad("gain * 0.2 mps", "0.3 mps")

    def test_require_not_bool(self):
        self.bad("require clearance > 0.2 m", "require clearance")

    def test_add_wrong_dimensions(self):
        self.bad("gain * 0.2 mps", "0.1 mps + 2 N")

    def test_logical_numeric(self):
        self.bad("when intent -> moving", "when intent and gain -> moving")

    def test_boolean_order_comparison(self):
        self.bad("when intent -> moving", "when intent > false -> moving")

    def test_unknown_function(self):
        self.bad("gain * 0.2 mps", "eval(gain)")

    def test_function_wrong_arity(self):
        self.bad("gain * 0.2 mps", "clamp(0.1 mps, 0 mps)")

    def test_unknown_value(self):
        self.bad("gain * 0.2 mps", "missing * 0.2 mps")

    def test_duplicate_command(self):
        self.bad("command arm = gain * 0.2 mps;", "command arm = gain * 0.2 mps; command arm = 0 mps;")

    def test_unknown_transition(self):
        self.bad("-> moving;", "-> nowhere;")

    def test_terminal_effect_rejected(self):
        self.bad("state complete terminal { }", "state complete terminal { command arm = 0 mps; }")

    def test_nonterminal_fault_handler(self):
        self.bad("on fault -> stopped", "on fault -> moving")

    def test_unreachable_state(self):
        self.bad("on fault -> stopped;", "state unused { } on fault -> stopped;")

    def test_multiple_initial_states(self):
        self.bad("state moving {", "state moving initial {")

    def test_duplicate_invariant(self):
        self.bad("invariant contact_load : load < 5 N;", "invariant contact_load : load < 5 N; invariant contact_load : true;")

    def test_trailing_source_rejected(self):
        with self.assertRaises(EquilibriumError):
            compile_source(SOURCE + "garbage")

    def test_ir_roundtrip(self):
        c = checked()
        self.assertEqual(load_artifact(c.artifact()), c)

    def test_ir_source_tamper(self):
        data = checked().artifact()
        data["source"] += "// changed"
        with self.assertRaises(EquilibriumError):
            load_artifact(data)

    def test_ir_ast_tamper(self):
        data = checked().artifact()
        data["ir"]["name"] = "Other"
        with self.assertRaises(EquilibriumError):
            load_artifact(data)

    def test_byte_exact_crlf_digest(self):
        self.assertNotEqual(checked().source_sha256, checked(SOURCE.replace("\n", "\r\n")).source_sha256)

    def test_decimal_context_isolation(self):
        with localcontext() as ctx:
            ctx.prec = 3
            c = checked()
            self.assertEqual(c, checked())
            self.assertEqual(Quantity.of("0.123456789", "cm").value, Decimal("0.00123456789"))

    def test_unit_conversion(self):
        self.assertEqual(Quantity.of("100", "cm"), Quantity.of("1", "m"))

    def test_expression_precedence(self):
        expr = Parser("2 + 3 * 4").expr()
        self.assertEqual(evaluate(expr, {}).value, 14)

    def test_parentheses(self):
        self.assertEqual(evaluate(Parser("(2 + 3) * 4").expr(), {}).value, 20)

    def test_division_by_zero(self):
        with self.assertRaises(EquilibriumError):
            evaluate(Parser("1 / 0").expr(), {})

    def test_inverted_clamp(self):
        with self.assertRaises(EquilibriumError):
            evaluate(Parser("clamp(1, 2, 0)").expr(), {})

    def test_json_duplicate_keys(self):
        with self.assertRaises(EquilibriumError):
            loads('{"x":1,"x":2}')

    def test_json_float_and_nonfinite_rejected(self):
        for value in ["0.5", "NaN", "Infinity"]:
            with self.subTest(value=value), self.assertRaises(EquilibriumError):
                loads('{"x":' + value + '}')

    def test_numeric_bool_float_nonfinite_rejected(self):
        for value in [True, 0.2, "NaN", "Infinity", "1e31"]:
            with self.subTest(value=value), self.assertRaises(EquilibriumError):
                Quantity.of(value)


if __name__ == "__main__":
    unittest.main()
