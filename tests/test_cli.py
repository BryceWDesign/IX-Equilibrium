import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from equilibrium.codec import read_json
from equilibrium.codec import write_json
from equilibrium.report import write_report
from equilibrium.simulation import simulate
from tests.support import ROOT, checked, scenario


class CLITests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "equilibrium", *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True)

    def test_version(self):
        self.assertEqual(self.cli("--version").stdout.strip(), "0.1.0")

    def test_malformed_verify_and_replay_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for command, data in [("verify", []), ("replay", {"format": "equilibrium.simulation/1", "source": 42, "scenario": {}})]:
                write_json(path, data)
                result = self.cli(command, path)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_check(self):
        p = self.cli("check", "examples/assist.eq")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"checked":true', p.stdout)

    def test_compile_run_replay_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            ir = Path(tmp) / "assist.eqir.json"
            output = Path(tmp) / "run"
            commands = [("compile", "examples/assist.eq", "-o", ir),
                        ("run", ir, "--scenario", "examples/assist.scenario.json", "-o", output),
                        ("replay", output / "bundle.json"),
                        ("verify", output / "bundle.json")]
            for cmd in commands:
                with self.subTest(command=cmd):
                    p = self.cli(*cmd)
                    self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue((output / "report.html").exists())
            head = read_json(output / "bundle.json")["evidence"]["head"]
            self.assertEqual(self.cli("verify", output / "bundle.json", "--expected-head", head).returncode, 0)
            self.assertEqual(self.cli("verify", output / "bundle.json", "--expected-head", "f" * 64).returncode, 2)

    def test_campaign_and_explore(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cmd, flag, file in [("campaign", "--scenario", "examples/assist.scenario.json"),
                                    ("explore", "--choices", "examples/assist.choices.json")]:
                p = self.cli(cmd, "examples/assist.eq", flag, file, "-o", Path(tmp) / (cmd + ".json"))
                self.assertEqual(p.returncode, 0, p.stderr)

    def test_invalid_source_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.eq"
            p.write_text("system nope {}")
            result = self.cli("check", p)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_runtime_fault_exit_status_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = scenario()
            s["events"][2]["simulation_review"] = False
            path = Path(tmp) / "denied.json"
            write_json(path, s)
            out = Path(tmp) / "out"
            result = self.cli("run", "examples/assist.eq", "--scenario", path, "-o", out)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertTrue((out / "bundle.json").exists())

    def test_ast_contains_real_source_tree(self):
        p = self.cli("ast", "examples/assist.eq")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"name":"AdaptiveAssist"', p.stdout)

    def test_report_escapes_untrusted_names(self):
        s = scenario()
        s["name"] = '<script>alert("x")</script>'
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "report.html"
            write_report(simulate(checked(), s), p)
            html = p.read_text()
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("Content-Security-Policy", html)

    def test_nonempty_simulation_database_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "journal.sqlite"
            out = Path(tmp) / "out"
            command = ("run", "examples/assist.eq", "--scenario", "examples/assist.scenario.json", "--database", p, "-o", out)
            self.assertEqual(self.cli(*command).returncode, 0)
            result = self.cli(*command)
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be empty", result.stderr)

    def test_live_host_demo_admits_and_denies_real_file_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            for deny in (False, True):
                out = Path(tmp) / ("denied" if deny else "allowed")
                command = [sys.executable, str(ROOT / "examples/host_demo.py"), "--out", str(out)]
                if deny:
                    command.append("--deny-review")
                result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((out / "command.json").exists(), not deny)
                self.assertTrue((out / "stop.json").exists())


if __name__ == "__main__":
    unittest.main()
