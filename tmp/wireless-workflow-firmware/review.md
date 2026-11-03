# Independent workflow firmware source review

Result: **SOURCE-ONLY PASS; no concrete source blocker found.**

Reviewed revision (SHA256):

- `firmware/gld/src/GldDatasetWorkflowWifi.cpp`: `1f6389ddedb17e3d7f47657fc20f32da0cef06b356b8b8be4d0ad4e39a7cfda7`
- `firmware/gld/include/GldDatasetWorkflowWifi.h`: `fc74c8b51ee42ce40ab9092c9b9d22a8584395683312760afe184aee65a86116`
- `firmware/gld/include/GldDatasetWorkflowBuffer.h`: `1c003f7195c1685a3507ea07b4ec17b0d344b2c5a93de506e7288d8939c9c0ea`
- `firmware/gld/src/GldUnifiedMain.cpp`: `1e1d73a7b5d06c3614df3ad6894ded0c13a59f84bdb61518391fce737c9f9df8`
- `firmware/platformio.ini`: `0a4561ff5f38eff2d449eb36114a2b845648bc22d60c910dd6b6a6984bca0305`
- `firmware/tools/prepare_dataset_workflow_wifi.py`: `b3d4fd71ff8e913caed70fcdab1a3c0d0cd3728b9e2d25c32d9026f7f823178e`

## Checks actually performed

- 12 new source checks PASS: parent baseline of233 protected files and previous CSV, all old environment definitions after removing exactly3 workflow targets, old Unified selection, separate commands/epochs, prediction layout and nullable schema, ACK/summary ordering, callback and ML gate structure.
- 7 credential tests PASS using temporary synthetic files only: separate protocol3 header/config, matching protocol2 copy without mutation, existing-config stability, length/charset boundaries, malformed configs and old/unknown targets fail closed. No actual private credential was read.
- 18 pre-existing Replay source/credential checks PASS. Only additive workflow conditional stripping and removal of exactly3 workflow environments was added to the old isolation test; its protected baseline hash constants were not changed.

Exact commands (working directory D:/Github/PertaminaGLD):

```powershell
& apps/gld-operator/python-embed/python.exe firmware/tests/test_dataset_workflow_source.py
& apps/gld-operator/python-embed/python.exe firmware/tests/test_dataset_workflow_credentials.py
& apps/gld-operator/python-embed/python.exe firmware/tests/test_dataset_replay_source.py
```

## Independent C++ inspection

- Pause and Stop invalidate the acquisition epoch under the mutex before ACK. Sampler checks the epoch before append, discarding an in-flight old frame. Pause does not reset transport generation, sequence or retained records. Continue schedules now+500ms without backfill; only sampler resets moving average and performs inference.
- Transport Resume validates identity/prefix and cannot unpause acquisition. Offered-prefix bounds protect cumulative ACK. Control dequeue and sample selection share one mutex; socket I/O remains outside it. Stop from paused clears sampling/paused; summary requires not-paused, empty retained ring and acknowledged prefix equal total. Terminal incomplete remains sticky.
- Exact duplicate of the last Pause/Continue is a historical idempotent ACK even after terminal Stop; it does not resurrect acquisition and emits current paused=false/stopped status. Other stale/conflicting transitions fail. A future protocol3 client must reconcile actual ACK/status state rather than treating command ACK alone as proof of current acquisition.
- Raw mode remains available without prediction readiness. Prediction gate checks model approval, active nulling binding and DAC/readiness. It consumes the same captured raw frame; no additional ADS acquisition. Warmup/error/disabled values serialize null classes/confidence. Valid index, finite0..1 confidence and gas class mapping are checked; retained frames preserve predictions for replay.
- JSON/control serialization checks overflow and measured length before enqueue/send; sample encoding failure stops incomplete. The2304-byte JSON budget and workflow-only task stack allowances are inspected as source, not proven on ESP32.

## Baseline encoding note

The new Unified baseline is the explicitly UTF-8 decoded pre-workflow HEAD, meaningful SHA256 `9ca66d309fe90e327458ac377a8ca8d9b81d5e3cee7600b0a957228cc931dbbe`. Current workflow-disabled source matches that revision exactly. The initially observed `b5da...` came from Windows default cp1252 decoding of identical UTF-8 comment bytes; it was not a firmware drift. Existing old Replay baseline constants remain unchanged.

## Limits

No firmware/native compiler, build, COM, device API, service, upload, Wi-Fi switch or hardware execution occurred. Pattern tests and source review do not prove C++ execution, FreeRTOS interleavings, actual layout/heap/stack, worst-case JSON capacity, inference duration or500ms timing. Existing Hub collectors still reject protocol3; the wizard/client and physical acceptance are separate work.
