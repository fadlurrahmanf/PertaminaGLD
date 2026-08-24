# PertaminaGLD audit evidence policy

## Evidence levels

Label every conclusion with the strongest evidence actually obtained:

| Level | Meaning |
| --- | --- |
| `proposal` | suggested design or next action; not an observed defect |
| `source-confirmed` | demonstrated from current source or artifact content |
| `host-test-proven` | reproduced by a deterministic local test without target hardware or live services |
| `build-confirmed` | the relevant target was built successfully; no runtime claim follows |
| `runtime-observed` | observed in a running host process or service |
| `device-observed` | observed on an identified physical device |
| `deployment-observed` | observed in the intended deployed environment |
| `field-observed` | observed under the defined field acceptance conditions |
| `tbd` | evidence is absent or inconclusive |

These levels are not a universal linear ladder. For example, a build result cannot replace a protocol runtime observation, and TCP reachability cannot replace an MQTT `CONNACK (0)`.

## Severity

- `P1`: credible safety, security, unrecoverable data/state corruption, or fleet-wide operational failure requiring immediate attention.
- `P2`: reachable correctness or availability defect with material device, topology, command, alarm, or release impact.
- `P3`: localized defect, degraded diagnostics, recovery weakness, or maintainability issue with a concrete operational consequence.

## Confidence

- `high`: trigger and impact are directly traced and reproduced, or source logic is deterministic with no credible blocking guard.
- `medium`: trace is strong but one runtime condition, integration assumption, or artifact identity remains unverified.
- `low`: plausible lead with material gaps. Keep it out of the primary findings list; place it under follow-up evidence if useful.

## Finding gate

Before reporting, answer all six questions:

1. What exact input, state, or sequence triggers the behavior?
2. Which production path carries it to the impact?
3. What invariant or documented contract is violated?
4. Which guards, retries, rollback paths, and compensating controls were checked?
5. What evidence class supports each claim, and what stronger proof is absent?
6. What safe, deterministic gate would verify remediation?

Reject a finding that cannot answer the first four questions. Keep missing runtime or device proof explicit rather than inventing it.

## PertaminaGLD boundaries

- EasyEDA schematic, net, and PCB pad data can confirm design connectivity; they cannot prove the assembled board, soldering, voltage, timing, or physical fault.
- A package hash can prove file consistency; it cannot prove which image is flashed.
- A successful upload cannot prove target identity, NVS contents, active nulling profile, DAC state, or model binding.
- TCP reachability cannot prove MQTT authentication or subscription readiness. Require broker evidence such as `CONNACK (0)` and the relevant subscription result.
- Source configuration cannot prove the deployed Node-RED flow, broker ACL, service state, or field topology.
- Telemetry values cannot substitute for electrical waveform, calibration, or sensor-response evidence.
- Firmware build success cannot prove GLD nulling. Require device evidence for all expected channels, persisted profile, DAC readback, and model/profile binding.

## Report shape

For every finding, provide:

- ID, title, component, severity, status, confidence, and evidence level.
- Trigger and impact.
- Violated invariant.
- Exact file/line evidence and any host-test command/result.
- Missing proof.
- Verification gate.
- Suggested fix only as a separately labeled proposal.

Passing syntax checks, a clean worktree, or no findings in one pass does not prove the system is bug-free.

