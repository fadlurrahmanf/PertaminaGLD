# GLD preflight revision 2 — 2026-11-03

Status: PASS for source, built-image identity, Hub packages and automatic credential resolution. Physical board identity/readiness is still unproved; this worker did not access hardware, COM ports, WLAN, services, or external sockets. No build, upload, reset or firmware edits.

## Accepted evidence

- All three successful build receipts still match their current public source hashes, unchanged before/after build. The four artifact flash images match their successful build files and recorded SHA-256. All seven Hub package files match their respective artifact copies; manifest SHA and each flash-file SHA are correct.
- Exact embedded source model/profile is present once in each respective image, with protocol3 and acquisition/replay command markers. Private matching credential configuration, generated header and image agree; secret is absent from plaintext metadata/logs. Automatic resolver validates all three dedicated model configurations and their equality; no secret returned or printed.
- 25 current checks pass: workflow source/isolation 12; workflow credential preparation 7; operator package provenance 1; app automatic credential resolver 5. These are PC/source/fixture checks, not physical proof.
- Firmware hashes and model profiles are in sibling gld-preflight.json.

## Firmware selection and readiness

Use only matching `gld_model_{1,2,3}_dataset_workflow_wifi` / Hotspot Wizard Dataset package for actual UI. Plain Stage1 protocol1 and Replay protocol2 packages do not implement this protocol3 UI. Runtime version 0.8.36 alone does not distinguish them.

- Raw ready requires external 24V (including ST_P power reading), ADS ready, DAC ready, and successfully applied saved nulling profile ID >0: `GldUnifiedMain.cpp:7037-7042`.
- Prediction additionally requires initialized model, production approval, matching valid stored model binding/profile and runtime DAC readback: `GldUnifiedMain.cpp:7060-7069`.
- Model1 production approval true (`models/model_1/ModelMetadata.h:8`), Model3 true (`model_3/ModelMetadata.h:11`), Model2 false (`model_2/ModelMetadata.h:10`). Model2 raw sensors/CSV can be ready while prediction remains unavailable; do not bypass that gate.
- Prediction moving average needs ten samples, about five seconds at 500 ms, and resets on fresh acquisition/resume. Raw samples remain available during warmup.
- Dedicated image forces Dataset mode transiently without writing stored boot intent (`GldUnifiedMain.cpp:7172-7177`), so prior NVS MQTT/running mode need not be changed to start its hotspot.
- If saved calibration/binding is missing or invalid, workflow image cannot run serial nulling. Matching normal model image is required to calibrate/bind before returning to matching workflow image. Any upload is a separate explicit action; preserve Reset NVS OFF.

## COM7 and safe runtime identification for parent

The dedicated Wi-Fi loop returns before normal serial commands (`GldUnifiedMain.cpp:7481-7496`). Therefore GET_STATUS timeout is expected for a correctly installed workflow image and cannot identify it. No command is necessary to prove hotspot functionality.

If observing COM7, use an exclusive passive 115200 connection with DTR/RTS held false *before* opening, no reset, no input-buffer flush, no arbitrary commands. Only a boot log that is already emitted/available can be observed; lack of bytes is inconclusive. Boot exposes firmware version/profile, Dataset mode, power, nulling apply and `DATASET_WIFI_SERVER ready=1` (`7125`, `7182-7191`, `7380`). Do not deliberately reboot merely to obtain it.

Definitive runtime identification is authenticated WebSocket HELLO on `ws://192.168.4.1:81/dataset` after joining the actual `GLD-DATASET-xxxx` AP. Let the real bridge own that socket; maximum one client, so do not run a parallel probe while bridge is connected. HELLO fields include:

- protocol exactly `gld-dataset-wifi/3`, interval_ms 500, retention_ms 300000, capacity 640;
- device/session/boot identity, feature order, raw ready and reason;
- prediction_ready, model.profile_id, scaler_profile_id, runtime_version, production_approved and class_map.

Definitions: `GldDatasetWorkflowWifi.cpp:255-282`, begin/AP setup `631-670`; ring 640 samples and 300000 ms in `GldDatasetWorkflowBuffer.h:10-12`. AP is channel1, one client, no Internet. A network restoration watchdog must be prepared by the parent before joining; this worker did not operate WLAN.

## Remaining physical gate

Actual installed firmware/model/protocol,24V/nulling readiness, AP association/authentication, all eight real sensor channels, CSV equality/verification, Pause/Resume/Continue and actual disconnect/replay remain for the parent live test. No source/package finding requires recompilation at this time.
