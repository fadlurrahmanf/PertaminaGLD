# Wireless Dataset workflow firmware — protocol 3

Latest UI revision 2026-11-03: five grouped steps, cumulative readiness, backend-only credentials, timestamp label, shared Running chart and export below table. Current report: gld-dataset-wizard-ux-20261103.md; manual output/pdf/Manual-GLD-Dataset-5-Langkah.pdf. Firmware/protocol/binaries unchanged. Current app Hub6204/GLD12940. Earlier seven-step screenshots/PIDs below are historical; physical release gate remains deferred (95% release).


Status update: Model1/2/3 firmware builds and the isolated Hub wizard now pass PC
release gates; physical-device validation is still pending. See
[release evidence](gld-dataset-workflow-release-20261102.md). Existing protocols1/2, packages, saved nulling and operator CSVs stay
protected. Scope: GLD1 Model1/2/3, external24V,8sensors, target500ms and five-minute
volatile acquisition retention. The original source checkpoint did not authorize
compile; the user's later instruction to finish all work authorized the three
parallel builds. No upload, COM or physical Wi-Fi action was performed.

## Boundary

Three new `gld_model_{1,2,3}_dataset_workflow_wifi` environments inherit their
matching Stage1 Dataset target. Only `PGL_GLD_DATASET_WORKFLOW=1` selects the new
module/hooks; the Stage2 replay flag is not enabled. No package post-hook.
`gld-dataset-wifi/3` uses the existing authenticated endpoint, Basic username,
private password and `GLD-DATASET-<id>` hotspot. The first approved build keeps
the matching operator password by copying validated private protocol2 config to
a separate ignored workflow config. It never rotates or mutates the old config.

Firmware supplies device identity, readiness, capabilities, timestamped samples,
optional predictions and acquisition controls. Windows scanning/joining Wi-Fi,
file picking, CSV projection/verification, wizard numbering, Lock and Reset are
Hub responsibilities. The original protocol1/2 collectors still reject protocol3;
the new wizard uses an isolated compatible workflow service. Existing protocol2
images and their Expert controls remain available alongside the new packages.

## Acquisition versus transport

`START_DATASET` admits a new session only after the previous session has stopped,
all retained samples are durably acknowledged, and its terminal summary has been
sent. Interval must be500ms, label/ID valid, externalpower/nulling/ADS ready.
`prediction_enabled` is an optional boolean defaultfalse. Duplicate Start must
match session, commandID, label, interval and prediction option; no reset/restart.

`PAUSE_DATASET` stops acquisition, invalidates an in-flight capture before its
ACK, preserves session/sequence and retained data, and emits no terminal summary.
It does not freeze only the webpage. Pending samples still drain into the same
file. A confirmed Pause is distinct from a transport dropout.

`CONTINUE_DATASET` resumes acquisition only for the same paused session. The
next due time is now+500ms; paused time is not backfilled. Sequence continues;
timestamps show the real gap. Prediction moving-average state is freshly primed
after Continue, by the sampler only.

Pause/Continue include boot/session identity and `transition_seq`: initial0 at
Start, exactlylast+1 for each new transition. An exact duplicate of the last
accepted `(seq,commandID,command)` acknowledges without another mutation. Stale,
skipped or conflicting requests fail closed; they cannot re-pause a later state.
Hello/status expose the accepted sequence and paused state for reconciliation.

`RESUME_DATASET` remains transport/durable-prefix recovery only: it validates
boot/session/label/prefix and replays retained data. It must never unpause the
device or create a new session. `ACK_SAMPLES` remains cumulative durable ACK.

`STOP_DATASET` works while recording or paused, uses its stable idempotent
commandID, and closes acquisition. It cannot clear an incomplete reason. Summary
requires all samples offered+ACKed, acquisition stopped and **not paused**.
Stop while disconnected remains pending in the Hub until reconciled.

After Stop, the user's **Continue into the same CSV** is a Hub file-session
feature: a fresh GLD Start/SID creates the next segment, with its own sequence0,
inside the same logical recording. Firmware must never reuse a finalized SID.
The Hub preserves segment boundaries, timestamps, schema and actual device/model
identity; it must refuse incompatible append. Reset never erases device NVS or
existing CSV and must first settle any owned remote session.

## Storage and loss

Retain640 compact frames with window8. No network I/O or second ADS reader in the
sampler. ACK may release only the prefix offered on the authenticated connection;
successful socket send is not durable storage. On loss, retain original timestamps
and prediction results. At300000ms without ACK progress while acquiring, or on
capacity exhaustion, stop incomplete and retain remaining data while powered.
Pausing never deletes pending data. Reconnecting does not automatically resume
acquisition from Pause. Power loss clears RAM; backend-crash recovery is outside
this revision.

Direct versus automatic recovery is a Hub CSV policy on the same firmware. Direct
freezes the public CSV on first loss and privately closes/drains its owned session;
automatic recovery appends replay into the same CSV. Neither mode permits stopping
foreign sessions or retrying an ambiguous Start as a new Start.

## Prediction

Hello advertises the model/scaler identity, approval/output/class mapping metadata
and whether real inference is ready. Raw recording remains available when the
model is unavailable. A Start requesting prediction must be rejected when the
model, production approval or active-profile binding is not valid.

Inference uses the already captured canonical8-channel frame and the existing
moving-average/model preprocessing, with no extra sensor reads. The sampler owns
the prediction context. A captured frame's prediction is retained with the frame;
replay must not recompute it using newer sensor data or model state.

Each frame includes a prediction object with `enabled`, `status`, `valid`,
`predicted_class`, `gas_class`, `confidence` and `inference_duration_ms`.
Statuses distinguish disabled/not_ready/warmup/error/valid. Class and confidence
are null when invalid; zero is never a placeholder prediction. Valid confidence
is finite0..1; predicted class is an actual output index and mapped gas class is
checked against model metadata. Ground-truth label remains separate.

The compact retained record budget is at most96bytes,640records at most61440bytes.
Actual struct size, total RAM, inference duration and500ms deadline still require
the three approved builds and real-device timing tests. Source assertions/review
are not proof of those runtime properties. Overrun remains observable.

## Verification gates

Source checks protect all old modules, existing env configurations, no-workflow
Unified behavior and existing package/CSV hashes. Temporary-fixture credential
tests validate inheritance, limits, ownership, no mutation/rotation or secret leak.
Review covers pause/stop in-flight races, stale transition commands, Stop while
paused, transport Resume not unpausing, terminal summary exclusion while paused,
durable ACK/window limits, model readiness/priming and per-frame prediction replay.

Firmware compile and physical validation require separate authorization. No new
Hub package/compatibility claim is made before the new firmware and Hub adapter
have both passed integration and device gates.
