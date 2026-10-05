# GLD1 active release: v0.8.38 / 69a493c + GPIO48 alarm + Models 1, 2 and 3

Baseline activated 2026-09-16 18:24 WIB. Board 1 / Model 1 refreshed 2026-09-21 17:28 WIB from the user-supplied `BOARD GLD 1.zip`.

The installed Operator Hub packages are **v0.8.38** for `gld/latest`, `gld_model_1/latest`, `gld_model_2/latest`, and `gld_model_3/latest`, rebuilt on **2026-10-05 for direct GPIO48 alarm**. Source baseline is `69a493c32d2500134a21e029820cd4addea1794a` (18 August 2026). Nulling retains original **5 ms settle and no 30-second nulling warm-up**; ADC/DAC/runtime and model artifacts are unchanged. Settle is not total nulling duration. Version stays 0.8.38 to preserve the exact-baseline NVS migration guard.

Model 3 / Board 3 was published on 2026-09-29 from `BOARD GLD 3.zip`, with explicit user approval for this baseline and inference for board testing after nulling/bind. Model 1 and all other packages were unchanged by that refresh. See [Model 3 release and verification](gld-model-3-release.md); it has two classes and profile `cnn-dualbranch-board-3-2class-v1`.

Model 2 / Board 2 was aligned on 2026-10-01 from `C:/Users/MSI/Downloads/ModelGLD/BOARD GLD1 Model 2.zip`: two classes `Clean_Air, LPG`, profile `cnn-dualbranch-board-2-2class-v2`, ZIP SHA-256 `a82b55f0747e99ee8c6e5e7b76c78a2cb706582f1454418e3a75e98ed90a26f5`, and model SHA-256 `ba5caab562c87fabfe76b87540f86a3fbe55fc82320242e205bed0abf5f05230`. Its package is uploadable and provenance-verified, but inference/bind is intentionally fail-closed pending board/gas validation and explicit approval. This differs from Model 2's prior four-class v0.8.34 package.

## Current Model 1

- Source: `C:/Users/MSI/Downloads/BOARD GLD 1.zip`; archive SHA-256 `c25536cd250e71cf7afd661a3bd47721a77d2a7c9fc6de2dc810121450943c16`.
- INT8 dual input: 8 ADC + 7 derived evidence values. **Two output classes: Clean_Air, LPG**, mapped to protocol CLEAR=0 and LPG=1. It no longer has dedicated H2/CO2 outputs; do not infer other-gas recognition from this model.
- Model and scaler profile: `cnn-dualbranch-board-1-2class-v2`. Firmware version stays 0.8.38; the new model profile and package hashes identify this refresh and invalidate old binding.
- Embedded model: 9,632 bytes; SHA-256 `6de1521a995163fcdb1aab31dbb2cad234af6c18c36bdaa1761fd5cc339d4f37`.
- The three runtime headers in both the main slot and the release worktree match the ZIP byte-for-byte (canonical destination filenames retained). `.keras`, notebooks and CSV are training/reference artifacts and are not compiled into firmware.
- Each package includes `model-provenance.json` with model/source/scaler/table/app hashes. This audit sidecar is not flashed; the strict schema-v2 upload manifest remains unchanged.

## Upload and migration

1. Open/reopen Operator Hub, then refresh the Hub/GLD Expert page (Ctrl+F5).
2. Select **GLD1 / Model 1, Model 2 or Model 3 / v0.8.38**, matching the intended board. Expert resolves these to `gld_model_1`, `gld_model_2` or `gld_model_3`; legacy `gld` contains Model 1. Model 2 must not be treated as inference-ready until its separate approval gate is opened.
3. Read the warning and explicitly check **Reset NVS**. Save any configuration/provisioning details needed beforehand. This resets configuration, nulling and binding; the default device ID is 1001.
4. Upload yourself. Restore the correct configuration and perform full nulling in confirmed clean air with 8/8 pass. Model 1/3 can then be bound according to their existing approvals; the current Model 2 build intentionally refuses bind/inference until its separate board/gas validation and approval. Do not consider upload completion evidence of operational gas-detection readiness.
5. Check the boot log for **Firmware version: 0.8.38** and **GLD1_BASE_COMMIT=69a493c**.

The original unversioned 92-byte nulling profile can accept a newer 92-byte profile with shifted DAC values. The active child GLD bridge therefore enforces consent and the exact baseline NVS region before serial interaction. For only `gld`, `gld_model_1`, `gld_model_2`, or `gld_model_3`, version 0.8.38, source commit 69a493c..., upload order is:

- Erase verified NVS (0x9000 / 0x5000), with a 45-second bound and `--after no_reset`.
- Only after successful erase, write firmware using `--before no_reset`.
- Normal hard reset occurs only after successful flash. Erase failure means no downgrade was written; flash failure cannot report success.
- Other packages retain their existing upload/reset behavior. Explicitly choosing Reset NVS authorizes configuration loss even if later flashing fails; recovery may require another upload.

## Alarm

GPIO48 is a direct logic trigger: **HIGH continuously during alarm, LOW normally**. Firmware preloads LOW before enabling OUTPUT at startup. GPIO17/40/41 are no longer alarm outputs. AUTO follows current valid inference; MANUAL remains session-only. Neither a stored boot latch nor retry of an old radio alarm replays a stale physical alarm. In the archived original GLD1 PCB, GPIO48 is U49 pad25 and is not routed to J2; the trigger wire must be connected to GPIO48, not the old ULN2003 J2 output. Actual voltage, load compatibility and levels before firmware starts remain unverified hardware checks.

The GPIO48 firmware packages are ready for the existing upload route. Operator Hub/Expert application files have not been changed: the Simple Hub manual-alarm validator does not yet recognize `active_high_gpio48_steady`, and Expert's legacy fallback description is not valid for this new output. UI alignment awaits explicit scope approval; AUTO inference alarm operation does not depend on those controls.

2026-09-30 verification: all three GLD1 builds passed (1,021,168-byte application binaries); startup, steady output, AUTO/MANUAL and invalid-inference host tests passed. Non-GLD1 preprocessed source remained identical. Strict upload validators accepted the manifest/four flash files, package binaries matched build output, unchanged model provenance/embedded model matched, and NVS migration guard remained active. No COM, physical upload, reset or hardware test. Task-start source/package backups: `tmp/gld1-gpio17-20260930/before/`. Repeat package checks: `C:/Users/MSI/.platformio/penv/Scripts/python.exe tmp/gld1-gpio17-20260930/verify_release.py --published`.

## Source, backups and verification

The detailed verification counts below are the 2026-09-21 Model 1 snapshot, not a new claim about current running processes. Model 3's 2026-09-29 evidence and backups are recorded in its linked release note above.

- Rebuild worktree: `D:/Github/PertaminaGLD-GLD1-69a493c`, branch `codex/gld1-69a493c-alarm`.
- [Rebuild and detailed release instructions](D:/Github/PertaminaGLD-GLD1-69a493c/GLD1-BASELINE-RELEASE.md).
- Main workspace firmware was deliberately not rolled back. **Do not rebuild this release from main firmware/**.
- Previous v0.8.37 packages remain recoverable under `D:/Github/PertaminaGLD-GLD1-69a493c/release-backup/pre-rollback-v0.8.37/`.
- Previous Model 1 headers and both packages were backed up under `D:/Github/PertaminaGLD/tmp/model1-20260921/` (`main-model1-before`, `release-model1-before`, `package-gld-before`, `package-gld_model_1-before`).
- Previous Model 2 source/package and the supplied ZIP extraction are backed up under `D:/Github/PertaminaGLD/tmp/model2-20261001/`.
- Each app binary is 1,021,216 bytes; RAM 134,056/327,680; flash app usage 1,020,837/6,553,600. Both builds passed.
- Actual release TFLM library + unchanged NeuralNetwork code passed AllocateTensors and Invoke on four synthetic vectors with the existing 40 KiB arena. FlatBuffer structure, INT8 inputs 8+7, two outputs and class mapping passed. This is host compatibility evidence, not board/gas accuracy evidence.
- Host alarm/parser/startup/baseline tests, 68 Operator Hub tests and executable Expert/Simple Hub UI regressions passed.
- Actual upload validator, manifest/four-file hashes, build equality, embedded new model/profile and exact ZIP artifact checks passed. Real HTTP handlers served both new packages, and Simple Hub's proxy fetched Model 1. The existing reset guard still recognizes both packages.
- Operator Hub was not running at verification time. HTTP smoke tests used temporary loopback servers and closed them afterward; no persistent app processes were started/restarted.
- All 995 protected main firmware/other package files retained their task-start hashes. Of 867 protected release firmware files, only the approved packaging hook and baseline-test allowlist changed; runtime/alarm/nulling code did not.
- Repeat model/package/HTTP verification: `C:/Users/MSI/.platformio/penv/Scripts/python.exe tmp/model1-20260921/verify_model_release.py --http-smoke` from the main workspace. Host inference test: `tmp/model1-20260921/host_model_test.py`.

| Package | Firmware SHA-256 |
|---|---|
| gld | 1027191e18f33b2c9dcdfa5eed7b28725de63192f7e8fc12e1ad17927555073a |
| gld_model_1 | d18d661c929643816c530910750b5995862ceaa5a6aa61f587184ff69ed56632 |
| gld_model_2 | c09d8538baf0d0402f52eb3b8ec5c1d6dc1ffa6447cbd37a8304a0dcb0220314 |
| gld_model_3 | ea8d2eaf86884e8330ce71a3e57f3125947ae8d85a69e820f2719b62bc4baefe |

Historical baseline activation logs (2026-09-16, not current process state): `D:/Github/PertaminaGLD-GLD1-69a493c/tmp/operator-activation/`.

No actual firmware upload, NVS erase, serial command, board reset, physical gas test, or J2 voltage measurement was performed. Host inference and HTTP/package checks do not prove physical upload sequencing or hardware operation. No commit/push was performed.
