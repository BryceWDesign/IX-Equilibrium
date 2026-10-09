# Observed validation, IX-Equilibrium 0.1.0

Validated on Linux x86-64, Python 3.12.14. These are local observed results,
not remote CI or hardware validation. Machine-readable details are in
`evidence/quality.json`; individual scenario bundles and reports are included.

| Check | Observed result |
|---|---|
| Behavioral unit/integration tests | 156 passed, zero failures/errors |
| Assistance fault campaign | 13/13 cases passed |
| Finite synthetic exploration | 81 four-event sequences enumerated |
| Checked-artifact reload and source revalidation | passed for all 3 examples |
| Complete deterministic scenario replay | passed for all 3 examples |
| Independent integrity verification with retained heads | passed |
| Python bytecode compilation | passed |

Examples:

| Program | Recorded steps | Active adapter calls | Final virtual result |
|---|---:|---:|---|
| AdaptiveAssist | 12 | 8 | idle; arm position 0.014 m; setpoint 0 |
| ThermalMesh | 11 | 10 | finished, terminal; heater setpoint 0 |
| SharedControl | 12 | 12 | motion; left/right positions 0.0084 m each; setpoints 0.08 m/s |

Thermal simulation stops at its terminal state; the twelfth source scenario
event is deliberately not executed. Shared control ends a finite experiment
while the virtual state is running; it does not imply any real continuing motion.

Boundary evidence includes:

- real loopback UDP acceptance, wrong key/source/session/producer/scope,
  oversized and malformed packets, replay and timeout;
- independent SQLite connection visibility before a real file write;
- a full SDK demonstration that writes a command file only with admitted review;
- two independent SQLite writers producing one validated 40-record chain;
- eight concurrent review consumers, exactly one successful reservation;
- source/IR/plan/token tampering, changed snapshots, source revision binding,
  revocation before and after evidence commit, and pinned-head truncation detection;
- sensor freshness boundaries, uncertainty crossing, mesh dissent, slew limits,
  bounded adaptation, prospective invariants, missed logical ticks and stop failure.

In the post-dispatch evidence-failure campaign, **one** adapter effect occurs
and remains unresolved in the journal. That is the expected result: recording
failure cannot roll back an effect. An adapter failure also leaves unresolved
authorization because a real adapter could have performed partial effects.

The current journal validates the full history per append. No production
throughput, long-history scaling or high-availability claim is made.

Not run: Windows, Python 3.11 or 3.13 locally, remote GitHub Actions, ROS 2,
robot hardware, medical devices, wall-clock deadline certification, independent
security review, or physical stability/safety validation. Ruff/mypy are not
installed in the creation environment; no claim that they ran is made.

Reproduce the observed software gate:

```powershell
python scripts/quality_gate.py --output out/quality.json
```

The release package also includes a wheel and source distribution. Their
build/import smoke verification is recorded separately in
`evidence/package-validation.json` after package creation.

