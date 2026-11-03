# Native features plus hotspot — release record

Updated 2026-11-03 14:38:22 Asia/Jakarta.

All three requested firmware compilations succeeded in parallel, without warnings/errors. Real three-process overlap: 8.858949 seconds. No firmware was uploaded.

|Model|Firmware SHA-256|
|---|---|
|1|`10dc13e3328a3fa3ba33562d7d85906113fe23295ea3eeb6db3b86472f5bb68e`|
|2|`4fe021b9f1381402b146f85985ce22dd8f9f95a9df108dcafa57a34af53e12de`|
|3|`747c423c32fae90eed2e9f05a92b8a985a815ed49a891935c4358c4feeaffa3c`|

## Package and source evidence

- Three final Hub latest directories now contain exactly seven validated package files. Previous directories preserved as previous-20261103-before-native-features.
- Strict child, Hub and preflight validators pass; exact model blob/profile, NVS flash-sector isolation and private credential consistency pass. Capability metadata nativeSerial=true and datasetWifi=true is validated only for the exact three final workflow environments.
- Served GET package manifests and all four flash files match the new bytes. 199 other latest package files unchanged; strict pre-deployment protection also verified 321 older package/artifact files.
- 95 Hub Python tests, four new capability validator tests, actual Expert upload-action CJS and final-menu/legacy wireless CJS pass. Earlier source/replay/credential 47 checks and alarm contract pass. An initial Node invocation used a nonexistent test filename; it is not counted, and the actual test_native_workflow_upload_ui.cjs subsequently passed.
- Ordinary firmware conditional behavior, model/pin/nulling inputs and stored-mode semantics remain protected. Firmware source freeze from the reviewed receipt matches all builds.

## COM and activation

The older dedicated hotspot firmware bypassed native serial processing; the Hub also intentionally skipped post-upload COM reconnection. The new source restores native operation when unleased, and capability-marked packages now select the ordinary COM reconnect/version/ID readback path. Dataset ownership still requires Stop, durable CSV verification, then Disconnect before mutating COM controls.

The user approved restarting Hub and GLD bridge. Automatic approval review rejected the composite restart command before process creation, with no detailed reason. No process was stopped, no credential file was read by that rejected command, and COM7 remains connected. No alternative process-control route was attempted. Package installation is complete, but the currently running backend has the previous manifest validator and upload routing. Restart Hub and GLD bridge manually before using the new packages; browser refresh alone does not reload Python modules. CH/Gateway services and the active broker remain untouched.

Real-device upload, COM readback with this new firmware, 500 ms cadence, alarm, replay and radio/power checks remain pending. Reset NVS remains OFF for a future approved upload.

## Activation resolved after stale duplicate diagnosis

2026-11-03 15:20:48: user manually closed the old runtime. Standard start-only Hub launch succeeded; new Hub21096/GLD21584 is active. Live validator recognizes capabilities on Models1/2/3, package hashes match, browser selectedModel2 without errors. Broker running/authenticated. The former activation-pending section is historical and superseded. Exclusive Windows listeners, accurate occupied-port preflight and non-owning reuse of healthy children now prevent duplicate startup. 105Hub tests and4capability tests pass. No firmware flash or NVS reset.
