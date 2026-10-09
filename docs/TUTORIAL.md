# Programming your first system

Use Python 3.11 or later. From the repository directory, all commands can run
as `python -m equilibrium ...` without installing anything. Installation
additionally supplies the `equilibrium` executable.

## 1. Check a complete source example

```powershell
python -m equilibrium check examples/assist.eq
```

The JSON response identifies the exact source digest, number of states, and
which command/adaptation ranges were established statically. A dimensional
mistake such as `command arm = 2 N;` fails with a source-positioned diagnostic.

## 2. Run the simulated assistance scenario

```powershell
python -m equilibrium run examples/assist.eq --scenario examples/assist.scenario.json -o out/assist
Start-Process .\out\assist\report.html
```

The scenario supplies three distance channels, a load measurement and boolean
operator intent. Events 0 and 1 remain idle. Intent is true in events 2..9:
the plant receives eight admitted commands. Removing intent returns the output
to zero; the final position is 0.014 m in the virtual kinematic model. These
results describe the included synthetic scenario, not a measured robot.

`report.html` is offline and displays decisions, timing, setpoints and adapter
call counts. `bundle.json` contains source, complete input events, outcomes and
the evidence chain. You can inspect both without a server or cloud account.

## 3. Compile and run a checked artifact

```powershell
python -m equilibrium compile examples/assist.eq -o out/assist.eqir.json
python -m equilibrium run out/assist.eqir.json --scenario examples/assist.scenario.json -o out/compiled
```

The artifact embeds the exact source, normalized AST, dimensionally checked
declarations, bound summaries and hashes. Loading it recompiles source and
requires exact agreement; an edited artifact cannot bypass checking. This is
checked intermediate representation interpreted by the runtime, not native
machine code.

## 4. Reproduce and inspect evidence

```powershell
python -m equilibrium replay out/assist/bundle.json
python -m equilibrium verify out/assist/bundle.json
```

Replay reruns every recorded synthetic event and compares the entire bundle.
Verify checks sequence, linkage, receipt digests and authorization/outcome
relationships. To detect truncation against a separately retained checkpoint:

```powershell
$bundle = Get-Content .\out\assist\bundle.json -Raw | ConvertFrom-Json
$head = $bundle.evidence.head
python -m equilibrium verify out/assist/bundle.json --expected-head $head
```

Keep the original `$head` separately before transferring or auditing a bundle.
Reading a potentially modified bundle's own head does not independently anchor
it. Hash linkage alone is integrity bookkeeping, not a signature.

## 5. Test failure paths and finite input combinations

```powershell
python -m equilibrium campaign examples/assist.eq --scenario examples/assist.scenario.json -o out/campaign.json
python -m equilibrium explore examples/assist.eq --choices examples/assist.choices.json --depth 4 -o out/exploration.json
```

The assistance campaign injects 13 authority, evidence, adapter and sensing
faults. Other source programs receive the seven general host-boundary faults.
Campaign requires a baseline containing an admitted command. Exploration tries
all 81 four-event combinations of the three included sample choices. It records
counterexamples and outcome counts, but does not claim a general safety proof.

## 6. Change behavior deliberately

Copy `examples/assist.eq` to your own `.eq` file. Change the actuator speed
range and command expression together. Changing only the range can leave a
command outside it: compilation catches a constant violation; execution catches
an unproven dynamic violation. Reduce the `fresh` limits and rerun scenarios
that omit samples to test stale-input stops. Reduce mesh tolerance and introduce
a disagreeing reading to test the quorum veto.

Every source change creates a new SHA-256. Host grants for the old revision do
not authorize the new program. Simulator grants are regenerated automatically
and are explicitly synthetic. They cannot represent a real operator approval.

## 7. Author scenario inputs

Scenario envelope:

```json
{"format":"equilibrium.scenario/1","name":"my-scenario","events":[
  {"at_ms":0,"simulation_grant":true,"simulation_review":true,"samples":[
    {"channel":"intent","value":true,"unit":"bool","at_ms":0,"sequence":0,"uncertainty":"0"}
  ]}
]}
```

This minimal shape is illustrative. `assist.eq` also needs its numeric sensor
samples, so use the complete supplied JSON as the working starting point.
Each tick is 20 ms for assistance, 50 ms for thermal control and 10 ms for
shared control. Sample sequences increase per channel. `simulation_grant` and
`simulation_review` default to false; omitting them does not grant permission.

Use `adapter_failure`, `stop_failure`, `revoke_grant`, and `journal_failure`
(`before`, `after`, or `all`) for deliberate fault injection. A malformed
sample faults the scenario and prevents active dispatch. An ended scenario can
report a running state: the simulator is a finite virtual experiment, not a
continuing hardware controller. Use a terminal state when completion is part
of the program's required behavior.

See [SDK.md](SDK.md) to connect trusted host adapters and real sensor transport.
