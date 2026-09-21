---
name: pertaminagld-agentic-audit
description: Audit the PertaminaGLD repository across firmware, Operator Hub, Gateway, Node-RED, and integration paths using evidence-bounded component routing and deterministic read-only checks. Use when asked to find bugs, regressions, contract drift, or readiness gaps in this repository. Do not use this skill as authorization to implement fixes, build or package firmware, access COM ports, upload, deploy, install dependencies, or operate live services.
metadata:
  short-description: Evidence-bounded PertaminaGLD audits
---

# PertaminaGLD Agentic Audit

Produce a sceptically validated repository audit. Report findings by default; do not silently turn an audit into a remediation task.

## Preserve the boundary

- Start read-only. Permission to audit is not permission to fix.
- Do not mutate source, generated flows, firmware packages, documentation, Git state, services, databases, or external systems.
- Do not build or package firmware, access COM ports, upload, start or stop Operator Hub, operate MQTT, deploy Node-RED, install dependencies, or call live services unless the user authorizes that action separately.
- If repository coordination rules require an activity entry, follow them. When the user sets a strict no-write boundary, that boundary wins; disclose that the coordination write was skipped.
- Preserve a dirty worktree. Never stash, reset, clean, overwrite, or discard existing changes.
- Redact credentials and tokens from commands, output, and reports.
- Distinguish source/static, host-test, build, runtime, device, deployment, and field evidence. Never promote one class into another without proof.

## Establish the current state

1. Resolve the Git repository root. Do not assume the current directory is the root.
2. Read the applicable `AGENTS.md` chain, `ActivityAI/rules/AGENTS.md`, `ActivityAI/rules/AI_WORKFLOW_RULES.md`, `docs/resume.md`, and current activity logs when present.
3. Recheck branch, HEAD, working-tree changes, and active ownership. Treat previous reports and memory as leads, not current evidence.
4. Run the read-only inventory helper:

   ```powershell
   & skill/pertaminagld-agentic-audit/scripts/inventory.ps1
   ```

## Select scope and route work

- Honor an explicit user scope. For a broad audit, inspect production paths before examples, archives, or generated output.
- Read [component-routing.md](references/component-routing.md) before delegating or auditing more than one component.
- Keep baseline collection, cross-component reconciliation, and final validation with the main agent.
- Give each worker non-overlapping paths and interfaces. Do not assign duplicate discovery passes merely to increase the number of agents.
- Ask for the strongest validated findings, not a quota. A worker may correctly return no finding.

## Run safe host checks

Use only checks already present in the repository. Executable checks are pinned in `references/host-check-manifest.json`; the helper skips them when their reviewed hash changes. It never dynamically discovers test files, installs dependencies, builds firmware, opens a serial port, contacts a broker, or deploys anything.

```powershell
& skill/pertaminagld-agentic-audit/scripts/run-host-checks.ps1 -Scope all
```

Available scopes are `firmware`, `server`, `hub`, `gateway-server`, and `all`. Use `gateway-server` for that producer/consumer interface instead of running unrelated Hub and full-firmware checks. Treat a failing check as a candidate signal, not automatically as a product defect. Treat a skipped or hash-mismatched check as missing evidence; review the changed check before updating its manifest hash, and do not install a missing runtime or dependency during an audit.

## Validate each finding

Read [evidence-policy.md](references/evidence-policy.md) before final triage.

A reportable finding needs all of the following:

1. A concrete trigger or reachable state.
2. A source-to-impact trace across the relevant functions, messages, or artifacts.
3. Exact file and line evidence.
4. A violated invariant or expected contract.
5. Checks for nearby guards, retries, rollback, compensation, and generated-source ownership.
6. A safe verification gate that could confirm the fix later.

Reduce confidence or reject the candidate when the test is stale, the affected code is non-production, a guard prevents the trigger, or the impact is speculative. Do not report style preferences, TODO comments, naming concerns, or missing features as bugs without a violated current contract.

Use [finding.schema.json](references/finding.schema.json) for JSON, persisted, or machine-readable findings.

## Report and stop

The final audit report must include:

- audited branch, HEAD, and whether the worktree was dirty;
- findings ordered by `P1`, `P2`, then `P3`, with confidence;
- trigger, impact, invariant, exact evidence, missing proof, and verification gate;
- host checks that passed, failed, or were skipped;
- explicit statements for absent runtime, device, deployment, or field evidence;
- a separately labeled next batch proposal when remediation would require new authorization.

Use clickable absolute local file links. Omit weak candidates rather than padding the report. State that no validated findings does not prove the repository is bug-free.

Stop after the report. Implement fixes only after an explicit remediation request, then re-read repository rules and claim the affected paths before editing.
