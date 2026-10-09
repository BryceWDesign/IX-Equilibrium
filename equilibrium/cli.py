"""Dependency-free command-line toolchain."""
import argparse
import sys
from pathlib import Path

from . import __version__
from .codec import canonical, read_json, write_json
from .compiler import compile_source, load_artifact
from .errors import EquilibriumError
from .evidence import verify_export
from .report import write_report
from .simulation import campaign, explore, replay, simulate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="equilibrium", description="IX-Equilibrium checked coordination language")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "ast", "compile"):
        sub = commands.add_parser(name)
        sub.add_argument("source")
        if name == "compile":
            sub.add_argument("-o", "--output", required=True)
    for name in ("run", "campaign", "explore"):
        sub = commands.add_parser(name)
        sub.add_argument("source", help=".eq source or .eqir.json compiled artifact")
        sub.add_argument("--scenario" if name != "explore" else "--choices", required=True)
        sub.add_argument("-o", "--output", required=True)
        if name == "run":
            sub.add_argument("--database", default=":memory:", help="fresh SQLite journal path")
        if name == "explore":
            sub.add_argument("--depth", type=int, default=3)
    for name in ("replay", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("bundle")
        if name == "verify":
            sub.add_argument("--expected-head")
    args = parser.parse_args(argv)
    try:
        if args.command in ("verify", "replay"):
            data = read_json(args.bundle)
            evidence = data.get("evidence", data) if isinstance(data, dict) else data
            result = replay(data) if args.command == "replay" else verify_export(evidence, args.expected_head)
        else:
            if args.source.endswith(".eqir.json"):
                checked = load_artifact(read_json(args.source))
            else:
                # Byte-exact UTF-8 source identity, including Windows CRLF.
                checked = compile_source(Path(args.source).read_bytes().decode("utf-8"))
            if args.command == "check":
                result = {"checked": True, "source_sha256": checked.source_sha256,
                          "states": len(checked.program.states), "bounds": list(checked.bounds)}
            elif args.command == "ast":
                result = checked.program
            elif args.command == "compile":
                write_json(args.output, checked.artifact())
                result = {"compiled": args.output, "artifact_sha256": checked.artifact()["artifact_sha256"]}
            elif args.command == "run":
                result = simulate(checked, read_json(args.scenario), database=args.database)
                out = Path(args.output)
                out.mkdir(parents=True, exist_ok=True)
                write_json(out / "bundle.json", result)
                write_report(result, out / "report.html")
                result = {"output": str(out), **result["final"], "head": result["evidence"]["head"]}
            elif args.command == "campaign":
                result = campaign(checked, read_json(args.scenario))
                write_json(args.output, result)
            else:
                result = explore(checked, read_json(args.choices), args.depth)
                write_json(args.output, result)
        print(canonical(result))
        failed = (args.command == "campaign" and not result["passed"]
                  or args.command == "run" and result["state"] == checked.program.fault)
        return 2 if failed else 0
    except (EquilibriumError, OSError, UnicodeError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

