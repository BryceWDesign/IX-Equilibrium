# Design and extension boundaries

Equilibrium is a domain-specific language for supervisory interaction. Its
reason to exist is the common representation of physical dimensions, sensor
freshness/uncertainty, operator requests, independent effect authority and
recorded outcomes. It does not replace motor control or safety controllers.

| Module | Executable responsibility |
|---|---|
| syntax.py, parser.py | tokens, positions, immutable source tree, precedence parser |
| units.py, expressions.py | dimensional types, decimal arithmetic, finite expressions |
| compiler.py | semantic checks, reachable states, bound summaries, checked artifact |
| sensors.py, robust.py | per-channel validity, quorum intervals, conservative predicates |
| runtime.py | snapshot plans, state transitions, bounded adaptation, effect mediation |
| authority.py | external scoped grants, exact-action reviews, expiry, revocation and reservation |
| evidence.py | durable commit-before-effect journal and independent integrity verification |
| adapters.py | host protocol and kinematic virtual plant |
| transport.py | authenticated scoped UDP sensor packets |
| simulation.py | scenario execution, replay, boundary faults and finite exploration |
| cli.py, report.py | operational commands and offline evidence display |

Compilation produces a revision-bound checked source tree with inferred
dimensions and static bound summaries. Loading serialized IR recompiles and
requires exact equality. The runtime interprets that checked tree; it does not
generate Python or machine code from source. Its finite language excludes
unbounded loops and dynamic calls, making each tick's source evaluation bounded
in structure. That does not imply a bounded wall-clock execution time, because
storage and host callbacks can block.

The external grant and sensor inputs are independent of source declarations.
An operator intent input indicates a request. It is not permission. A review
covers the exact proposed setpoints, source revision, session, state, time and
tick. The source cannot manufacture that review. Adaptation cannot enlarge its
declared parameter domain or actuator range.

The included demos cover assistive interaction, temperature mesh setpoints and
paired actuators. The same primitives can express haptic envelopes, operator
shared control and instrumented experimental meshes. Such applications still
need actual validated sensors, adapters, dynamics and independent hardware
limits. Neural inputs can arrive as host-fed channels, but this language does
not infer mental states or decode EEG itself.

## What would materially advance the next release

These are future engineering directions, not implemented features or promises:

1. A native backend with checked-IR semantic equivalence tests and measured
   execution deadlines, while leaving real-time inner loops in suitable hosts.
2. Coordinate-frame/vector types and transforms that reject frame mismatches.
3. Tested ROS 2 integration and one instrumented hardware demonstration with
   independently enforced limits and measured stop behavior.
4. Durable revocation, authenticated identity integration and signed checkpoint
   anchoring; a hardened journal with incremental validation and measured scaling.
5. Temporal verification against explicit environment models, including sensor
   delay and actuator dynamics, with assumptions exported alongside results.
6. Model-informed experimental soft-device or haptic systems, validated against
   real measurements rather than inheriting simulation conclusions.

No novelty/patent clearance, industry adoption or physical stability claim is
made. A new syntax alone is not evidence of an advantage over other robotics
tooling. Evaluate the implemented checks and recorded behavior directly.

