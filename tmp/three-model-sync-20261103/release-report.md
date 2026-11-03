# Three-model feature parity release

Completed 2026-11-03 16:26:31 Asia/Jakarta.

All three final Hotspot Wizard Dataset packages rebuilt by three compiler agents with 428.110326 seconds of simultaneous real compiler execution. No compiler warnings or actual errors. Two decorative star banners in each raw receipt were classified separately, not hidden.

|Model|Firmware SHA-256|
|---|---|
|1|`a2a74b5180aa8bd38984d7fb01a9b5722e41e011d937ed3bb98740cb724c70c2`|
|2|`c1b7028ca90670f3808d091732817b56f415eac7a6823ca7d508a60e521f4228`|
|3|`21ab4674d009cf1d4d7c7e61c5a1db2a5eecd91d924145e2a504f31946c1ef76`|

## Shared feature result

- Models1/2/3 use the same native COM, nulling/binding/QC/alarm/LoRa controls and Wi-Fi eight-sensor/500ms Dataset, compact CSV, Pause/Resume/Stop/Continue and RAM replay paths. Model weights/scalers/class map remain model-specific. Shared resource ownership remains unchanged; close/finalize/disconnect wireless recording before configuration mutations.
- All three binaries contain the same 16 required feature/control markers and no non-production Bind rejection. The shared runtime and calibration/pin/NVS code were not edited. Approval is true for all three source metadata profiles.
- Model2 activation follows explicit operator-reported board/gas validation and authorization dated2026-11-03, recorded in model.json. Agent did not perform new gas validation.
- Running and Expert use one common binding evaluator. Green requires approved model, matching model identity, valid positive bound/active profile IDs that are equal, and no explicit not-ready flag. Missing legacy metadata remains unknown.
- Strict child/Hub/preflight, exact model blob, preserved partition/NVS sectors and credential consistency validations passed. Seven files per package published after all three staged; previous final packages archived under previous-20261103-before-feature-parity. Served API manifests and every flash-file hash match the new bytes; all three share the same firmware tree snapshot.
- 313 protected source/package files remain unchanged. Model2 weights, scaler, profile IDs and class map remain unchanged; only its approval metadata changed by authorization. Normal firmware package directories were retained.
- Root reran51policy/source/replay/credentials and105Hub checks plus actual shared-binding JS, Running chart and workflowUI tests. Live served ESmodule browser policy passed all3models; a fresh full UI selected Model2 with new firmware hash and no JS errors.

## Device handoff

No device upload, Bind/NVS write, calibration/reset or Hub launch/restart performed by this release. Existing Hub remains user-accessible; future launches must use a visible terminal as requested.

For current GLD1002: refresh browser, upload GLD1 Model2 Hotspot Wizard Dataset with ResetNVS OFF and24V, confirm fresh GET_STATUS reports productionApproved=true and active profile still2. In Running Settings choose Use Latest Nulling Profile and explicitly confirm the NVS binding. Then Refresh Status: bindingValid/bindingModelMatches/profileReady should be true, bound and active IDs equal, followed by inferenceValid on a valid new sensor frame. Do not treat this package-release proof as physical upload or inference proof.

The previously observed running unit was Model2 unapproved with boundprofile1/active2; this runtime remains unchanged until the user uploads the new image and explicitly binds. The single binding record refers to the installed model, not three models simultaneously.
