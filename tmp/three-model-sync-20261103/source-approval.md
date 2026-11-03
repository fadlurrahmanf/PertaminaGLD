# Model 2 approval activation and three-model policy — 3 November 2026

Status: **source frozen and ready for the parent's three parallel builds**. This agent performed no compile, package mutation, upload, hardware/COM, network or service action, and no binding/NVS operation.

## Approval evidence

The user explicitly reported completed board/gas validation and authorized activation: **“Sudah divalidasi; setuju aktifkan”**, dated 2026-11-03. This is operator-reported evidence. The agent did not perform or independently certify a gas test. `model_2/model.json` records that distinction in structured `productionApproval` provenance.

`model_2/ModelMetadata.h` now sets `PRODUCTION_APPROVED=true`. The prior pending-approval comments and obsolete model.json upload/reset note were replaced with current operator approval and the unchanged requirement for a complete applied nulling profile and explicit matching binding. No reset or auto-bind is introduced. Models 1 and 3 were already approved; all three now use the same existing explicit-bind and inference-readiness policies.

## Frozen changed source files

| File | SHA-256 |
|---|---|
| `firmware/gld/models/model_2/ModelMetadata.h` | `72d43bc0a2af46b256a3e80e00904224ae3d33f536d77d3b7b6c1604526a8cdb` |
| `firmware/gld/models/model_2/model.json` | `9c648431a6108826823e8ca50af65c11a7608bf077ac06bd74c1376e574804be` |
| `firmware/tests/test_three_model_sync_policy.py` | `bdbaba0744bbe84e7ce00f1ad3d9e63f3e22f092ee3bd90538f23b7dff5b3d9a` |

These are the only firmware/test files changed by this revision/agent. This report is the sole additional audit artifact written by this revision. Shared runtime, all binding guards, NVS layout, calibration and pin code, PlatformIO environments, Models 1/3, Model 2 weights/scaler/sensor table, profile IDs, class map, and all existing packages are unchanged.

Protected Model 2 inputs remain:

- NN model-data header: `08b1ca9c19d5e0203a3431d67ed137b5f898a23a37432f1d46e2d31955191b7b`.
- Scaler header: `9c1e401c2861d940d921e1e083ecd5fe07fd0610b31b890afe3df3cac58fba97`.
- Sensor sensitivity table: `6f8bf32caaff031cf422b42db4889b34a2a9d211977fd47e1ee6eb48f134cefd`.
- Model/scaler names both remain `cnn-dualbranch-board-2-2class-v2`; fingerprint remains `c95e51df`; ADC8 + evidence7 → 2 outputs and CLEAR/LPG class map remain unchanged.

## Verification

With `C:/Users/MSI/.platformio/penv/Scripts/python.exe` from the repository:

```text
-m unittest firmware.tests.test_three_model_sync_policy firmware.tests.test_dataset_workflow_source firmware.tests.test_dataset_replay_source firmware.tests.test_dataset_workflow_credentials -q
Ran 51 tests in 0.463s — OK
```

The four new policy gates cover: explicit operator approval provenance; unchanged Model 2 binary/scaler/table identities and profile/class mapping; all three approved models sharing byte-identical NeuralNetwork engines and matching workflow environments; shared approval, stable profile, model fingerprint, applied profile, DAC and explicit-only binding gates without startup/scan/Wi-Fi auto-bind or direct calibration/mode/alarm side effects.

`git diff --check` passed for the two modified metadata files (only normal LF-to-CRLF notices). Compared all **378** entries in the parent's `protected-before.json`: exactly the two authorized Model 2 metadata files differ; **376** protected files remain identical; **zero unexpected changes**. The 51 tests also retain the previous normal-source/environment isolation and 233-file protected workflow/package/CSV baseline checks.

## Device synchronization after a verified authorized release

The currently running GLD1002 still has the prior firmware until a separate upload. Its old binding points to profile 1 while the applied complete profile is 2, and its saved fingerprint does not match the currently installed Model 2. Approval activation alone does not fix either binding mismatch and does not rewrite device storage.

After the parent completes three parallel builds, verifies the three final packages and performs any separately authorized upload with Reset NVS OFF, read fresh status. If the intended Model 2, applied valid complete profile 2 and other readiness gates are confirmed, an explicit authorized **Use Latest Nulling Profile** action can update only the binding record. Require ACK and fresh status with matching fingerprint and `boundNullingProfileId==activeNullingProfileId`, then a valid normal inference. Do not auto-bind, re-null, reset NVS or change models merely to align indicators.

Source/host verification does not prove compiled binaries, target runtime timing, physical alarm behavior or gas accuracy. The parent's build/package/device validation remains the next gate; any later source edit invalidates these source hashes.
