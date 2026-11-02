# Dataset Wireless replay — protocol 2 contract

Scope: one GLD1, external 24 V, 8 channels every 500 ms; volatile RAM while GLD remains powered. No router support, NVS changes, calibration changes, deployment, compile or hardware operation in the source implementation phase.

## Isolation

Keep protocol `gld-dataset-wifi/1`, `GldDatasetWifi.cpp`, `WirelessDatasetCollector`, existing build targets and all existing packages intact. Add protocol `gld-dataset-wifi/2`, a separate firmware module and three `gld_model_{1,2,3}_dataset_replay_wifi` environments. They inherit the corresponding Stage1 target with an additional replay flag and include, without changing the inherited model/pins/nulling configuration. The Unified call sites select the new module only with `PGL_GLD_DATASET_REPLAY=1`. Sample type/capture callback stay unchanged.

Add a separate replay collector and `/api/wireless-replay/{state,connect,start,stop,disconnect,export}` API. Emit `wireless_dataset_replay` events. UI explicitly selects direct Stage1 or five-minute replay; Stage1 stays the default. All COM and both wireless transports must be mutually exclusive while a wireless session is active, including recovery. Merely selecting another UI mode cannot terminate an active recorder. Existing Stage1 CSV schema remains identical.

## Device storage and sending

- Use a fixed ring of **640 compact sample records**, not 640 JSON strings. Each retained record stores its original seq, timestamp/scan end, voltage/gain/status and overrun count; device/session/label/profile remain immutable per session. At 2 Hz this covers 600 records for five minutes with 40 records of margin.
- Capture continues through transport loss. A successful socket send never releases a record. Release only the contiguous prefix acknowledged as persisted by the PC.
- Sample sequence starts at 0, remains monotonic across reconnects, and retains acquisition timestamps. Replay oldest first; live acquisition continues and appends behind the backlog. Bounded in-flight window (8 records maximum) and short control queue; no unbounded allocation or network call in sampler.
- Once an observed outage reaches 300000 ms, or ring capacity is exhausted, stop sampling, keep every retained record, and expose an incomplete terminal reason (`retention_limit` / `buffer_full`). Never silently overwrite an unacknowledged record. Retained samples remain available for later recovery while powered; five minutes is the supported acquisition outage, not a timer deleting evidence.
- Track link loss and stalled ACK progress so a half-open TCP connection also reaches the bound. Allocation/startup failures fail closed; AP visibility alone is not readiness. Do not touch ADS outside the sampler after setup.

## Wire messages

Endpoint stays `ws://192.168.4.1:81/dataset`; existing WPA2 + Basic authentication, user `gld`, private per-environment credential. No credential in snapshots/events/logs. Protocol 2 uses the same feature order, sample validation and CSV fields as protocol 1.

Hello includes existing identity/schema/readiness plus:

```
protocol: gld-dataset-wifi/2
boot_id: 32 lowercase hexadecimal chars, generated once at boot
retention_ms: 300000
capacity: 640
session_id: current retained session or empty
label: current label or empty
nulling_profile_id: current profile
total_samples: exclusive next acquisition sequence
oldest_seq: earliest retained sequence (total_samples if empty)
acked_next_seq: acknowledged exclusive prefix
sampling: boolean
incomplete: boolean
reason: controlled text
```

`START_DATASET` / `STOP_DATASET` keep command_id and session_id. Start also includes label and sample_interval_ms=500. Matching ACK plus status confirms Start. Start must not replace an active session or retained samples. Exact duplicate Start/Stop command IDs are idempotent; unexpected commands cannot reset the ring.

New `RESUME_DATASET` includes `command_id`, `session_id`, `boot_id`, required `label`, `next_seq` (exclusive contiguous prefix already persisted by PC). Validate boot, session and label identity, `acked_next_seq <= next_seq <= total_samples`, and availability of every requested record. Reject a rollback, different boot/session or impossible prefix; never fall back to a fresh Start. Resume may discard the newly confirmed prefix, then matching ACK and status precede replay. Status includes sampling, incomplete, total_samples, oldest_seq, acked_next_seq and buffered_samples. `state` is `running` while sampling, `stopped` for a stopped drain, `error` for terminal sampling failure. Retention/overflow reason and incomplete are sticky across Stop. At exactly 300000 ms, check retention before a new acquisition or Resume; terminal metadata and summary survive a lost summary send even with an empty ring.

New `ACK_SAMPLES` includes `session_id`, `boot_id`, `next_seq`. It is an idempotent cumulative confirmation, not a state-changing Start. It needs no command_id or response. Validate identity/bounds and never accept a forward acknowledgement beyond records actually offered to that connection. Duplicate/older valid ACKs do not release anything further. Process ACKs promptly; a replay burst must not overflow a tiny command queue.

Samples preserve their original Stage1 payload fields. Summary includes total_samples, reason, incomplete, overrun_count. Queue a summary only after all captured records have been offered and acknowledged, and only when sampling has stopped. After reconnection resend the pending terminal summary. The next Start is allowed only when prior retained samples are acknowledged and the terminal summary was sent. Final status/summary is not inferred from TCP success.

## PC collector

- Keep the same file open across recoverable drops. Confirm each valid contiguous row with ACK only **after CSV write + flush + fsync**. Snapshot/events contain no password; a password may remain only in process RAM for authorized reconnect and is cleared on explicit disconnect/terminal closure.
- Deduplicate a repeated already-persisted seq and re-ACK its contiguous prefix without a second CSV row. Reject noncontiguous future records, changed profile/label/device/boot, malformed arrays, nonfinite values or wrong channel status; never silently fill gaps or certify a damaged CSV.
- On transport EOF or sample silence while active, enter recovering and reconnect to the fixed endpoint with bounded exponential delay (1/2/4/8 seconds capped). Retry attempts continue until explicit cancellation, fatal validation/disk error or terminal reconciliation; do not impose an arbitrary attempt count that discards a still-recoverable retained prefix. One worker with bounded requests/backoff, no OS Wi-Fi switching. Reconnect/Resume is automatic; Start is never automatically resent. Reconcile an ambiguous Start only by Resume of its exact session, otherwise fail incomplete.
- Before resuming, validate hello device/boot/session/label/profile against the current session. Resume uses `next_seq=last_persisted_seq+1`. Replay writes into the same file, preserves original times and returns to live recording after catching up. Expose connection/recovery/replay/buffer state and saved count separately.
- A Stop explicitly requested while recovering may be queued as stop intent; resume first, then send/reconcile the same idempotent Stop command ID. Do not claim completion before Stop ACK + terminal summary + exact sample-count reconciliation. If Stop intent was never delivered, UI must say pending, not stopped. Explicit Disconnect cancels retries and closes the session incomplete if not finalized; it cannot silently stop remote sampling while offline.
- Reboot, identity mismatch, invalid prefix, disk failure, retention overflow, or unrecoverable protocol error marks CSV incomplete with a clear reason. Recover all available retained records for a terminal retention/overflow session, then reconcile its incomplete summary. Never automatically append data from a new device/session or reset sampling.
- PC backend restart/crash recovery is outside this phase; UI/browser close is supported. Do not promise RAM survives GLD reboot. Five-minute replay requires the backend process to remain alive with its session identity/prefix.

## Acceptance gates

Executable host tests must cover normal Start/Stop; one and repeated disconnects; retained >600 records within five minutes; reconnect at the 300s boundary; 301s/overflow without overwrite; ACK loss/duplicate replay; disconnect during replay; ambiguous Start and Stop; device reboot/wrong session; disk failure before ACK; malformed/gap samples; explicit cancellation; sample-silence handling; CSV continuity/all fields/original timestamps/sequence; protocol1 regressions; API mutual exclusion; UI state and stale snapshot guards.

Source checks protect all old env/model flags, unflagged Unified behavior, Stage1 module/collector and existing package hashes. Build proof and physical Model1 outage/replay proof are separate later gates requiring the user's compile/upload authorization.
