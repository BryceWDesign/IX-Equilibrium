# Trusted host integration

The language controls requests. The host owns identity, authority keys, device
bindings, clocks, telemetry, real effects and independent stopping behavior.
Do not expose arbitrary Python execution to untrusted source authors.

## Minimal host lifecycle

1. `compile_source(source)` returns a `CheckedProgram`.
2. Create a fresh host-assigned session, separate grant/review keys, a `Journal`
   at a durable path, and an adapter implementing `apply(action)` and `stop`.
3. Construct `Runtime(checked, session=..., authority=..., journal=..., adapter=...)`.
4. Feed samples using `runtime.ingest(sample, now_ms)` and a trusted clock.
5. Ask for `plan = runtime.plan(at_ms)`. `plan.action.sha256` is the exact review
   subject, including source, session, tick, time, state and all outputs.
6. Obtain an external scoped grant and, when required, a review for that action.
7. Call `runtime.execute(plan, grant=..., review=...)`. Alternatively `step`
   accepts a `review_provider(action)` callback and performs the same checks.
8. On shutdown, request `runtime.emergency_stop(reason, at_ms)`, then close the
   journal. A hardware watchdog must remain independent of process survival.

The runtime recomputes plans before authorization and after its pre-dispatch
commit. A modified plan or changed sensor revision is rejected. Python object
privacy is not an isolation mechanism against hostile code in the host process.

## Host authority

```python
from equilibrium.authority import Authority
import secrets

authority = Authority(secrets.token_bytes(32), secrets.token_bytes(32))
grant = authority.issue_grant(
    source_sha256=checked.source_sha256,
    session=session,
    principal=authenticated_principal,
    actuators=["arm"],
    not_before_ms=0,
    expires_ms=1000,
    nonce=secrets.token_hex(16),
    review_required=True,
)
```

This snippet presumes host-defined `checked`, `session` and an independently
authenticated principal. Grant issuance is an administrative host operation,
not a source-language expression. `Authority` authenticates tokens with HMAC
SHA-256 using distinct keys of at least 32 bytes. Keys must not be placed in
program source, scenario inputs, a public repository or exported evidence.
Review issuance must follow the host's actual human approval workflow; calling
`issue_review` alone does not establish that a human approved anything.

Review tokens bind the full `Action` digest and expire against the same trusted
logical clock. Each session/nonce is single-use in one `Authority` process.
Reservation occurs before evidence commit, so failure does not permit reuse.
The journal also rejects duplicate authorized action digests across reopenings.
Revocation is process-local in v0.1.0. Use new sessions and rebuild external
revocation state on restart; do not treat this as a durable identity service.

`review_required=False` is an explicit host-owned grant choice for deployments
whose external policy allows it. Untrusted `.eq` source cannot request that
change. HMAC proves key possession, not an independently attributable personal
signature. The simulator's publicly known keys never establish real authority.

## Adapter contract

`apply(action)` receives outputs as canonical SI quantities:

```json
{"arm":{"value":"0.02","dimension":[1,0,-1,0]}}
```

It must enforce its own configured resource binding, physical limits, timeout,
concurrency rules and fail-safe behavior. It returns a JSON-serializable
observation; the runtime records it after dispatch. An adapter's reported
observation is not independent sensor proof of physical execution. Do not
return binary floats: use decimal strings.

`stop(safe_outputs)` is an independent best-effort path. It can be invoked
without an active grant and even when evidence persistence fails. **Validate
the fallback against hardware configuration**, rather than trusting source
authors to choose physical safety parameters. Hardware stops must work even
if this Python process crashes. `stop_confirmed` in runtime reports means the
adapter returned successfully; it is not certification that a robot stopped.

Multi-actuator commands use one batch action. If the hardware adapter applies
part of a batch and fails, there may already be physical effects. The runtime
latches a fault, requests a stop and leaves unresolved authorization evidence.
There is no claimed physical rollback or distributed two-phase commit.

## Real I/O demonstration

```powershell
python examples/host_demo.py --out out/host-allowed
python examples/host_demo.py --deny-review --out out/host-denied
```

The complete example sends authenticated sensor datagrams over real loopback
UDP. Its file sink opens an independent SQLite connection to witness committed
authorization before writing `command.json`. The denied-review run creates no
command file. Both runs request cleanup and export evidence. Identity/review
are synthetic local fixtures; the effect is a real file write, not robot motion.

## Authenticated sensor transport

`SensorBridge` binds loopback by default, with an explicit per-producer key and
channel scope. `send_sample` emits a canonical HMAC-protected packet bound to
source revision and session. The receiver checks MAC, producer scope, source,
session and the runtime's sample anti-replay/freshness rules before ingestion.
Datagrams are limited to 8192 bytes. No device discovery or implicit trust exists.

UDP delivery is not guaranteed. There is no encryption or clock synchronization.
Protect networks separately, assign keys through an authenticated channel, and
provide host clocks. Packet rejection raises a controlled error; the host
decides whether to stop immediately or await remaining quorum. A missing
required input eventually fails freshness/requirements. A process with the
producer key can forge that producer's measurements; signatures cannot prove
the physical sensor value is true.

## Evidence

`Journal(path)` validates the full chain at startup and during each append.
SQLite serializes independent writers with `BEGIN IMMEDIATE`; a commit precedes
every active adapter call. v0.1.0 deliberately uses full replay on each append,
so journal append cost grows with history. This is a correctness-first reference
implementation, not validated high-rate telemetry infrastructure.

`verify_export(export, expected_head)` checks receipt ordering, canonical
digests, authorization subject binding, linked outcomes and an optional retained
head. Unresolved authorizations are reported without inventing outcomes.
The exported chain is **unsigned**. An attacker who can replace the whole export
can recompute it. Retain checkpoints in independent trusted storage or add a
host signing layer. Journal authentication and hardware-backed signing are not
implemented in this release.
