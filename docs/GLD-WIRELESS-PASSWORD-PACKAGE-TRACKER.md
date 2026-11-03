# GLD Model 1 - operator password package

Last tracker heartbeat: 2026-11-02 17:49:30 Asia/Jakarta
Last evidence update: 2026-11-02 17:49:30 Asia/Jakarta

## Progress dashboard

| Scope | Progress | Status | Evidence / next gate |
|---|---:|---|---|
| **Overall** | **100%** | Complete for package scope | Compile and prepare Model 1 package for user upload. |
| 1. Explicit short credential and protection |100%|Complete|Allow operator-selected eight-character password; preserve old artifacts/other models.|
| 2. Model 1 compile and image validation |100%|Complete|Successful build, correct model, matching NVS partition and provenance.|
| 3. Hub package and handoff |100%|Complete|Strict package checks and actual read-only catalog readiness; no hardware upload.|

## Scope and calculation

Weights 30/40/30%, equal work items within each phase. Completion means a validated Model 1 package available to upload, not newly flashed or physically verified firmware. Previous Stage 2 actual test evidence remains in [the completed tracker](GLD-WIRELESS-REPLAY-GOAL-TRACKER.md). Protect sensor/pin/runtime/replay behavior, nulling/NVS, Stage 1, Model 2/3 packages, old Model 1 artifact and credentials. Do not embed the selected password in tracked source, logs, manifests or screenshots.

## Work items

| ID | Phase / work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
|1.1|Credential validation and explicit local setting|100%|Complete|Closed|18 focused tests PASS; explicit 8 chars stable, 7/64 rejected; private old credential backed up.|
|1.2|Freeze old artifact and protected sources|100%|Complete|Closed|205 package files / 10 sources hashed; old Model 1 Hub package copied separately.|
|2.1|Incremental Model 1 build|100%|Complete|Closed|Actual PIO SUCCESS 96.935s; no clean command; inherited objects rebuilt by SCons.|
|2.2|Image/model/NVS validation|100%|Complete|Closed|Strict child/Hub/preflight gates; model blob matches, unchanged NVS region and boot/partition images.|
|3.1|Place only new Model 1 package|100%|Complete|Closed|Seven new files placed; previous package archived; actual bridge serves new hash/version. Other packages/runtime unchanged.|
|3.2|Operator Hub selection and handoff|100%|Complete|User self-upload/physical test deferred|Actual browser ready: correct Model 1 Replay, v0.8.36, COM7, target 1002, NVS OFF; screenshot saved; Upload not pressed.|

## Issue register

| ID | Status | Issue | Closure evidence |
|---|---|---|---|
|P01|Solved|Replay credential preparer requires 24 characters although transport supports 8..63|Support explicit eight-character private credential; random default stays unchanged.|
|P02|Solved|New package must not replace only known-good artifact|Retain old artifact/manifest/credential backup and validate new package separately.|
|P03|Deferred|New password is not yet installed on device|User upload and subsequent actual test; old password remains until upload.|
|P04|Solved|Initial package label used shared GLD v0.8.30 instead of GLD1 v0.8.36|Corrected metadata before handoff/upload; final manifest ece0dda...8f8ec. No binary change or recompile.|

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---|---|---|---|

Tidak ada agent aktif saat ini. Package scope complete; next action belongs to user: upload and physical test. No new firmware is installed yet.



## Evidence log

- User requests compile/package for Model 1 self-upload. No upload, COM access, network switch or reset is part of this assignment.

- Heartbeat SLA breach: 90s while assigning workers/capturing baseline; timestamp not backdated.

- Baseline: tmp/wireless-password/protected-before.json; old package backup tmp/wireless-password/previous-hub-model1. Original named build artifact preserved. GLD worker implementing credential preparation; Integration worker reviewing manifest validation read-only.

- Accepted preparer diff: minimum existing explicit credential 24 -> 8; random default/character rules unchanged. 18 focused tests PASS. Model 1 credential matches user selection (value not logged), private original backup verified. No runtime source changes.

- Actual build log SUCCESS: 96.935s, Model 1 Replay. Next gate copied image/manifest/model/NVS validation. Read-only live bridge checks: both wireless collectors inactive; no recording/recovery/connection.

- Heartbeat SLA breach: 61s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 68s while authoring/reviewing package; no backdating.

- Heartbeat SLA breach: 98s while authoring/reviewing package; no backdating.

- Build accepted: firmware SHA256 792638eb8af70252b02b6a0887a651e01f0df58950b6c5b123bb688fa70cb2b6, 1,047,008 bytes, PIO96.935s, no warnings. New strict package and live bridge endpoint PASS; corrected manifest SHA256 ece0dda563d31df889a0bb9b6cc873d50e1a6d70c403c8951a51183a85a8f8ec. First label drift caught independently, dialog closed until correction; never uploaded. Both workers complete; Root browser handoff active.

- 2026-11-02 17:49:30: Final handoff accepted: actual API serves new binary/hash/version, four files match. Actual browser dialog selects Model1Replay, COM7, target1002, ResetNVS=false, Upload enabled. No upload clicked; PIN remains user-controlled. Screenshot tmp/wireless-password/operator-upload-ready.png. Report docs/firmware/gld-dataset-wireless-model1-password-package-20261102.md. Both workers complete and ownership released.
