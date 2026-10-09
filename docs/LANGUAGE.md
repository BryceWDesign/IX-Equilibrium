# Equilibrium language reference, version 0.1

Equilibrium programs describe bounded supervisory decisions across operator
inputs, sensor channels, sensor meshes, parameters and actuator setpoints.
The reference implementation is Python 3.11+, not an extension of Python
syntax. Programs cannot import Python, execute shell commands or invoke eval.
The host SDK itself runs in the same trusted Python process as its integrator.

Files use `.eq`. Source is UTF-8. `//` introduces a line comment. Names are
case-sensitive ASCII identifiers. Statements end with semicolons. State blocks
do not have a trailing semicolon. One file contains exactly one system.

```text
system Example {
    tick 20 ms;
    sensor distance : m fresh 100 ms uncertainty 0.01 m;
    input intent : bool fresh 100 ms;
    param gain : scalar = 0.5 within [0.1, 1.0] rate 0.1;
    actuator arm : mps range [-0.2 mps, 0.2 mps] safe 0 mps slew 1 mps2;
    capability command arm;
    state idle initial { when intent -> moving; }
    state moving {
        require distance > 0.2 m;
        adapt gain = clamp(distance / 1 m, 0.1, 1.0);
        command arm = gain * 0.2 mps;
        when not intent -> idle;
    }
    state stopped terminal { }
    on fault -> stopped;
}
```

`capability command arm` declares a requested effect. It never grants runtime
authority. The integrating host must supply a separate grant and any review
that the grant requires.

## Values and dimensions

| Unit | Meaning | Canonical conversion |
|---|---|---|
| scalar, rad | dimensionless scalar / angle | 1 |
| m, cm, mm | length | 1 m, 0.01 m, 0.001 m |
| s, ms | time | 1 s, 0.001 s |
| kg | mass | 1 kg |
| N | force | kg m / s² |
| Pa, kPa | pressure | 1 Pa, 1000 Pa |
| mps | speed | m / s |
| mps2 | acceleration | m / s² |
| Hz | frequency / dimensionless slew | 1 / s |
| K | absolute temperature | kelvin |
| bool | true or false | not numeric |

Dimensions are vectors of length, mass, time and temperature exponents. Speed
can be written as `distance / 1 s`; multiplication and division derive types.
Addition, subtraction and comparisons require compatible dimensions.
`rad` is dimensionless in this release; no angle/coordinate-frame distinction
is enforced. There are no vectors, coordinate transforms, Celsius offsets or
user-defined units yet. Such constructs are rejected if used as declarations.

Numbers in source use decimal digits, with an optional fractional part and
unary minus. JSON numeric quantities are **decimal strings** or integers.
Binary floats and boolean-to-number conversion are rejected. Computations use
28-digit decimal precision, round half even, isolated from the application's
Decimal context. Nonzero magnitudes must remain within 1e-30..1e30 and numbers
may contain at most 28 significant digits. Overflow, underflow outside that
domain, division by zero and invalid clamp bounds fault the runtime. This is
specified software arithmetic, not a physical measurement accuracy claim.

Numeric operators, from low to high precedence: `or`, `and`, `== !=`,
`< <= > >=`, `+ -`, `* /`, unary `- not`. Parentheses override precedence.
`and` and `or` short-circuit. Boolean ordering is rejected. Functions:

| Function | Arity | Behavior |
|---|---|---|
| abs(x) | 1 | absolute value |
| min(a,b) | 2 | smaller value |
| max(a,b) | 2 | larger value |
| clamp(x,lo,hi) | 3 | restrict x to inclusive bounds; inverted bounds fault |

All numeric function arguments must share dimensions. There are no strings,
arrays, recursion, arbitrary function definitions, imports, dynamic evaluation
or unbounded loops in source. Expressions are limited to 64 levels and 256
nodes; files to 1 MB and 50,000 tokens; state machines to 256 states.

## Channels and meshes

`sensor` and `input` both declare host-fed channels. `input` is a descriptive
keyword, not a more trusted channel. Every channel has a freshness interval.
Numeric channels require an uncertainty ceiling; bool channels have no numeric
uncertainty declaration. Channel values have no inferred hardware origin.

```text
sensor camera : m fresh 80 ms uncertainty 0.01 m;
sensor rangefinder : m fresh 80 ms uncertainty 0.01 m;
sensor backup : m fresh 80 ms uncertainty 0.01 m;
mesh clearance : m = quorum(camera, rangefinder, backup) tolerance 0.08 m require 2;
```

Each numeric sample carries a nominal value and absolute uncertainty. Its
closed interval is nominal ± uncertainty. A mesh requires at least its declared
number of available, fresh, valid members. All available valid members must
agree: the outer union of their intervals must be no wider than tolerance.
The result is their nominal median, with the complete outer interval retained
for conservative predicates. A third dissenting member vetoes the mesh even
when two members agree. A missing member can be tolerated when quorum remains.
No sensor independence is proven from having distinct names.

Samples with replayed sequences, future/negative/regressing timestamps,
incorrect units, excessive uncertainty or malformed values are rejected.
An invalid known channel remains unavailable until a valid newer sample
arrives. A sample is fresh at exactly the declared age limit, stale beyond it.
Missing/stale values fault only when an evaluated expression needs them; the
short-circuit rules can avoid an unused dependency.

Comparisons involving numeric channels use intervals, not just nominal values.
`clearance > 0.2 m` is true only when its entire interval is above 0.2 m;
it is false when entirely at or below it. Overlap makes the predicate uncertain
and faults the step. Negation cannot turn uncertainty into permission. Interval
arithmetic is conservative and may reject correlated expressions such as
`distance - distance`; it does not model correlations or Bayesian confidence.

## Parameters and adaptation

```text
param gain : scalar = 0.5 within [0.1, 1.0] rate 0.1;
adapt gain = clamp(clearance / 1 m, 0.1, 1.0);
```

Initial values and bounds are checked at compilation. `rate` is a maximum
change **per tick**, in the parameter's own dimensions. It is not a rate per
second. Proposed values must first fall entirely within the declared interval;
then the rate limiter limits the change. Out-of-bounds adaptation faults rather
than being silently clamped. Write `clamp` explicitly when clipping is intended.

Commands and adaptations evaluate against the same pre-tick snapshot. Multiple
adaptations cannot depend on each other's changes within the tick. Prospective
parameters are checked against all invariants and the selected state's
requirements, then committed only after successful observation recording (or
a successful idle stop). Failed authorization/dispatch does not commit them.
This is bounded deterministic adjustment, not learned control or self-rewriting.

## Actuators, effects and envelopes

```text
actuator arm : mps range [-0.2 mps, 0.2 mps] safe 0 mps slew 1 mps2;
capability command arm;
command arm = gain * 0.2 mps;
```

The compiler checks dimensions and rejects out-of-range constant commands.
Its checked IR reports whether a static interval bound is established.
Unproven expressions are still permitted as syntax, but the runtime recomputes
their intervals and denies unbounded/out-of-range results before dispatch.
Every accepted active command is limited to the actuator range and slew per
tick. Slew dimensions must be actuator dimension / time. Default/unassigned
actuators request their declared safe setpoint immediately. Stop bypasses slew.

Actuator names are host bindings, not network destinations. A `safe` literal
is a program's requested fallback, not a validated physical safety assertion.
The host adapter must independently validate bindings, fallback behavior and
all hardware limits. A batch action is one exact review subject covering all
outputs. The adapter determines atomicity; physical rollback is not assumed.

## States, invariants, transitions and faults

Exactly one state is `initial`. Terminal states cannot command, adapt or
transition. The fault destination must be terminal. Each ordinary state must
be syntactically reachable from the initial state (the fault state is also
considered reachable). Syntactic reachability does not prove a guard feasible.

`require expression;` is a state-local condition. `invariant name : expression;`
applies before every tick and to prospective adaptation. A false/uncertain
requirement or invariant requests a stop and latches the fault state.

`when condition -> state;` and `after duration -> state;` express transitions.
Elapsed time is measured since entering the current state; self-transition
resets it. If more than one transition is enabled in the same tick, the step
faults rather than choosing by declaration order. Design guards to be mutually
exclusive. One transition is taken per tick. Both the current state's and
destination state's requirements are checked before destination commands.

At each step:

1. Validate the logical clock, snapshot channels and compute meshes.
2. Evaluate global invariants and current-state requirements.
3. Select zero or one transition; check destination requirements.
4. Compute bounded adaptations; recheck prospective invariants/requirements.
5. Compute bounded outputs with slew limiting.
6. Obtain host authority and any exact-action review.
7. Commit authorization to SQLite before any active adapter call.
8. Recheck grant/revocation and the source/sensor/parameter snapshot.
9. Invoke the adapter; commit its reported observation.
10. Commit software state and parameters for the next tick.

No active outputs means an idle/terminal decision, then an independent stop
request. Idle stops need no active-command grant. Failures at any boundary
request a best-effort independent stop, even if journaling also fails. A failed
stop is reported as `stop_confirmed: false`. After a fault, there is no automatic
reentry. Start a new host-approved session after addressing the cause.

## Timing and trust

Tick must be a whole number of milliseconds in [1,60000]. The first tick is
time zero; each subsequent tick must be exactly one declared period later.
Host-fed sample timestamps share that logical clock. A missed/regressing step
faults. This is schedule validation, **not** a wall-clock watchdog or hard
real-time scheduler. Hosts must implement independent clocks, watchdogs,
emergency stops and stopping-distance limits.

See [SDK.md](SDK.md), [THREAT_MODEL.md](THREAT_MODEL.md), and
[grammar.ebnf](grammar.ebnf). Source is interpreted only after checking.

