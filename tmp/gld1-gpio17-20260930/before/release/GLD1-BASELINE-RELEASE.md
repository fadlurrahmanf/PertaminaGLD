# GLD1 v0.8.38: 69a493c + GPIO41/J2 alarm + Models 1 and 3

## Model 3 addition: 2026-09-29

With explicit user approval, built and published **only `gld_model_3`** from `BOARD GLD 3.zip` on this same v0.8.38 baseline. Model 1/2 and other packages were not rebuilt. Model/scaler profile is `cnn-dualbranch-board-3-2class-v1`, classes `Clean_Air, LPG` -> `{0, 1}`. Inference is approved for board testing after full nulling and bind; this does not establish field accuracy. Runtime/nulling/alarm code remains unchanged. Model3 migrated from v0.8.34, with the exact-baseline NVS guard extended to this environment in the main Expert/Hub.

Firmware SHA-256: `a9cf9cde9d5507b21ae05513d4638d4e10f200d5099e8ebfb23d9773edaed81a`. Model SHA-256: `ec636bb559dec26acdf5d5ebe3a4f75dc6644023d9e483b42b1e53d9518c9890`. Build, original baseline/alarm checks, 68 Hub tests, executable UI tests, strict package validators, exact ZIP headers, host TFLM Invoke and actual temporary-loopback HTTP/package proxy passed. No COM, physical flash, reset, gas test or persistent service restart was performed. Details: `D:/Github/PertaminaGLD/docs/firmware/gld-model-3-release.md`; backups/evidence: `D:/Github/PertaminaGLD/tmp/model3-20260929/`. Rebuild this slot with `platformio run -d firmware -e gld_model_3 -j 1` using the runtime/temp setup below; do not rebuild from main firmware.

## Model 1 release history: 2026-09-16 and 2026-09-21

Built and validated 2026-09-16 18:06 WIB; **published to the active Operator Hub on 2026-09-16 18:24 WIB** after the user authorized the safe-downgrade upload guard.

Model-only refresh published to both active packages on **2026-09-21 17:28 WIB** from `C:/Users/MSI/Downloads/BOARD GLD 1.zip`. Both builds passed (gld 25.609 s; gld_model_1 25.601 s). Each binary is 1,021,216 bytes; RAM 134,056/327,680 bytes, flash application usage 1,020,837/6,553,600 bytes. Host alarm/parser/handler/startup/baseline tests, 68 current Hub tests, executable Expert/Simple Hub UI regressions, actual child package-validator checks, all flash-file hashes, binary/build equality and expected/absent binary markers passed. Actual TFLM host AllocateTensors/Invoke passed four synthetic vectors in the existing 40 KiB arena; no runtime hardware/gas accuracy proof is claimed.

Model 1 now has two outputs in order `Clean_Air, LPG`, mapped to protocol `{0, 1}`. Weights, normalization and sensitivity headers match the user ZIP. Profile/scaler ID is `cnn-dualbranch-board-1-2class-v2`; embedded INT8 model SHA-256 is `6de1521a995163fcdb1aab31dbb2cad234af6c18c36bdaa1761fd5cc339d4f37` (9,632 bytes). `.keras` and training/reference files are not firmware inputs. Firmware version remains 0.8.38 so the existing exact-baseline NVS guard remains active. The new profile invalidates old model binding.

| Published package | Firmware SHA-256 |
|---|---|
| gld | e7ea240274cc210cf3078a37fbcd10289f36b2718881633ef962785dece35e92 |
| gld_model_1 | d1590f2d08f6af4465b4208a7478e8ec8f901bb95a0c5b5d17e9548c8e35cc94 |

Main active packages are v0.8.38 and match these build outputs. Previous v0.8.37 packages are preserved at `release-backup/pre-rollback-v0.8.37/`. Pre-model-refresh artifacts/packages are backed up in `D:/Github/PertaminaGLD/tmp/model1-20260921/`. Main `models/model_1` is updated to the same source; main runtime and all protected GLD2/GLD3/Model2/3 files are unchanged. Run `verify_gld1_release.py` here to repeat package validation using the current main bridge. Model/source/binary hashes are in each package's non-flashed `model-provenance.json`; the strict upload-manifest schema is unchanged. HTTP handlers and Simple Hub package proxy passed temporary-loopback testing; no persistent app service was running or started during this refresh.

## Required BEFORE the first upload of this rollback

**Use the updated main Operator Hub only.** The activated bridge enforces explicit reset consent and erases verified NVS before writing the downgrade, keeping the chip in bootloader between those operations. Do not use an older unguarded app or this historical worktree application.

**Check Reset NVS in Operator Hub. Do not upload this downgrade while retaining a profile from a newer firmware.**

The original 69a493c nulling profile has no algorithmVersion field. Newer profiles have the same stored size but a shifted DAC array, so this firmware can accept a newer profile with incorrect DAC values. This exact-baseline release intentionally does not import a new profile schema or migration algorithm. The Hub checkbox remains operator-controlled; firmware/package validation does not erase NVS for you.

Implemented upload guard: recognize only `gld`, `gld_model_1`, or `gld_model_3`, version `0.8.38`, source commit `69a493c32d2500134a21e029820cd4addea1794a`; require boolean reset consent and `RESET NVS` confirmation before serial access. Pre-erase only the verified 0x9000/0x5000 NVS region with `--after no_reset`, bounded to 45 seconds; then write firmware using `--before no_reset`, with the normal reset only after successful flash. Erase failure means the downgrade was not written. Flash failure after erase leaves configuration erased and requires recovery; it cannot report success. The child bridge enforces this for both Hub and Expert. The UI requires explicit checkbox consent and retains a setup/nulling/binding reminder; AES reprovisioning remains unchanged. Other packages keep their existing behavior. Mocked backend and executable UI regressions passed; no hardware flashing was performed. The 2026-09-16 live service checks are historical; the later model refreshes used temporary loopback servers and did not start persistent services.

Record device ID, target CH, radio/network settings and provisioning beforehand. Reset NVS erases saved configuration, nulling and model binding; boot defaults include GLD ID 1001. Restore the correct configuration/security provisioning after upload. Run full nulling in confirmed clean air, require 8/8 pass, then explicitly bind the selected model. This sequence alone does not prove gas-detection accuracy; complete board/gas acceptance before operational use.

## Scope

- Baseline commit: `69a493c32d2500134a21e029820cd4addea1794a` (18 August 2026).
- Original nulling: settle 5 ms; no 30-second nulling warm-up; no newer stability-window algorithm. ADC acquisition and other original waits remain, so this is not a 5 ms total nulling duration guarantee.
- Original ADC, DAC, I2C, classifier runtime, profile storage, radio and build configuration retained. Model 1 weights/scalers/sensitivity/class metadata are the approved 2026-09-21 user ZIP refresh; Model 3 is the approved 2026-09-29 refresh described above.
- Alarm: GPIO41 HIGH sinks J2 LAMP LOW normally. GPIO41 LOW releases J2 during alarm; a suitable external pull-up supplies continuous J2 HIGH. GPIO40 unused. AUTO follows valid current inference; MANUAL is session-only and resets to AUTO at boot. A persisted radio retry does not replay a stale physical alarm.
- Firmware cannot suppress a possible J2 pull-up HIGH before setup runs during reset. Pull-up voltage, trigger tolerance/loading and actual voltage remain hardware checks.
- Approved GLD1 builds: `gld`, `gld_model_1`, and (since 2026-09-29) `gld_model_3`. Build/publish only the slot the user requests. Do not build/publish GLD2, GLD3 or Model 2 from this rollback worktree without a separate user decision.

## Rebuild

Source worktree: `D:/Github/PertaminaGLD-GLD1-69a493c`, branch `codex/gld1-69a493c-alarm`. Main workspace source is intentionally not rolled back. Changes remain local, not committed/pushed by this task.

```powershell
Set-Location D:\Github\PertaminaGLD-GLD1-69a493c
$taskBuildTemp = Join-Path $PWD "tmp\platformio-temp"
New-Item -ItemType Directory -Path $taskBuildTemp -Force | Out-Null
$env:TEMP = $taskBuildTemp
$env:TMP = $taskBuildTemp
& C:\Users\MSI\.platformio\penv\Scripts\python.exe firmware/gld/tests/test_69a_alarm_baseline.py
& C:\Users\MSI\.platformio\penv\Scripts\platformio.exe run -d firmware -e gld -e gld_model_1 -j 1
```

Use the current main Operator Hub, not the historical application from this worktree. Package post-build metadata records base commit plus dirty firmware snapshot, isolated version, and flash-file hashes. The package baud is 921600, matching the unchanged PlatformIO upload_speed; historical package-hook metadata used 460800.

After user upload, verify **Firmware version: 0.8.38** and **GLD1_BASE_COMMIT=69a493c** in the boot log. Selecting an upload package alone does not establish which firmware is running.

No COM access, flash, reset, service restart or hardware validation is performed by building this release. Build/package tests do not prove physical nulling duration, sensor accuracy or J2 voltage.
