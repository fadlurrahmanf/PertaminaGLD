# Final hotspot native-feature integration — source receipt

Date: 3 November 2026. Scope: parent-authorized source implementation only. Compile, packaging, upload, COM, network/interface and service operations were not performed. Shipped firmware packages remain the previous binaries and do not yet contain this revision.

## Source snapshot for final review/freeze

| File | SHA-256 |
|---|---|
| `firmware/gld/src/GldUnifiedMain.cpp` | `2b93d489b873d173faa008474c7d307aa83af21ed80c9dca3e129a93ebd7c0a6` |
| `firmware/gld/src/GldDatasetWorkflowWifi.cpp` | `71493a20a62233a8ce7e3e3168ac1573c84039a03a8b3d2f4051606899a808c5` |
| `firmware/gld/include/GldDatasetWorkflowWifi.h` | `b8222a17ffb3bf3b0d39d4b2b5271366bd2b2f1ea88a53891a4c5ff4d8213888` |
| `firmware/tests/test_dataset_workflow_source.py` | `e61c096c688b89f625e15e95ef7f484d300d8e5e641b179e39868c0f70467a52` |

These are the only firmware/test files modified by this child. This directory additionally contains this receipt, `gld-baseline-audit.md` and the task-start `unified-before.cpp` source backup. The parent's application/manual work and the integration reviewer's report are separately owned. No firmware source outside the four listed files was edited by this child.

## Implemented behavior

- Only final `PGL_GLD_DATASET_WORKFLOW` targets acquire this integration. Ordinary stored mode, native serial command implementations, battery fallback, normal loop supervision, inference, nulling, model binding, diagnostics/QC and LoRa capability remain present. Older stage1/replay targets remain isolated.
- Workflow capture, moving average and NN now run in main-thread polling; the transport task only handles socket/queue/buffer state and cached readiness. ADS and LoRa share one SPI bus and have one execution owner.
- A session lease spans Start, Pause, Continue, link replay and Stop draining. It releases after a terminal session has delivered all samples and summary and the client disconnects. COM read-only supervision remains available; mutating commands, including priority Restart/CANCEL, receive their canonical busy ACK while leased. Start/Continue admission rejects native operation overlap.
- Current captured frames update native telemetry/result/fault/AUTO alarm even when optional CSV prediction columns are unchecked. Disabled CSV prediction still serializes the protocol-required `disabled` status and null class/confidence fields. Same-profile MAV and a valid steady alarm are preserved across transport/session transitions; only actual invalid data/readiness/profile discontinuity resets them.
- Native station/offline helpers preserve the Dataset AP. In stored native DATASET mode, a connected AP client suspends blocking background station/broker reconnect; an in-progress station wait yields to the new AP client. Native MQTT remains available when unattended and an already connected MQTT client may continue servicing idle commands. Temporary native busy state does not falsely label hardware-ready Hello as not ready.
- Native 24 V fan, SHT40, watchdog/service-hold, status and power reconciliation remain in the common loop. Active/paused wireless acquisition fails closed on power/readiness loss before native power processing. Native conflicting ADC/radio/recovery/legacy acquisition work is deferred while the external-power session owns acquisition.

## Verification receipts

Run with `C:/Users/MSI/.platformio/penv/Scripts/python.exe` from the repository:

```text
-m unittest firmware.tests.test_dataset_workflow_source firmware.tests.test_dataset_replay_source firmware.tests.test_dataset_workflow_credentials -q
Ran 47 tests in 0.442s — OK

firmware/gld/tests/test_alarm_control_contract.py
GLD alarm control source contract: PASS

git diff --check -- firmware/gld/src/GldUnifiedMain.cpp
PASS (only the repository's LF-to-CRLF notice)
```

The 47 tests include:

- Exact pre-workflow meaningful unified-source SHA-256 after removing final-workflow conditionals: `9ca66d309fe90e327458ac377a8ca8d9b81d5e3cee7600b0a957228cc931dbbe`.
- Exact existing environment-map SHA-256: `fe1c34e2087a57c7b654d0ab484387bee5fee50d3a73ff2fea1a2a8e0ee3f8ed`.
- All **233** recorded protected baseline files, including **226** package files, plus the previously captured CSV are byte-for-byte unchanged.
- Main-thread single acquisition, no hardware callbacks on transport, session/config ownership through Pause/replay/final Disconnect, native serial/priority guards, same-frame native alarm independent of CSV, disabled wire projection, steady alarm continuity, safe-idle profile refresh, standalone AP admission and AP-preserving station helpers.
- Existing replay/retention/ACK/order/idempotency/summary contracts, exact three final workflow build environments, credentials isolation and Model 1/2/3 dual-input model shape gates.

Normal Model 1 app remains `6ff1ddec033e9fa08391a8e3d4cad54d9e2fd6b059100e78d698ccaa6366b324` (manifest v0.8.36, 1,039,200 bytes). Normal packages, pin maps, model files, calibration implementation, NVS schema and PlatformIO environments were not edited.

## Review findings resolved

1. Starting a Dataset session initially reset valid MAV/alarm and created an artificial warmup gap. Removed ownership/epoch resets and added a continuity regression.
2. Stored native DATASET could starve standalone AP Connect/Start with repeated station retries. Added client-aware station/broker admission and kept hardware readiness independent of temporary native busy state.
3. Native inference while CSV prediction was OFF initially exposed a `valid`/`warmup` wire status despite `enabled=false`. Serializer now explicitly projects `Disabled` and nullable fields independently of native inference.

## Remaining gates and practical limits

- This is **source-contract evidence**, not a C++ compile, live GLD, physical alarm, RF or timing proof. User approval is required before compiling this new revision. After approval, compile Models 1/2/3 in three parallel agents and verify exact final package provenance before replacing those three hotspot packages.
- AP startup follows normal hardware/mode boot initialization. Stored native NULLING can perform its existing blocking calibration before AP startup; stored DATASET can perform its initial configured station connection attempt before AP startup. Measure real boot availability and timeout on the target board; do not promise immediate hotspot discovery.
- Exact 500 ms capture plus simultaneous blocking LoRa TX/ACK/retry is not claimed. Wireless Dataset session ownership defers conflicting native radio work until closure/disconnect; the existing LoRa feature returns afterward.
- Runtime hardware acceptance must cover native idle COM commands/QC/nulling/binding/radio, native sensor/alarm continuity with CSV checkbox OFF and ON, graph8 and 500 ms sampling, compact CSV, Pause/Continue/Stop verification, dropped-link replay and lease release, standalone AP without router/broker, and 24 V/battery transitions. Reset NVS remains OFF for an authorized upload unless the user changes that instruction.
- Changing device ID with the advanced native `reboot=false` option does not rename the already-running AP/cached wireless identity. Restart is required; normal/default `reboot=true` behavior is preserved.

**SOURCE FROZEN:** the independent integration reviewer confirmed these four exact hashes and all three fixes, with no remaining blocking source finding. Their independent checks passed 22 Workflow source + 18 Replay source + 38 backend Workflow + 4 route tests and the standalone alarm contract; see `integration-review.md` in this directory. Any later source edit invalidates this freeze and requires a new receipt.
