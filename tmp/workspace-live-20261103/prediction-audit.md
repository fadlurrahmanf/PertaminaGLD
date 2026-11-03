# Prediction audit revision 3 — real Model1 device

## Deterministic cause found

The workflow-specific ML initialization checks the wrong input width.

`firmware/gld/src/GldUnifiedMain.cpp:7357-7359`:

```cpp
mlReady = network != nullptr && network->isInitialized() &&
    network->getInputSize() == pgl::gld::model::EXPECTED_ADC_INPUT_ELEMENTS &&
    network->getOutputSize() == pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS;
```

All three `firmware/gld/models/model_N/NeuralNetwork.cpp:258-264` implement `getInputSize()` as **ADC + evidence**, returning `8 + 7 = 15` when initialized or `0` when uninitialized. The workflow code requires **8**. Therefore this condition is false in either state, and `mlReady` is always false for these three workflow builds. `datasetWorkflowPredictionReady():7064` requires `mlReady`, causing `prediction_ready=false`, then the UI correctly disables Predicted Class + Confidence. It cannot recover after warmup, connection retry, or waiting.

This is a concrete source-contract mismatch, independently characterized across Model1/2/3. It is not necessary to assume broken calibration, model binding, or model allocation to explain the observed real-device failure. Other physical gates may still require proof after this mismatch is repaired.

## Minimal focused repair recommendation

Change ONLY the workflow-specific size comparison to the API's total input contract:

```cpp
network->getInputSize() ==
    pgl::gld::model::EXPECTED_ADC_INPUT_ELEMENTS +
    pgl::gld::model::EXPECTED_EVIDENCE_INPUT_ELEMENTS
```

Keep constructor/isInitialized/output size and all production/nulling/binding/DAC gates. Do not change shared `NeuralNetwork::getInputSize()`: production uses its existing 15-element meaning, and the constructor already validates the independent ADC=8/evidence=7/output=2 tensor shapes. Do not flip Model2 production approval.

A focused regression should characterize all three model APIs as total width15, show a correctly initialized15-input/two-output runtime can pass the workflow initialization gate, and show invalid dimensions/uninitialized runtime remain rejected. Re-run workflow source isolation and protected baseline checks; real prediction proof is still required after an explicitly authorized compile/upload.

## DAC-bypass hypothesis ruled out

- For this GLD1 board profile, `firmware/gld/include/BoardPins.h:250` sets HAS_PCF8574=false.
- `runtimeDacVerificationReady():5278-5283` returns true immediately when !HAS_PCF8574, so delayed normal-loop DAC verification cannot block this GLD1 image.
- Independently, Dataset setup calls `runExternalPowerBootSensorSamples(power):7349`, which calls `applySavedNullingProfileOnly():5446`; its per-channel readback records `recordRuntimeDacVerification(...):5378` before workflow ML initialization and AP begin. The dedicated loop bypass does not prevent that boot verification.

## Binding diagnostics remain valid but are secondary

The saved binding loads before hardware setup (`7135`), and workflow's prediction readiness recomputes fingerprint/profile checks directly (`7062-7069`), so it does not rely on stale `modelProfileReady`. The current HELLO does not expose mlReady/bindingValid/bindingModelMatches individually. Existing boot logs, if retained, expose `MODEL_NULLING_BIND_LOAD=... profileId=... fingerprint=...`; normal inference status also exposes those fields, but changing firmware/mode merely to probe is unnecessary to establish the proven input-width defect.

## Actual evidence and remaining gate

`real-browser/evidence.json`: actual Model1 profile `cnn-dualbranch-board-1-2class-v2`, production_approved=true, raw nulling_profile_id1, eight chart traces, eight readings, interval median500ms, direct and replay CSV/control cases passed, prediction.available=false/valid_samples0. Raw readiness proves its prerequisites, not ML readiness or binding. Expected prediction warmup is10samples(~5s) only after readiness passes.

This audit changed only this report. No firmware/source/test edits, build, upload, reset, COM access, WLAN access or service operations were performed by this worker.


## Revision 4 — minimal source repair applied

Parent explicitly assigned the workflow-only patch. `GldUnifiedMain.cpp` now compares `getInputSize()` against ADC+evidence (15), preserving isInitialized, output count and all prediction readiness gates. Shared model implementations and all non-workflow branches are unchanged.

Added one cross-model source-contract regression in `test_dataset_workflow_source.py`: it reads each actual model getter and metadata independently, evaluates the workflow caller condition, accepts initialized dual-input width15/output2, rejects null/uninitialized/ADC-only/wrong widths/wrong output. RED before patch: all three model subcases failed, reproducing the bug. GREEN after patch: 13 workflow source tests passed. Protected previous Replay/source/credential regressions passed18, and workflow credential tests passed7 (38 total). These checks are source/fixture evidence, not execution of compiled TFLite.

No compiler, packages, hardware, COM, network or service actions. Existing packages remain prior build until approved parallel compile/repackage/upload; initial preflight receipt-current-source result is now historical and intentionally superseded by this source patch.
