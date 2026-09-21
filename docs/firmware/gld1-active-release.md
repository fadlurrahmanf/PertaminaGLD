# GLD1 active release: v0.8.38 / 69a493c + alarm + Board 1 model v2

Baseline activated 2026-09-16 18:24 WIB. Board 1 / Model 1 refreshed 2026-09-21 17:28 WIB from the user-supplied `BOARD GLD 1.zip`.

The installed Operator Hub packages are **v0.8.38** for both `gld/latest` and `gld_model_1/latest`. Source baseline is `69a493c32d2500134a21e029820cd4addea1794a` (18 August 2026), plus the approved GPIO41/J2 alarm. Nulling retains original **5 ms settle and no 30-second nulling warm-up**; ADC/DAC/runtime code remains the baseline. Settle is not total nulling duration. This update replaces only Model 1 weights, normalization, sensitivity table and model metadata, plus packaging provenance.

## Current Model 1

- Source: `C:/Users/MSI/Downloads/BOARD GLD 1.zip`; archive SHA-256 `c25536cd250e71cf7afd661a3bd47721a77d2a7c9fc6de2dc810121450943c16`.
- INT8 dual input: 8 ADC + 7 derived evidence values. **Two output classes: Clean_Air, LPG**, mapped to protocol CLEAR=0 and LPG=1. It no longer has dedicated H2/CO2 outputs; do not infer other-gas recognition from this model.
- Model and scaler profile: `cnn-dualbranch-board-1-2class-v2`. Firmware version stays 0.8.38; the new model profile and package hashes identify this refresh and invalidate old binding.
- Embedded model: 9,632 bytes; SHA-256 `6de1521a995163fcdb1aab31dbb2cad234af6c18c36bdaa1761fd5cc339d4f37`.
- The three runtime headers in both the main slot and the release worktree match the ZIP byte-for-byte (canonical destination filenames retained). `.keras`, notebooks and CSV are training/reference artifacts and are not compiled into firmware.
- Each package includes `model-provenance.json` with model/source/scaler/table/app hashes. This audit sidecar is not flashed; the strict schema-v2 upload manifest remains unchanged.

## Upload and migration

1. Open/reopen Operator Hub, then refresh the Hub/GLD Expert page (Ctrl+F5).
2. Select **GLD1 / Model 1 / v0.8.38**. In Expert, GLD1 plus Model 1 intentionally resolves to `gld_model_1`; both package variants are this same approved release.
3. Read the warning and explicitly check **Reset NVS**. Save any configuration/provisioning details needed beforehand. This resets configuration, nulling and binding; the default device ID is 1001.
4. Upload yourself. Restore the correct configuration, perform full nulling in confirmed clean air with 8/8 pass, then bind Model 1. Do not consider upload completion evidence of operational gas-detection readiness.
5. Check the boot log for **Firmware version: 0.8.38** and **GLD1_BASE_COMMIT=69a493c**.

The original unversioned 92-byte nulling profile can accept a newer 92-byte profile with shifted DAC values. The active child GLD bridge therefore enforces consent and the exact baseline NVS region before serial interaction. For only `gld` or `gld_model_1`, version 0.8.38, source commit 69a493c..., upload order is:

- Erase verified NVS (0x9000 / 0x5000), with a 45-second bound and `--after no_reset`.
- Only after successful erase, write firmware using `--before no_reset`.
- Normal hard reset occurs only after successful flash. Erase failure means no downgrade was written; flash failure cannot report success.
- Other packages retain their existing upload/reset behavior. Explicitly choosing Reset NVS authorizes configuration loss even if later flashing fails; recovery may require another upload.

## Alarm

GPIO41 HIGH sinks J2 LAMP LOW normally; GPIO41 LOW releases J2 so a suitable external pull-up provides continuous HIGH during alarm. GPIO40 is unused. AUTO follows current valid inference; MANUAL is session-only. Neither a stored boot latch nor retry of an old radio alarm replays a stale physical alarm. Actual trigger voltage/tolerance/loading remain hardware checks; firmware cannot suppress possible J2 HIGH during reset before setup.

## Source, backups and verification

- Rebuild worktree: `D:/Github/PertaminaGLD-GLD1-69a493c`, branch `codex/gld1-69a493c-alarm`.
- [Rebuild and detailed release instructions](D:/Github/PertaminaGLD-GLD1-69a493c/GLD1-BASELINE-RELEASE.md).
- Main workspace firmware was deliberately not rolled back. **Do not rebuild this release from main firmware/**.
- Previous v0.8.37 packages remain recoverable under `D:/Github/PertaminaGLD-GLD1-69a493c/release-backup/pre-rollback-v0.8.37/`.
- Previous Model 1 headers and both packages were backed up under `D:/Github/PertaminaGLD/tmp/model1-20260921/` (`main-model1-before`, `release-model1-before`, `package-gld-before`, `package-gld_model_1-before`).
- Each app binary is 1,021,216 bytes; RAM 134,056/327,680; flash app usage 1,020,837/6,553,600. Both builds passed.
- Actual release TFLM library + unchanged NeuralNetwork code passed AllocateTensors and Invoke on four synthetic vectors with the existing 40 KiB arena. FlatBuffer structure, INT8 inputs 8+7, two outputs and class mapping passed. This is host compatibility evidence, not board/gas accuracy evidence.
- Host alarm/parser/startup/baseline tests, 68 Operator Hub tests and executable Expert/Simple Hub UI regressions passed.
- Actual upload validator, manifest/four-file hashes, build equality, embedded new model/profile and exact ZIP artifact checks passed. Real HTTP handlers served both new packages, and Simple Hub's proxy fetched Model 1. The existing reset guard still recognizes both packages.
- Operator Hub was not running at verification time. HTTP smoke tests used temporary loopback servers and closed them afterward; no persistent app processes were started/restarted.
- All 995 protected main firmware/other package files retained their task-start hashes. Of 867 protected release firmware files, only the approved packaging hook and baseline-test allowlist changed; runtime/alarm/nulling code did not.
- Repeat model/package/HTTP verification: `C:/Users/MSI/.platformio/penv/Scripts/python.exe tmp/model1-20260921/verify_model_release.py --http-smoke` from the main workspace. Host inference test: `tmp/model1-20260921/host_model_test.py`.

| Package | Firmware SHA-256 |
|---|---|
| gld | e7ea240274cc210cf3078a37fbcd10289f36b2718881633ef962785dece35e92 |
| gld_model_1 | d1590f2d08f6af4465b4208a7478e8ec8f901bb95a0c5b5d17e9548c8e35cc94 |

Historical baseline activation logs (2026-09-16, not current process state): `D:/Github/PertaminaGLD-GLD1-69a493c/tmp/operator-activation/`.

No actual firmware upload, NVS erase, serial command, board reset, physical gas test, or J2 voltage measurement was performed. Host inference and HTTP/package checks do not prove physical upload sequencing or hardware operation. No commit/push was performed.
