"""One portable validation gate. Exit nonzero on any behavioral failure."""
import json
import platform
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from equilibrium.codec import read_json, write_json
from equilibrium.compiler import compile_source, load_artifact
from equilibrium.evidence import verify_export
from equilibrium.simulation import campaign, explore, replay, simulate


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="out/quality.json")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    tests = unittest.TextTestRunner(verbosity=1).run(suite)
    examples = []
    for path in sorted(ROOT.glob("examples/*.eq")):
        source = path.read_bytes().decode("utf-8")
        checked = compile_source(source)
        assert load_artifact(checked.artifact()) == checked
        bundle = simulate(checked, read_json(path.with_suffix(".scenario.json")))
        assert replay(bundle)["reproduced"]
        assert verify_export(bundle["evidence"], bundle["evidence"]["head"])["valid"]
        examples.append({"name": path.name, "source_sha256": checked.source_sha256,
                         "steps": len(bundle["steps"]), "adapter_calls": bundle["final"]["adapter_calls"],
                         "bundle_sha256": bundle["bundle_sha256"]})
    assist = compile_source((ROOT / "examples/assist.eq").read_bytes().decode("utf-8"))
    fault_result = campaign(assist, read_json(ROOT / "examples/assist.scenario.json"))
    enumeration = explore(assist, read_json(ROOT / "examples/assist.choices.json"), 4)
    result = {"passed": tests.wasSuccessful() and fault_result["passed"],
              "python": platform.python_version(), "platform": platform.platform(),
              "tests_run": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors),
              "examples": examples, "campaign": fault_result, "exploration": enumeration}
    write_json(args.output, result)
    print(json.dumps({k: result[k] for k in ["passed", "python", "tests_run", "failures", "errors"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

