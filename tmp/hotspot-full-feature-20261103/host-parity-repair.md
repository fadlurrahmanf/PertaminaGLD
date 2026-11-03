# Host upload parity repair — revision 3

Owner: Integration_Agent. Date: 2026-11-03. Scope is host application code and inert tests only. No firmware source, model, pin, NVS setting, compiler, package, COM device, Wi-Fi interface or service was operated or changed by this worker.

## Cause and corrected behavior

Both Expert and Simple Hub classified every workflow hotspot as the older dedicated Dataset image. After flashing, they intentionally skipped COM reconnection/readback and showed instructions claiming no native serial loop. This obsolete classification contradicted the additive final firmware.

Only the exact three final environments (`gld_model_[123]_dataset_workflow_wifi`) whose validated manifest has boolean `capabilities.nativeSerial === true` now follow native COM completion:

- Expert reconnects COM through its existing connection function, then waits at most 35 seconds for the fresh GET_INFO snapshot requested by that connection. It checks exact firmware version and the preserved target device ID before reporting completion/closing the dialog. Missing COM, missing readback, wrong version or wrong ID produces an explicit error that distinguishes a completed flash from failed verification.
- Simple Hub uses its existing `wait_for_readback(..., timeout=35.0)` and exact version/identity checks. Its ordinary successful readback response drives the existing Simple Hub verified flow, so no Simple Hub JavaScript change was needed.
- Unflagged workflow packages, stage 1 and replay packages retain their existing hotspot-only receipt and no automatic COM reconnect. Truthy strings cannot enable the capability. Normal firmware keeps its prior flow.
- The existing Reset NVS OFF and no-initial-firmware restrictions remain before all flashing/device actions. Existing Dataset/COM ownership exclusions were not modified.
- Expert cache references were bumped. The approved three final dropdown labels and all legacy API/package identities were preserved.

The root worker separately owns capability stamping, strict manifest schema validation and package revalidation. This host patch requires that package work and an idle-safe runtime reload before live use; it does not prove the installed application or GLD already runs this revision.

## Files changed

- `apps/gld-operator/js/firmware.js`
- `apps/gld-operator/js/main.js` and `apps/gld-operator/index.html` (cache references only in this revision)
- `apps/operator-hub/bridge.py` (capability-gated completion branch only in this revision)
- `apps/operator-hub/tests/test_native_workflow_upload.py` (new actual-handler tests)
- `apps/operator-hub/tests/test_native_workflow_upload_ui.cjs` (new actual Expert upload-action tests)
- `apps/operator-hub/tests/test_wireless_package_selection.cjs` (two obsolete visibility assertions updated to the already approved hidden legacy choices; its legacy routing/receipt coverage remains intact)

## Verification

Passed using inert mocks/COM999; no flash process or serial API was invoked:

- Native upload Python: 5 tests with Model 1/2/3, legacy/absent/string/false capability, wrong version/ID, normal model and reset/initial restriction subcases.
- Native Expert upload CJS: actual full upload action for all three capable workflows, fresh delayed GET_INFO, exact version/ID mismatches, bounded missing-readback timeout, reconnect failure, legacy and normal paths, and reset rejection before upload/disconnect.
- Existing wireless selection Python: 18 tests.
- Existing board/package selection Python: 28 tests.
- Existing workflow route/admission Python: 4 tests.
- Existing normal Model 2/3 Expert and Simple Hub upload CJS: PASS.
- Existing stage 1/replay upload/receipt/selector CJS: PASS after aligning stale visibility assertions with the approved dropdown cleanup.
- Scoped `git diff --check`: PASS.

These tests validate actual host branch behavior against mocked child/serial responses. They do not prove real firmware upload, GPIO/alarm, Wi-Fi, NVS retention, COM boot timing or actual device readback.

## Frozen SHA-256

| File | SHA-256 |
| --- | --- |
| Expert `firmware.js` | `3e7908c8448d24e9396195ce493029e19b62cb1c7be4113672aff5ea3690c71c` |
| Expert `main.js` | `bc6dcf72ac025fe3b5659bd71285cce4aab0cab6fb33f6bda2932e36420b08c0` |
| Expert `index.html` | `a662061442083355001dd1fe801aafce8f46aa2babe5b4a1f702d824f761cae5` |
| Simple Hub `bridge.py` | `2d884f772bb651de6bedeb2f85d9d16d48c6a54f119df17e7f782ef1fab8f85e` |
| Native Python test | `a8eb7fde988595a6fa2f3cc101ca3da7a873e9bd7cf7201fca761a85501975e1` |
| Native Expert CJS test | `3508a30c10524b9ff9a979239834d0f231380f1fad469aabdde911b920e954ec` |
| Legacy wireless CJS test | `f9538957fa92f5796fa3b0e55a61776dab0cbaf89c3ea8451ae21f9505915a36` |
