# IX-Equilibrium

**Typed sensing. Bounded actions. Independent authority. Recorded outcomes.**

Equilibrium is a new programming language for supervisory human, AI, sensor
and actuator coordination. Version **0.1.0** implements a checked language,
deterministic runtime, simulator and trusted-host integration SDK.

A program can request physical setpoints only when dimensional checks, sensor
validity, state requirements, actuator envelopes and independent host authority
agree. Operator intent is a request; source capabilities do not grant permission.

Copyright 2026 Bryce Lovell. **Apache License 2.0**, including commercial use
subject to the license. No runtime dependencies. Python 3.11 or later.

## Start here

Extract the release and open PowerShell in this folder:

```powershell
python -m unittest discover
python -m equilibrium check examples/assist.eq
python -m equilibrium run examples/assist.eq --scenario examples/assist.scenario.json -o out/assist
Start-Process .\out\assist\report.html
```

No installation is needed for these commands. Optional installation:

```powershell
python -m pip install --no-deps .
equilibrium --version
```

Read [the programming tutorial](docs/TUTORIAL.md),
[the language reference](docs/LANGUAGE.md), and
[Windows/GitHub handoff](HANDOFF.md).

## Actual language source

```text
system SharedAssist {
    tick 20 ms;
    sensor distance : m fresh 100 ms uncertainty 0.01 m;
    input intent : bool fresh 100 ms;
    actuator arm : mps range [-0.2 mps, 0.2 mps] safe 0 mps slew 1 mps2;
    capability command arm;

    state idle initial { when intent -> moving; }
    state moving {
        require distance > 0.2 m;
        command arm = 0.1 mps;
        when not intent -> idle;
    }
    state stopped terminal { }
    on fault -> stopped;
}
```

This syntax is implemented. `examples/assist.eq` extends it with a three-channel
mesh, a load invariant, bounded adaptive gain and a completion deadline.
Other complete examples cover a thermal sensor mesh and a two-actuator batch.

## Implemented toolchain

| Capability | What it actually does |
|---|---|
| Parser and diagnostics | lexes source into immutable AST with line/column errors |
| Compiler/checker | checks dimensions, declarations, capabilities, bounds and state reachability |
| Checked IR | serializes exact source, checked tree, bound summaries and hashes; reload rechecks everything |
| Sensors and mesh | enforces freshness, sequence, units and uncertainty; dissent vetoes numeric quorum |
| Conservative predicates | uses uncertainty intervals; overlapping thresholds fault the step |
| Bounded adaptation | adjusts declared parameters within bounds and per-tick limits, preserving invariants |
| Actuator mediation | enforces range/slew; batches exact outputs behind a trusted host boundary |
| External authority | HMAC-authenticated grants and exact-action, expiring, single-use reviews |
| Pre-dispatch journal | commits authorization in SQLite before an active adapter call |
| Evidence verifier | checks chain/order/action linkage, unresolved outcomes and optional retained head |
| Simulation and replay | runs finite scenarios and reproduces complete recorded bundles |
| Fault campaigns | exercises authority, journal, adapter and sensor failure paths |
| Finite exploration | enumerates bounded input choices and records counterexamples |
| Host SDK and real I/O | authenticated scoped UDP sensor bridge and a witnessed file-effect example |
| Offline report | displays decisions and evidence in a portable HTML file |

Compilation targets checked intermediate representation interpreted by Python;
it does not emit native machine code. Simulator authority/reviews are synthetic.
The real I/O example writes a local command file, not a robot command.

## Commands

```powershell
python -m equilibrium ast examples/assist.eq
python -m equilibrium compile examples/assist.eq -o out/assist.eqir.json
python -m equilibrium run out/assist.eqir.json --scenario examples/assist.scenario.json -o out/compiled
python -m equilibrium replay out/compiled/bundle.json
python -m equilibrium verify out/compiled/bundle.json
python -m equilibrium campaign examples/assist.eq --scenario examples/assist.scenario.json -o out/campaign.json
python -m equilibrium explore examples/assist.eq --choices examples/assist.choices.json --depth 4 -o out/exploration.json
python examples/host_demo.py --out out/host-allowed
python examples/host_demo.py --deny-review --out out/host-denied
python scripts/quality_gate.py --output out/quality.json
```

`run` creates `bundle.json` and `report.html`. It returns status 2 on a runtime
fault while preserving the evidence. Check/compile/replay/verify return status 2
on rejected input; campaign returns status 2 if a fault case fails its expectation.
Finite exploration reports counterexamples as data and returns status 0 on
successful enumeration. Use a fresh output directory for each host demonstration
and a fresh SQLite path when requesting persistent simulation evidence.

## Observed validation

**156 tests passed locally** on Linux, Python 3.12.14. The included assistance
campaign passes **13 injected-fault cases**. All three complete examples replay
exactly; the included exploration enumerates **81 input sequences**.

A test opens an independent SQLite connection to confirm authorization is
committed before a real file write. Missing grant/review or pre-dispatch evidence
failure prevents active dispatch. Post-dispatch evidence failure records an
unresolved effect and requests a stop; it does not claim rollback.

See [validation report](VALIDATION_REPORT.md),
[machine-readable claims](docs/CLAIMS.json), and the `evidence/` directory.
The GitHub workflow covers Windows/Ubuntu and Python 3.11/3.12/3.13; its remote
results are not known until this release is pushed and those jobs run.

## Engineering boundary

This release is executable research supervisory software. It has no validated
robot hardware adapter, ROS 2 integration, native/Rust backend, coordinate-frame
types, hard real-time guarantee, certified safety controller, EEG decoder or AGI.

The integrating host owns device bindings, authenticated human workflow,
authority keys, trusted clocks, independent watchdogs and hardware limits. A
source-declared `safe` setpoint is a requested fallback, not a physical guarantee.
A successful adapter stop return is not independently measured stopping.

The exported evidence chain is unsigned; retain an independent original head
to detect replacement/truncation. HMAC authority is not a personal public-key
signature. Review reservation and revocation are process-local. Journal append
replays full history and is not validated for high-rate operation. The virtual
plant is kinematic; finite exploration is not a general physical safety proof.

Read [threat model](docs/THREAT_MODEL.md) and [host integration](docs/SDK.md)
before adapting it to consequential devices.

## Donor provenance

The six supplied projects informed different architecture boundaries:
IX/Decriel for contracts and authority; HapticSight/SynapDrive for embodied
constraints and uncertain inputs; BlackFox/Sally for pre-dispatch evidence and
proposal gating. **No donor implementation source was copied or linked.**
BlackFox and Sally retain their existing evaluation licenses. Equilibrium's new
implementation is Apache 2.0. See [donor audit](docs/DONOR_AUDIT.md) and
[design/extension boundaries](docs/DESIGN.md).

Author: **Bryce Lovell**, [BryceWDesign](https://github.com/BryceWDesign).
