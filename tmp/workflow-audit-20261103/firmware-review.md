# Firmware audit — F revision 1

Audit time: 2026-11-03 07:00:14 Asia/Jakarta. Read-only firmware audit; no compile, upload, COM, WLAN, native dialog or service action.

## Result

No actionable firmware defect confirmed in the reviewed protocol-3 path. All 37 focused source/credential/isolation tests passed. Current public source identity matches the three successful build receipts; all three Hub packages match immutable build artifacts, manifests, and the exact embedded model/protocol markers. No firmware source or package changes made.

## Acceptance evidence

|Contract|Source evidence|Result|
|---|---|---|
|Hotspot independent of saved running mode|GldUnifiedMain.cpp:7172-7176 forces dedicated image DATASET without consuming/writing stored mode; workflow begin uses AP 192.168.4.1, GLD-DATASET-device and Basic auth at GldDatasetWorkflowWifi.cpp:631-669|Source conformant|
|8 sensors / 500ms|GldDatasetWorkflowWifi.cpp:23 and sampler:456-514; captureDatasetWifi in Unified:7044 captures exactly canonical channels 0..7 once. ADC reader owned exclusively by sampler after setup; loop:7481-7498 returns before legacy acquisition|Source conformant; actual timing unmeasured|
|Retention to 5min|Buffer.h:10-12 fixed 640 records, 300000ms, window8; AckProgressClock arms on pending sample/loss and advances only durable prefix progress; Wifi.cpp:156 exact-boundary check stops incomplete and keeps retained data|Source conformant; RAM only, no reboot retention|
|No fabricated or repeated prediction|Unified:7060 strict model/binding/DAC readiness; 7076 prediction consumes same raw sample and production MAV/preprocessing; sample prediction retained with raw frame. Warmup/error/not_ready class/confidence null|Source conformant; actual inference runtime unmeasured|
|Pause / Resume|Wifi.cpp:411-437 stable transition identity and monotonic seq, epoch invalidation before ACK; sampler epoch discard:499. No ring reset or summary on Pause; Continue same SID/seq and schedules next capture after500ms; reset MAV on new epoch acquisition worker only|Source conformant|
|Stop while recording or paused|Wifi.cpp:439-449 stop invalidates in-flight work, sticky incomplete reason; poll:680-698 summary only notpaused/stopped, ringempty, allprefixACKed|Source conformant|
|Stop followed by Continue CSV|Firmware allows genuinely new SID only after prior summary sent and all retained samples ACKed; logical sameCSV append is backend responsibility|Source conformant|
|Direct vs indirect|Firmware transport preserves samples and pending session; client Direct freezes public output and privately closes/drains, indirect replays. Firmware alone does not choose CSV behavior|Backend responsibility reviewed separately|
|UI Reset preserves data/NVS|No RESET command exposed by protocol3. LogicalReset is backend Stop/verify/reset; sampler doesn't clear ring on disconnect. Only admitted newStart clears acknowledged prior session. No workflow NVS writes|Source conformant|
|Old pin/nulling/model paths protected|Workflow isolated compile flag/three envs inherit matching Stage1; old unflagged Unified meaningful digest, old env config digest, existing233 publicbaseline hashes and previous62rowCSV all match|37 tests PASS|

## Verification commands (2026-11-03)

- `apps/gld-operator/python-embed/python.exe -m unittest discover -s firmware/tests -p test_dataset_workflow_source.py -v` — 12 PASS.
- `apps/gld-operator/python-embed/python.exe -m unittest discover -s firmware/tests -p test_dataset_workflow_credentials.py -v` — 7 PASS, synthetic credentials/temp only.
- `apps/gld-operator/python-embed/python.exe -m unittest discover -s firmware/tests -p test_dataset_replay_source.py -v` — 18 PASS, original protected source/package identity checks included.
- Read-only `package_dataset_workflow.verify_receipt(model)` for1/2/3 verified successful receipts, before/after/current public hash identity, actual build log SUCCESS, exact four images in build/artifact/receipt.
- Independent Hub manifest SHA256/file sizes/hashes vs artifacts and `model_provenance` on each firmware image: all3 PASS. Did not run package main or private_verification; no private credentials opened or reported.

## Remaining physical evidence

Actual Windows WLAN scan/join, GLD AP startup/reconnect, 500ms eight-channel capture with prediction load, heap/stack margins, 5min RF retention, model readiness/accuracy and physical power behavior remain unproved by this audit. Source checks and prior successful compilation are not physical evidence. Existing 0.8.36 workflow binaries require correct model selection with Reset NVS OFF and saved valid nulling profile; no new firmware compile needed for this read-only result.
