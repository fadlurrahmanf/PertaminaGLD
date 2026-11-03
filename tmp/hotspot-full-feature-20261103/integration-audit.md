# Integration audit - normal Model 1 features plus hotspot

Status: read-only source audit, 3 November 2026. No source edits, compiler,
device/COM/WLAN access, service changes or runtime claims by this worker.
The parent owns implementation, tracker and activity logging.

## Conclusion

The current Workflow image is an intentionally exclusive Dataset runtime, not
the shipped normal firmware with an added transport. Removing one early return
cannot safely restore parity: normal and Workflow paths currently share the
ADS/SPI bus, moving average, model object, calibration and power state without a
cross-task ownership boundary. The smallest defensible final implementation is
normal-firmware baseline plus an additive hotspot recorder with a single sensor
and inference owner and explicit recording lease. Three visible final hotspot
choices can be simplified independently without deleting legacy artifacts or
changing their backend allow-lists.

## Concrete source findings

| Finding | Evidence | Consequence |
|---|---|---|
| Mode forced to Dataset | `firmware/gld/src/GldUnifiedMain.cpp:7172` | Stored normal mode is bypassed. Normal INFERENCE/NULLING mode selection does not behave normally in this image. |
| Exclusive loop | Same file `7483-7500` | Only WDT and Workflow poll execute. `firmwareServiceTick`, power reconciliation, SHT40/fan maintenance, boot recovery, normal scan/alarm/radio and nulling runtime below the return do not execute. |
| Serial handling bypassed | `firmwareServiceTick:3656`; `checkSerial:3248` | GET_INFO/GET_STATUS, normal settings, nulling/binding and controls remain compiled but are not serviced after setup. |
| Same SPI object | ADS `ads.begin(gldSpi)` at `1407/4321`; LoRa `Module(...gldSpi)` at `5784` | Running normal LoRa while the new task samples ADS needs arbitration, even if the main normal ADC scan is skipped. No relevant mutex found in ADS/DAC drivers. |
| One model/average owner required | `runScan:6020` and `predictDatasetWorkflow:7076` | Both use `movingAvg`/`network`. Concurrent execution or reset corrupts inference/window semantics. |
| Alarm is not Workflow prediction | `runScan:6130-6153` updates `lastInferenceValid`, telemetry cache and physical alarm. Workflow callback returns prediction only (`7095-7113`) | Simply making normal commands callable still does not restore AUTO alarm or normal telemetry in recording. CSV's prediction checkbox must not become an alarm-enable control. |
| Network mode conflicts | `disableNetworkForOfflineMode:4756` uses WIFI_OFF; `connectWifi:4766` uses WIFI_STA. Workflow `begin:635-645` uses WIFI_AP | Normal INFERENCE/NULLING network-off or MQTT Dataset STA maintenance would tear down the AP. AP/STA ownership/policy needs explicit integration. |
| Weak public lease API | `GldDatasetWorkflowWifi.h` exposes begin/poll only | Main runtime cannot ask whether capture is in flight, retained data remains, or summary is pending. No safe mutation guard can be built from public API today. |
| Pause/Stop is not physical quiescence | Sampler releases `guard` before capture/predict (`463-499`); final epoch test discards a stale result | Epoch invalidation prevents publication after Pause, but ADC/model callback may still be executing when the ACK is queued. Nulling must not begin merely because sampling=false. |
| Profile identity cached at begin | `state.profile = nullingProfileId` in Workflow begin; HELLO/transition use state.profile | Restoring calibration after AP startup needs idle-only metadata refresh or a safely restarted service, otherwise HELLO and transitions retain old profile ID. |
| App reserves device on connection | `apps/gld-operator/bridge.py:430-446` | workflow_in_use includes connected=true even in ready/complete. Connect/start/continue/resume reject any connected COM. |
| COM/probe/upload barred while reserved | Bridge `1614`, `1656`, `1688`; `tests/test_workflow_routes.py` | These are deliberate existing protection gates. Normal COM can be restored initially by Disconnect after closing a Wi-Fi session. Simultaneous COM+Wi-Fi requires new command/resource admission tests. |
| No generic wireless control plane | Workflow commands are START/PAUSE/CONTINUE/RESUME/STOP/ACK only | Existing Running/Nulling/Expert UI writes serial commands. Providing all those views over Wi-Fi is a new authenticated RPC/transport-adapter project, not a property already supplied by protocol 3. |

The normal package baseline is v0.8.38 / 69a493c with later GPIO48/model updates,
as recorded in `docs/firmware/gld1-active-release.md`. Current Workflow reports
v0.8.36. GLD baseline worker owns the exact runtime/NVS/pin/model comparison;
source parity must be anchored to the actual shipped normal images, not only to
the current root branch's inactive preprocessor path.

## Confirmed transport scope and preferred implementation

The parent subsequently confirmed the user's answer: **normal controls remain
COM; Dataset data use Wi-Fi**. No generic Wi-Fi RPC is required. Existing
Stop/Disconnect-before-COM admission can remain the protected app contract. The
missing capability to restore is the normal firmware's command/runtime behavior
inside the final hotspot image, not a new transport for every Operator view.

GLD baseline worker and this worker agree that moving bounded capture/MAV/NN
execution into the main firmware scheduler is simpler than threading a new
hardware mutex through reentrant serial/nulling/diagnostic service callbacks.
The WebSocket transport worker can remain queue/serialization only. A main-thread
acquisition lease must still make Start vs long native operations deterministic;
callbacks must not reenter acquisition from firmwareServiceTick/serviceDelay.
Paused/Stop acknowledgement must follow actual callback completion, not just an
epoch change. Keep clear ownership until retained data/summary are reconciled.

Feature parity is **by operating mode**, not a claim that every feature runs
concurrently. The current normal firmware's Dataset mode already does not run
the INFERENCE-mode LoRa scan path. If normal inference is intentionally retained
during acquisition, preserve its production alarm independently of CSV options.
If recording instead acquires an explicit Dataset lease and defers normal LoRa,
state that temporary policy and restore the normal idle mode after safe closure;
do not promise continuous LoRa plus 500 ms sampling without a separately verified
nonblocking radio design. Original UART GET_STATUS/GET_INFO and normal tools
should remain available after Stop+Disconnect in either design.

## Minimum safe integration contract

1. **Idle normal operation remains the baseline.** Retain normal boot intent,
   serial command service, calibration/bind, model initialization, alarm,
   settings, LoRa, diagnostics, power and sleep policy. Start AP as an additive
   externally powered service rather than forcing the entire product into the
   old special Dataset boot branch. Reuse the normal model object; do not allocate
   a second independent runtime merely for CSV.
2. **Explicit acquisition ownership.** One owner produces an eight-channel
   frame. Normal telemetry, inference/alarm and optional Dataset storage consume
   that frame. If keeping task-based capture, use a shared sensor/SPI/model lease
   with an in-flight/quiescent handshake. Do not run two independent ADS scans or
   moving-average/model calls. SPI operations from normal radio need the same
   arbitration or a verified scheduler boundary.
3. **Preserve the relevant mode's safety behavior independently of CSV
   choices.** The public prediction checkbox controls CSV/result inclusion; if
   production INFERENCE remains active it must not silently turn off its AUTO
   alarm. Preserve approval, binding, DAC, sensor-validity and class mapping gates
   and the normal physical-output policy. Explicitly document a temporary Dataset
   mode/lease if that is the chosen concurrency boundary.
4. **Mutation admission on firmware too.** Reject or defer calibration, sweeps,
   gains/DAC/sensor power changes, mode/NVS/identity changes and other resource
   writers while a recorder owns the session (including Pause/recovery/draining).
   A cached status read may be safe; classify commands by actual resource
   effects, not GET/SET prefix. `checkSerial` has a priority RESTART path outside
   normal dispatch, so a central handler-only guard is insufficient. Any
   deliberate reset/poweroff must preserve the existing explicit intent/data-loss
   semantics rather than pretending buffered RAM survives.
5. **Pause and Stop semantics remain precise.** Pause stops future acquisition,
   retains the session/profile/configuration and does not permit recalibration
   before Resume. Stop must reach in-flight quiescence and the existing
   retained-prefix/summary ownership condition before releasing the recorder.
   Transport disconnect is not release while data/session is still owned.
6. **Refresh identity only at a safe boundary.** After an idle calibration/bind,
   refresh live readiness/profile metadata for the next HELLO/new Start. Never
   change the identity of retained samples or a paused session.
7. **Explicit Wi-Fi mode and power policy.** Preserve AP while required normal
   networking executes; do not let reconnect helpers force STA or OFF behind it.
   If normal MQTT Dataset must coexist with the AP, implement and test AP+STA
   deliberately (including channel change/reconnect). Keep battery normal
   sleep behavior; recording was authorized for external 24 V and RAM retention
   only while the GLD remains powered.
8. **Do not broaden the confirmed app transport scope.** The confirmed
   parity target is all normal functionality available using its existing COM
   controls when the Wi-Fi recorder is disconnected/closed, while Dataset data
   remain wireless. Full Running/Nulling/Expert control over Wi-Fi would need
   authenticated request IDs, command results, readonly/mutation classification,
   admission/ownership and a bridge/frontend transport adapter. This is a scope
   future scope expansion only; the user confirmed COM controls and Wi-Fi
   Dataset, not replacement of every serial API.

## Regression/acceptance gates

| Boundary | Required evidence before claiming parity |
|---|---|
| Normal runtime | Exact baseline pins, nulling settle/no-warmup policy, saved-profile/binding ABI, alarm AUTO/MANUAL, normal inference/model, UART commands, LoRa configuration and power/sleep checks unchanged. |
| Resource ownership | Concurrent Start vs nulling/sweep/config mutation; Pause ACK with in-flight capture; Stop while callback runs; retained/outage session vs attempted normal operation; LoRa/ADS SPI access; model average/reset interleavings. |
| Operator transport | Existing `test_workflow_routes.py` admission and actual old flows remain protected; any simultaneous mode has explicit new route/command guards. No stale UI can mutate hardware behind locks. |
| Recorder protocol | Duplicate/unknown Start/Pause/Stop, transport resume, same CSV Continue, ring/ACK limits, 300s retention and power loss semantics still match existing tests. |
| CSV | 12 base columns, optional gain/status groups, full internal metadata, fsync-before-ACK, rollback and full Stop verification still pass. |
| Normal status + alarm in recording | One coherent frame/cache; any retained INFERENCE behavior keeps normal production alarm independent of CSV inclusion. If Dataset lease explicitly defers normal inference/radio, verify exact mode-equivalent behavior and restoration on closure. Invalid-frame and physical-output behavior must not silently change. |
| AP/STA lifecycle | Cold boot modes, 24V/battery transition, normal network reconnect, user configuration changes and service restart cannot silently destroy an owned recording or disable unrelated normal paths. |
| Physical validation | After separately approved compile/upload: same-model device proof for normal controls, nulling/bind while idle, current-frame inference/alarm, 500ms eight-sensor acquisition, replay, Stop/Continue and no lost radio behavior. Build-only is not this gate. |

Existing `firmware/tests/test_dataset_workflow_source.py` intentionally asserts
the old dedicated isolation. Do not simply delete those tests to claim success;
replace/supplement them with the new explicit ownership contract while protecting
the legacy dedicated artifact histories. Useful existing suites include
`apps/gld-operator/tests/test_workflow_routes.py`,
`test_dataset_workflow.py`, `test_workflow_adversarial.py`, and
`firmware/gld/tests/test_alarm_control_contract.py`,
`test_nulling_fast_scope.py`, `test_nulling_stability_scope.py` plus the active
baseline worktree's release verifier.

## Decision and authorization boundary

The transport decision is resolved: COM normal controls, Wi-Fi Dataset. No new
user decision is needed merely to preserve these transports. Do not
claim all normal UI controls are already wireless. Before expanding that transport
scope or choosing a genuinely conflicting simultaneous operating policy, surface
the concrete difference, not a broad repeated questionnaire. The user's standing
rule still requires confirmation before any new firmware compile; no compile or
upload is authorized by this audit.

## Baseline checks actually run

- `python-embed/python.exe -m unittest discover -s apps/gld-operator/tests -p test_workflow_routes.py`: **4 passed**. Inert route dispatch/admission only.
- `python-embed/python.exe -m unittest discover -s firmware/tests -p test_dataset_workflow_source.py`: **13 passed**. Current dedicated source-isolation/ownership contract only; no compiler or device execution.

These checks establish the existing protected boundary; they do not prove that
the requested normal-feature integration is implemented. This worker wrote only
this report and did not change application or firmware source.
