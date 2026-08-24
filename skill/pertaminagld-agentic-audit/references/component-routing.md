# PertaminaGLD audit routing

Use this routing map to divide discovery by ownership while keeping protocol reconciliation with the main agent.

## Component ownership

| Role | Primary paths | Primary concerns |
| --- | --- | --- |
| `GLD_Agent` | `firmware/gld/**`, model/profile artifacts, GLD-facing code in `apps/gld-operator/**` | sensor acquisition, nulling, DAC/profile/model binding, commands, alarms, GLD serial contracts |
| `CH_Agent` | `firmware/ch/**`, CH configuration and operator paths | GLD transport, request/response correlation, addressing, watchdogs, CH command contracts |
| `GW_Agent` | `firmware/gateway/**`, `apps/gw-operator/**` | MQTT connection/subscriptions, CH routing, topology, gateway status, retries |
| `Server_Agent` | `server/nodered/**` | decoder/encoder behavior, request ownership, MQTT topics, flow generation, persistence |
| `Integration_Agent` | `apps/operator-hub/**`, firmware-package manifests, cross-component tests | package integrity, Hub/device contracts, release gates, end-to-end acceptance |

Adjust names to the available workers; keep the path boundaries.

## Cross-component passes

Run a focused comparison when the scope crosses an interface:

- GLD to CH: addresses, command IDs, response ownership, timeout and replay semantics.
- CH to Gateway: framing, node identity, pull/push delivery, retry and duplicate handling.
- Gateway to Server: MQTT topics, subscription readiness, request IDs, liveness, topology ownership.
- Operator Hub to device: serial commands, parser responses, firmware package metadata, failure recovery.
- Release readiness: source, built artifact, manifest, flashed identity, persisted state, and acceptance evidence.
- Hardware design: schematic/net/pad evidence only; keep physical assembly and electrical behavior unproven.

For a Gateway-to-Server audit, inspect both `firmware/gateway/**` and `server/nodered/**`, then run:

```powershell
& skill/pertaminagld-agentic-audit/scripts/run-host-checks.ps1 -Scope gateway-server
```

The composite scope runs only the reviewed Gateway isolation test plus the Server checks. It does not replace direct producer/consumer source comparison.

## Worker task contract

Every delegated task must state:

1. Exact paths and interfaces in scope.
2. Explicit read-only and prohibited-action boundaries.
3. Current HEAD and known dirty paths to preserve.
4. The symptom, invariant, or interface to investigate.
5. A request for the strongest validated findings, not a finding quota.
6. Required output: trigger, impact, exact file/line evidence, confidence, missing proof, and a safe verification command or gate.

A worker is allowed to return `no strong finding`. Do not ask workers to modify files during an audit.

## Main-agent reconciliation

- Independently reproduce or trace every proposed `P1` and `P2` before reporting it.
- Merge observations only when they share one root cause. Keep separate component defects separate even when one scenario exposes both.
- Compare producer and consumer implementations directly; do not infer a protocol contract from one side alone.
- Prefer deterministic host-test evidence over textual matches. A passing host test does not prove device or deployment behavior.
- Resolve disagreements by inspecting the exact code path and rerunning a safe repository-owned check. Preserve uncertainty when evidence remains incomplete.
