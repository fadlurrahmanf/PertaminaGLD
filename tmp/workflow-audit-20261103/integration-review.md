# Integration audit I, revision 1

Scope: current protocol-3 workflow service, collector and bridge admission; independent source review plus deterministic host tests. No GLD, serial, WLAN, dialog, live service change, firmware compile or upload.

## Confirmed findings

1. **Solved in backend:** verified Stop → Unlock → Lock could not re-lock because the UI submits Configure even when unchanged, but Configure rejected every request once a ledger existed. Reproduced using real service + existing injected device: `verification.verified=True`, `can_continue=True`, `locked=False`; identical Configure raised `Reset dan pilih file baru...`.
   - Repair in `apps/gld-operator/dataset_workflow.py`: normalize and validate the request, accept it idempotently only if it equals `_logical_config`; reject changed label/mode/schema before mutation. Add `configuration_frozen` snapshot field.
   - New tests in `test_dataset_workflow.py`: full Stop → Unlock → identical Configure → Lock → Continue, same CSV and five exact rows across two segments; changed schema rejected with unchanged bytes, original form still re-locks, Reset clears frozen state.
2. **UI issue reported to root:** owned cleanup may stop in `cleanup_pending=True, cleanup_paused=True`; backend Connect supports exact-owned-SID recovery and is tested, but the prior UI disabled password and Connect due to Lock/active. Recovery must expose only password and Connect while device/schema remain locked. Root owns the UI repair.
3. **UI issue reported to root:** errors leave changed input DOM values visible while backend rejected the changes; root owns synchronization and explicit frozen-schema guidance. Preserve immutable schema for Continue into the existing CSV.

## Reviewed contracts

- Canonical ledger and projected CSV both fsync before prefix ACK; failed partial writes roll back both public streams. Direct cutoff freezes public CSV/history while private cleanup drains only the owned remote SID.
- Pause/Resume acquisition is separate from transport recovery. Transition identities reconcile ambiguous ACKs. Stop waits for device terminal reconciliation and verifies every row/column against full ledger, not the bounded UI history.
- Continue creates a new remote SID/segment in the same logical CSV; rejects model/profile/schema/file tampering. Global row IDs remain contiguous.
- Reset from acknowledged Pause first requests Stop and waits for verified closure; cleanup prevents reset/unlock. Files are retained.
- Shared bridge admission blocks serial/upload/legacy wireless takeover while new workflow is connected, paused, transitioning or pending cleanup.
- Connection setup step is intentionally retained for a completed logical CSV, since terminal Stop closes WS and Continue reconnects. Do not derive this gate solely from `connected` after Stop. Root was notified to distinguish live connection from prior setup validation.

## Verification

Command: `apps/gld-operator/python-embed/python.exe -m unittest discover -s apps/gld-operator/tests -p 'test*workflow*.py' -v`.

- Baseline before repair: **46 passed**.
- After repair and two new tests: **48 passed**, 12.380 s.
- Focused `git diff --check`: passed.
- New `dataset_workflow.py` SHA256: `aaa18e69f0db24fdd9a6fe8f02e1bab5955457fd8617f609c24937b8b2f932d2`.

Runtime files changed by this worker: only `apps/gld-operator/dataset_workflow.py`. Test changes: only `apps/gld-operator/tests/test_dataset_workflow.py`. Original collector and legacy transports unchanged.

Remaining evidence: actual Windows WLAN/native file picker and GLD ADC/inference/timing/RF/recovery remain external proof; fixture tests do not establish physical behavior. Root must integrate UI repair, rerun combined browser/regression checks and activate only after confirming live services are idle.
