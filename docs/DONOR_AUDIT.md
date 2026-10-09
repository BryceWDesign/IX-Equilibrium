# Donor audit and reuse decision

The six user-supplied ZIP archives are preserved unchanged. Their SHA-256
identities are recorded in `donor-archives.json`. This was a targeted source
and license audit of relevant boundaries, not a whole-project security audit
or a rerun of every donor's test suite.

| Donor | Observed license | Role in Equilibrium | Source inspected |
|---|---|---|---|
| IX-Decriel | Apache 2.0 | primary capability/effect and host-boundary model | crates/decriel-core/src/authority.rs, lexer/parser layout, README |
| IX | MIT | primary source contracts, diagnostics and evidence model | ix/tools.py, ix/evidence.py, ix/validator.py, pyproject.toml, README |
| IX-HapticSight | MIT | physical envelope, multimodal quorum and latched controller model | src/ohip_control/envelope.py, authority.py, multimodal.py, realtime.py, README |
| SynapDrive-AI | Apache 2.0 | uncertainty-aware proposal inputs and deterministic experiments | synapdrive_ai/control/actuation_engine.py, neuro/fusion.py, neuro/uncertainty.py, README |
| IX-BlackFox | source-available evaluation | pre-dispatch authority/evidence concept | src/ix_blackfox/live_gateway/authority.py, README, LICENSE |
| IX-Sally | source-available evaluation | proposal versus authority and staged state commitment | src/ix_sally/proposal_gateway.py, authorization.py, README, LICENSE |

Hierarchy: Decriel and IX define the language/authority foundation; HapticSight
and SynapDrive inform embodied constraints and sensing; BlackFox and Sally
inform governance boundaries. This does not mean those six runtimes were
merged or linked together.

**No donor implementation source was copied into Equilibrium.** All language,
compiler, runtime, simulator, transport and tests were implemented separately.
BlackFox and Sally's evaluation restrictions therefore do not become dependency
licenses in the Apache-licensed release. Their own repositories and licenses
remain unchanged. Standard Apache license text was copied from Decriel's
LICENSE; the new copyright notice is in NOTICE.

Reasons for independent implementation:

- Decriel's checked operations are read/write/network/execute symbolic effects;
  the new language needs dimensions, freshness, mesh agreement and temporal
  states. Its authority separation is reusable as a design principle.
- IX's built-in tools are deterministic software operations, not physical
  quantities. Its contract/evidence distinction informs reviewable decisions.
- HapticSight's envelope uses floats and domain-specific schemas. Equilibrium
  uses a separate decimal dimensional type system and source-declared envelope.
- SynapDrive's simulated actuation and probability fusion do not validate robot
  motion or decode user intent here. The new language accepts host-fed typed
  inputs without inheriting those claims.
- BlackFox's signed ledger is not transplanted. Equilibrium's SQLite chain is
  intentionally unsigned and must not be advertised as equivalent cryptographic
  assurance. Sally's cognitive runtime is not included or advertised as AGI.

Implementation choice: Python's installed standard-library runtime made a
portable, executable, dependency-free reference release possible. The Decriel
Rust toolchain was not installed in this environment. There is no Rust compiler
or native code-generation backend in this release. Such a backend would need
separate engineering and equivalence testing rather than a directory of stubs.
