# Threat model and claim boundary

Protected within the trusted-host model:

- A source author cannot turn a capability declaration into an external grant.
- Source dimensional/type/policy errors cannot become checked actuator actions.
- Stale, missing, replayed, mismatched or over-uncertain required inputs fail
  closed at evaluated dependencies.
- Mesh disagreement cannot be concealed by majority outlier removal.
- Commands and bounded adaptation cannot exceed declared software envelopes.
- Changed source, session, actuator scope, action outputs or review subject
  invalidate the applicable authority token or checked artifact.
- Reusing an exact review nonce in the same authority instance is denied.
- An active adapter effect requires a preceding committed authorization record.
- Grant revocation and runtime snapshot changes are rechecked after that commit.
- Evidence failure before dispatch blocks it. Failure after dispatch produces
  an unresolved authorization and a best-effort stop request.

Trusted components: Python host process, runtime installation, host adapter,
authority keys/issuers, host-assigned clock/session, SQLite and its storage,
independent checkpoint retention, and any hardware controller/watchdog.
The host can explicitly disable required reviews by issuing such a grant.
This is an administrative capability and must be protected outside the DSL.

Not protected:

- Arbitrary hostile Python in the host process, compromised adapters, stolen
  authority/producer keys, a forged host clock, or false physical measurements.
- Loss of power or process death between authorization, hardware action and
  outcome recording. Authorization remaining without outcome is observable;
  exactly-once physical execution is not guaranteed.
- Sensor independence, physical dynamics, stopping distance, contact force,
  real-time scheduling, formal stability, emergency-stop certification or
  robot/machine regulatory compliance.
- Whole-export rewriting without an independently trusted original head.
  Hash linkage is not public-key authentication.
- Network confidentiality, reliable UDP delivery, distributed clock agreement,
  distributed actuator atomicity, Byzantine consensus or durable revocation.

The virtual plant integrates velocity into position using a discrete kinematic
model. Other actuator types are setpoints only. Thermal example inputs are
scenario values; no thermal dynamics model is inferred. `explore` enumerates
a bounded finite synthetic input set, not all physical environments.

No Anya-specific designs, patents, private materials or medical device models
were used to implement this release. No claim of patent novelty or freedom to
operate follows from donor separation. There is no AGI, EEG decoder, neural
intent inference or clinical microsurgical capability in this code.

The release includes ROS-neutral host interfaces but no ROS 2 adapter. It is
a research supervisory layer, not a replacement for existing controllers.

See [CLAIMS.json](CLAIMS.json) for implemented claims with exact validation
locations, and [VALIDATION_REPORT.md](../VALIDATION_REPORT.md) for observed runs.
