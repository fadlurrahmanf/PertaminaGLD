# GLD1 normal feature parity audit — 3 November 2026

Owner: GLD_Agent baseline audit child. Initial scope: source/package inspection and integration recommendation; no source, package, hardware, COM, Wi-Fi, service, compile, or upload action was performed during that audit. Parent subsequently authorized the source implementation documented in `source-implementation-receipt.md`. Parent owns activity log and implementation decisions.

## Baseline identity: use current artifact evidence

The currently installed normal Model 1 package is **not** the v0.8.38 / `69a493c` package described in `docs/firmware/gld1-active-release.md`. That document is historical and conflicts with the current manifest. The old isolated worktree `D:/Github/PertaminaGLD-GLD1-69a493c` is absent.

| Artifact | Normal Model 1 currently installed | Current final workflow Model 1 |
|---|---|---|
| Package directory | `apps/operator-hub/firmware-packages/gld_model_1/latest` | `apps/operator-hub/firmware-packages/gld_model_1_dataset_workflow_wifi/latest` |
| Manifest firmwareVersion | 0.8.36 | 0.8.36 |
| Manifest source commit | `022b740f0f416c31d18fe26370333b8984821e3b` | `74e1a2f932cb4dafb8ac393f6c7368c5f3dec965` |
| Created | `20261021T052026Z` | `20261103T053106Z` |
| App bytes | 1,039,200 | 1,104,000 |
| App SHA-256 | `6ff1ddec033e9fa08391a8e3d4cad54d9e2fd6b059100e78d698ccaa6366b324` | `f86925678ea2b8732c0be1ff791b3a364b9f1d748d6a67b7e02f1f7b3b5b4491` |
| Firmware tree snapshot SHA-256 | `f81432a0ff2faac12aea325fbafb0fdf143949a90c6d545a2650e7a7f3dda3ab` | `d2e221671cc77eb705c8acb024c42bf8df72f14ec6093137f119cf0245e2cc27` |

The normal manifest records a **dirty** source tree. The commit alone is therefore not proof of exact binary inputs. The protected normal app hash matches existing task baselines (`tmp/wireless-workflow-firmware/baseline.json`, `tmp/wireless-dual-mode/baseline.json`, `tmp/wireless-password/protected-before.json`). Preserve those normal package bytes. Pin source isolation and model headers before modifying final hotspot targets; do not silently replace normal packages or transplant historical v0.8.38 code.

`git show 022b740:firmware/gld/include/BoardPins.h` already specifies the GLD1 GPIO48 active-high steady alarm and no buzzer. Model 1 at that commit already has `PGL_GLD1_FAST_NULLING=1`. The later `1d35f95` commit extends deterministic nulling to Models 2/3. A 5 ms ADC settle value is not a promise of 5 ms total nulling. Existing October nulling logs record minutes of calibration, full 8/8 success before profile commit, and explicit model binding. Preserve those semantics.

## Actual feature loss in the current hotspot build

These references identify the inspected source before future integration edits.

| Feature | Normal behavior | Current workflow behavior / regression |
|---|---|---|
| Stored operating mode | `GldUnifiedMain.cpp:7173` normally reads `readGldMode()` | All Dataset Wi-Fi targets force DATASET and bypass stored mode |
| Serial/operator controls | `firmwareServiceTick()` at 3656 calls `checkSerial()` | Early return at 7483–7498 bypasses it; most operator controls become unavailable |
| Native inference and status | `runScan()` at 6020 updates sensor cache, MAV, validity, `lastResult`, fault state and alarm | Workflow capture/predict uses its own callback path; native telemetry/result are not updated |
| Physical AUTO alarm | `runScan()` at 6110–6147 applies current valid production inference and GLD1 invalid-inference policy | Workflow predictor explicitly excludes alarm; prediction checkbox OFF bypasses NN entirely |
| LoRa runtime | INFERENCE setup calls `beginLoraRadio()`, normal loop handles configured automatic/manual/target modes | Forced DATASET skips inference setup; early return skips normal TX/RX scheduling |
| Nulling and binding | COM command dispatch retains clean-air gate, full/failure retries, persistent profile rules and explicit binding | Parser is unreachable in workflow loop; these existing capabilities are absent in use |
| QC/boot/current state/full-scale tools | Native COM commands operate with watchdog/service support | Parser unreachable; boot/ADC/DAC recovery loop bypassed |
| Power lifecycle | Native loop reconciles external/battery transitions and battery one-shot warmup/acquire/transmit/DONE/CLR | Early return bypasses power reconciliation and pending shutdown; dataset only checks readiness during capture |
| Fan/status/environment | Native loop maintains continuous external-24 V fan, status indication, SHT40 and service hold | Early return bypasses normal loop services |
| Legacy MQTT Dataset | Native DATASET runs Wi-Fi/MQTT/replay/status/state machine | Workflow replaces this dedicated acquisition path; retaining capability requires coordinated network and acquisition ownership |

The loss is deliberate in the old dedicated-image design: the loop comment says not to run serial, boot recovery, inference, radio or nulling because the sampler task exclusively owns ADS. Removing only the early return introduces races rather than safely restoring features.

## Concrete concurrency and lifecycle hazards

1. **Shared SPI is confirmed.** Global `gldSpi` is at `GldUnifiedMain.cpp:261`; ADS is initialized with it at 1407; RadioLib `Module(..., gldSpi)` is constructed at 5781. ADS read transactions and radio operations cannot run concurrently just because their chip-selects differ.
2. **Sampler escapes the module lock.** `GldDatasetWorkflowWifi.cpp:458` takes scheduling/state under `Lock`, then executes readiness/capture/model callbacks without that lock. Pause/Stop changes epoch and rejects the late result but does not wait for the ADC/model callback to finish. An ACK currently does not establish hardware quiescence.
3. **MAV/NN state is shared.** Both native `runScan()` and workflow predictor use global `movingAvg` and `network`. The current reset callback explicitly assumes only the workflow worker owns them. Readiness also reads mutable DAC/profile/binding globals without a native-command barrier.
4. **COM handlers can be reentrant during native work.** `serviceDelay()` and ADS/boot/nulling helpers call `firmwareServiceTick()`; simply putting one global mutex around everything risks deadlock or nested mutation. Existing command reentrancy guards are not an acquisition lease.
5. **AP can be destroyed by normal helpers.** `disableNetworkForOfflineMode()` at 4756 calls `WiFi.disconnect(true)` and `WiFi.mode(WIFI_OFF)`; `connectWifi()` at 4766 calls `WiFi.mode(WIFI_STA)`. Workflow `begin()` selects WIFI_AP. Preserve AP explicitly in final workflow builds; legacy STA/MQTT capability needs AP_STA or mutually exclusive ownership.
6. **Profile cached at startup.** Workflow `begin(deviceId, nullingProfileId, ...)` stores profile identity once. If normal nulling/binding/configuration is restored, refresh safe-idle metadata after successful changes before a new session. Do not let one resumed session mix calibrations.
7. **Power transition needs coordination.** Dataset acquisition requires external 24 V and fails closed on invalid raw sample/power. Loss of 24 V must quiesce acquisition before native battery power sequencing; retained rows and finalization outcome must remain explicit.
8. **Production approval is a real gate.** Keep model binding fingerprint/profile, DAC readback and model approval gates; Model 2 must not be made production-approved simply to enable a checkbox. Model 1 uses ADC8 + derived7 = 15 inputs and two outputs; retain the fixed total-input check.

## Recommended integration boundary

The user has clarified: existing normal controls may remain on COM; Dataset capture is wireless. No new general-purpose wireless RPC is required.

Prefer **main-thread acquisition** for the final workflow targets. Move the current sampler's scheduling/capture/predict/append step into a bounded `pollAcquisition()` called by the native main loop. Leave the socket transmitter task queue-only. This is simpler to prove safe than spreading SPI/model locks over all native paths with reentrant serial handling.

1. Keep normal setup and runtime mode selection for final workflow builds. Initialize AP as an added service after common hardware/model initialization, independently of the native INFERENCE/DATASET/NULLING branch. Keep older stage1/replay code isolated or retired only from the UI, not silently rewritten.
2. Expose workflow session/resource state and native-operation busy admission. Before Start/Continue/Resume, reject while native nulling, boot/QC/full-scale, DAC/profile mutation, legacy acquisition or a native bus operation is active. Reject invalid power/profile/readiness. Validate admission **before** success ACK/session mutation.
3. While a wireless session owns acquisition, keep read-only serial status and safe supervision working, but reject commands that mutate mode, calibration, profile, model, power or shared hardware. Do not run a second native ADS scan, native recovery, legacy MQTT acquisition or blocking LoRa transaction concurrently.
4. Process Pause/Stop in the main execution context between captures. Their ACK then implies the capture/model callback is complete. Keep the **configuration lease** through Pause and through retained-data replay/finalization. Existing Stop + Disconnect gating can remain; do not permit nulling while a CSV session can resume.
5. Use each captured 8-channel frame once for both native production inference/AUTO alarm and optional exported prediction. CSV checkbox controls whether inference columns are emitted; it must not disable the safety/runtime inference path. Reuse native validity/priming/DAC/binding/alarm policy, not just `updateAlarmOutputs(true/false)` by confidence. Update native sensor/result status consistently and do not fabricate valid predictions during warmup or fault.
6. On Stop/finalization/disconnect, restore ordinary native scheduling. Preserve valid same-profile MAV and steady AUTO alarm across transport/session ownership changes; a session edge alone is not invalid data. Reset/re-prime only on an actual invalid frame, readiness failure or profile/model discontinuity. On next Start, refresh profile metadata from current successful calibration/binding. Do not preserve stale samples/model state across a changed profile.
7. Keep AP alive when native INFERENCE/NULLING disables station connectivity. For native MQTT Dataset, use deliberate AP_STA station-only reconnect/disconnect helpers and prevent duplicate sensor acquisition. Guard blocking network reconnect while wireless recording.
8. Preserve normal battery runtime when no wireless session is active. During recording, 24 V loss must stop acquisition, declare an explicit incomplete/error outcome as appropriate, and only then enter existing battery/DONE/CLR semantics. Do not enable service hold implicitly.

This preserves all existing **capabilities** with explicit resource ownership. It does not prove simultaneous long LoRa ACK/retry operations plus exact 500 ms capture. That concurrency requires a bounded nonblocking radio scheduler or an explicitly accepted recording exclusion; do not silently claim it works.

## Exact implementation touch points and ownership recommendation

Parent or one firmware owner only:

- `firmware/gld/src/GldUnifiedMain.cpp`: additive final-workflow setup/loop, serial mutation admission, native busy guards, safe AP-aware network calls, production same-frame inference/alarm integration, resource and power transitions.
- `firmware/gld/src/GldDatasetWorkflowWifi.cpp`: main-thread sampler, session/resource APIs, Start admission, quiescent Pause/Stop, safe-idle metadata refresh, preserve retention/ACK/command-idempotency/summary behavior.
- `firmware/gld/include/GldDatasetWorkflowWifi.h`: explicit lifecycle/admission/status contract and updated callback execution context.
- `firmware/tests/test_dataset_workflow_source.py`: retain no-bypass and production approval gates; replace old dedicated-worker assumptions with native feature availability and serialized ownership assertions.
- `firmware/gld/tests/test_dataset_wifi_source.py`, `firmware/tests/test_dataset_replay_source.py`: retain normal/non-workflow source isolation and old target compatibility.
- Native alarm, nulling, serial/parser, power, model shape/binding and package provenance tests: run relevant existing suites. Avoid widening the patch to model data, pin maps, NVS schema, unrelated GLD2/CH/Gateway or baseline normal packages.

Parent separately owns upload-choice filtering/labels and manual work. No package rebuild is needed for a UI-only choice filter. New firmware behavior does require an approved build before updating final hotspot package binaries; compile and upload remain unperformed.

## Completion gates before calling firmware feature parity complete

1. Preserve normal package files and approved model/pin/nulling inputs byte-for-byte; preserve normal and non-GLD1 preprocessed/runtime behavior outside final workflow conditionals.
2. Host tests: native serial availability when idle; Start vs native calibration/QC admission; busy mutation rejection; Pause/Stop completion vs in-flight capture; resume configuration invariance; profile refresh after calibration; AP lifecycle; 24 V transition; independent AUTO alarm with CSV prediction OFF; same-frame model inputs and cached telemetry.
3. Preserve all protocol3 replay guarantees: 500 ms interval contract, bounded RAM retention, 5-minute ACK timeout, direct/inDirect semantics, idempotent commands, sequence order/no duplicate CSV rows, final summary only after retained rows acknowledged and target CSV verified by the existing host flow.
4. With user compile approval, build final Models 1/2/3 in three parallel agents as requested in prior firmware builds; verify exact artifact provenance and only update final workflow packages. Normal packages remain unchanged.
5. With explicit current hardware authorization: upload intended Model 1 with Reset NVS OFF, then prove idle COM status/nulling/binding/QC/radio capabilities, Wi-Fi graph8/500ms and compact CSV, prediction checkbox OFF/ON, Pause/Resume/Stop/Continue, dropped link/replay, and return to native runtime after closure. Real radio/alarm/power observations must be recorded separately from host proofs.

Initial audit result: **the shipped dedicated hotspot package does not yet have normal-feature parity**. Parent subsequently authorized source integration; see the source receipt alongside this report. No claim of a compiled or hardware-verified fix is made.
