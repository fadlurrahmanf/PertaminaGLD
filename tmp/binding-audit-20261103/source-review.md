# Read-only binding audit — 3 November 2026

Scope: current firmware/UI source only. No GLD, COM, network, service, firmware/package, calibration, approval, binding or NVS action. Parent owns live read-only status inspection. This report is the only file written by this audit.

## Reconciliation with the parent's live snapshot

Parent reports `live-snapshot.json`: GLD1002 on COM7, native INFERENCE, installed **Model 2** (`cnn-dualbranch-board-2-2class-v2`), `productionApproved=false`, bound profile **1**, active profile **2**, `bindingValid=true`, `bindingModelMatches=false`, `profileReady=false`. Sensors valid/primed, ML initialized, nulling applied and DAC verification are all true. Wireless sessions are disconnected; no persistent action was taken.

There are three distinct readiness problems: saved binding fingerprint differs from the currently installed named model/scaler pair; binding refers to old local profile 1 instead of applied profile 2; and the installed Model 2 is unapproved. “Use Latest Nulling Profile” **cannot fix the current unit now**, because the bind handler rejects Model 2 at its first production-approval gate before any binding write. Sensor/DAC re-null or NVS reset is not indicated by these status values. `bindingValid=true` merely means the old record is structurally valid; it does not contradict those mismatches. Without its saved fingerprint, do not assume the old record specifically belongs to Model 1 rather than another model/profile revision.

Next decision is to establish which model is intended for this physical unit. If Model 2 is intended, retain its approval gate and complete the separate board/gas validation and explicit approval process before proposing a firmware change. If another model is intended, first verify the correct model/board/calibration pairing and separately authorize any firmware action; do not switch models merely to make the indicator green. Once the correct approved model and correct complete applied calibration are established, an explicit bind can synchronize that pair, followed by fresh read-back. This audit does not authorize any of those writes.

## Exact interpretation of status

Source: `firmware/gld/src/GldUnifiedMain.cpp:355`, `:1834`, `:2715`, `:6075`.

| Read-back | Meaning |
|---|---|
| `model.bindingValid=false` | No valid binding record was loaded; missing, invalid magic/schema/checksum/size, or a failed binding write. Does not prove a sensor or model-file fault. |
| `bindingValid=true`, `bindingModelMatches=false` | A valid saved record exists but its fingerprint differs from this compiled model/scaler **profile-name pair**. Typical after changing model/metadata. |
| `bindingModelMatches=true`, `boundNullingProfileId != activeNullingProfileId` | Model-name pair matches but binding refers to an older/different local calibration. Binding must explicitly reference the applied current complete profile before readiness opens. |
| IDs match but `profileReady=false` | Check ML initialization, applied nonzero nulling profile, production approval, and valid loaded binding. Binding equality alone does not satisfy every prerequisite. |
| `profileReady=true`, `inferenceValid=false` | Binding/model/profile gate is satisfied; actual sensor validity/priming, DAC readback or NN execution may still block inference. |

`gld1InferenceBlockerName()` reports its **first** blocker: scan observed → all sensors valid → primed → ML ready → profile applied → binding loaded → fingerprint matches → model profile ready → DAC verified → NN attempted/succeeded → inference valid. Sensor/priming faults can therefore hide a binding fault. `model_profile_not_ready` is generic and can mean approval/profile-ID mismatch; it is not a precise proof that rebinding is sufficient.

## Bind command effects and preconditions

`onBindModelToActiveNullingProfile()` rejects nonproduction/field-test/continuous-battery overrides and unapproved models; requires mode INFERENCE/Running, no armed nulling retry, an applied nonzero profile, and a freshly loaded saved profile whose ID equals the applied ID. `loadNullingProfile()` validates magic, current algorithm version 16, all 8 `channelOk==1`, and DAC codes ≤4095.

Successful bind constructs a 16-byte `GldModelBinding` with schema 1, current local profile ID, fingerprint and checksum. `GldModelBinding.cpp` writes only NVS namespace **`gld_model`**, key **`binding`**; it invalidates the previous record, writes the new record and verifies read-back. RAM binding flags/readiness are then updated. Persistence failure clears the RAM binding/readiness and returns an error.

The handler does **not** run nulling, change DAC voltages/codes or the saved calibration, reset MAV, change model/scaler weights, change operating mode/defaults, reboot, or directly drive an alarm. However, a successful bind can enable the **next normal inference**, which may change AUTO alarm output and permit ordinary LoRa telemetry. It is a persistent configuration action, not a read-only UI refresh. Do not execute it merely to diagnose status under this audit.

The final hotspot session guard also rejects bind as busy while recording, paused, replaying or draining/finalizing. Stop, verify/finalize the CSV and Disconnect first; no active wireless session should be disturbed to perform this check.

## Models and limits of “sync”

| Installed model | Profile/scaler name | Source approval | Fingerprint |
|---|---|---|---|
| 1 | `cnn-dualbranch-board-1-2class-v2` | true | `38fb9215` |
| 2 | `cnn-dualbranch-board-2-2class-v2` | **false**, explicit field validation/approval pending | `c95e51df` |
| 3 | `cnn-dualbranch-board-3-2class-v1` | true, board testing approved; field accuracy remains unestablished by host/build checks | `7ed418bb` |

Fingerprint is 32-bit FNV-1a of `PROFILE_ID + "|" + SCALER_PROFILE_ID`. It identifies the named pair, not a cryptographic hash of NN weights, scaler bytes or physical board identity. There is one binding record, not a three-model binding history. Switching models overwrites/requires the relevant explicit binding; changing metadata names invalidates that match. A new complete nulling profile deliberately needs a new explicit operator bind.

Binding does **not** mathematically adapt a model/scaler to new calibration, retrain it, or prove gas accuracy. Local `profileId` is a calibration sequence number, not a scientific cross-board compatibility identifier. Use the model intended for the physical board/sensor assembly and an appropriate complete clean-air calibration. Model 2's approval gate cannot be repaired by repeatedly pressing Bind or copying another model's binding; do not bypass its approval flag.

## Safe UI synchronization sequence, only if a later action is authorized

1. Keep the installed firmware/model and Running mode unchanged; confirm physical model/board identity and 24 V supply. Read fresh status first. If a wireless Dataset session exists, finish it normally before any bind action.
2. Compare `productionApproved`, `bindingValid`, `bindingModelMatches`, bound/active IDs, `profileReady`, applied profile and DAC readiness. If already matching/ready, only refresh status; no rebind is needed.
3. If only the binding is missing/mismatched and the approved model has a stable applied complete calibration, open **Running → Settings → Model & Nulling Profile → Use Latest Nulling Profile**. Its dialog explicitly states it saves an NVS binding. Confirm only the current correct model/current complete profile pair.
4. Require matching command ACK `BIND_MODEL_TO_ACTIVE_NULLING_PROFILE` with `status=ok`; then **Refresh Status**. The UI also sends `GET_STATUS` automatically. Verify both IDs match, `bindingModelMatches=true`, `bindingValid=true`, `profileReady=true`; then allow a normal scan and inspect `inferenceValid`/readiness. ACK success alone is not inference/gas-validation success.
5. If no complete applied profile, ML/DAC/sensors fail, or Model 2 remains unapproved, stop at diagnosis. This audit does not authorize new nulling, model changes, firmware builds, approval edits or NVS actions.

## Existing UI limitation: do not mistake green binding for full readiness

`apps/gld-operator/js/serial-protocol.js:301` formats “Model bound to profile #X; active profile #Y” from only `bindingValid && bindingModelMatches`, without comparing X/Y. `apps/gld-operator/js/expert.js:61` similarly marks its binding row true from those two booleans; it does not include profile-ID equality or production approval. Consequently that row can appear ready while `model.profileReady=false`. The raw status IDs plus `profileReady` remain authoritative for this audit. No UI/source correction is made under read-only scope.
