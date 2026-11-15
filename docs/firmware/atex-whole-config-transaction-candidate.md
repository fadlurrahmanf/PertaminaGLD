# ATEX whole-configuration transaction — design candidate

Status: design and host prototype only. Do not wire this partial prototype to
production or open the ATEX release gate. T31 radio/QC remains separately held.

## Why QC-only persistence cannot preserve SET_APP_CONFIG

`onSetAppConfigJson` in `firmware/gld/src/GldUnifiedMain.cpp` accepts LoRa fields
in the same command as network settings, credentials and AES, and calls
`saveRuntimeConfig`. Serial device-ID, CH-ID and LoRa setters also call that
function. A separate QC record can therefore publish only half a user command.
`saveDownlinkReplayState` writes `lastCmdId` separately, so a whole-app snapshot
that ignores that path could restore an older anti-replay counter after reboot.
A user-visible success must mean the complete requested update was published,
not merely that one key or one of two namespaces was written.

`Preferences::isKey`, `getUChar`, `getBytesLength` and `getBytes` collapse
missing keys and some I/O errors into the same fallback. The experimental raw
NVS adapter preserves explicit error codes. Real IDF NVS atomicity and recovery
must be verified on the installed version and with actual power-cut tests; host
mocks establish only logic under their stated per-operation atomicity model.

## Proposed ATEX-only contract

- Store one explicitly serialized, versioned full configuration snapshot:
  device/node/CH IDs; SSID and password; MQTT host, port, user, password and
  topic; AES presence, key ID and key bytes; downlink replay counter; all LoRa
  electrical parameters; QC interval, focus, target and auto flag. Exclude
  volatile alarms and transient radio/inference state. Include all fields that
  participate in `SET_APP_CONFIG_JSON` and all persisted fields of RuntimeConfig.
- Use fixed endian/length encoding with bounded strings, reserved bytes and a
  record version/checksum. Checksum detects corruption, not malicious tampering.
  Avoid serializing compiler padding or printing secret values. Do not weaken
  existing storage protection: verify existing NVS encryption/flash settings;
  a blob or checksum is not encryption.
- Stage an entire candidate from an immutable copy; validate *all* IDs, radio
  settings, lengths, AES semantics, QC cross-field rules and schema first. Do
  not mutate live runtime or restart the radio on a rejected/failed save.
- Use two record slots and one active marker, with a single atomic publish of
  the marker only after the new complete record has been written and verified.
  These are multiple NVS operations, but only one marker operation makes the
  whole new configuration visible. Preserve the previously active record until
  publish. No other namespace is a second authority for these fields.
- A publish/commit error or inconclusive reread is UNKNOWN, never a definite
  rollback or success. Disable automatic and manual ATEX TX and further config
  mutations until exclusive reopen/reconciliation. On reboot select only a
  valid active marker and validated pointed record. Missing/corrupt marker or
  invalid selected record must not silently fall back to a stale slot or prior
  legacy configuration. ACK loss after a successful commit remains ambiguous;
  expose a readback/reconciliation path and avoid retrying blind.
- One lock/owner must serialize every read-modify-write, including all serial
  setters, MQTT/LoRa-originated changes, key rotation and replay-counter
  updates. A workflow lease is not an NVS mutex. Persist a verified monotonic
  command ID before ACK/action as current protocol requires; coordinate an AES
  key rotation and its replay reset in the same snapshot. Determine flash-wear
  impact of writing the full blob per accepted downlink before release.
- Legacy migration is explicit and one-way for the selected physical ATEX
  device: obtain raw NVS results, require a valid legacy ctrlword/schema and
  fully validate all source fields, including key/replay binding. Supply safe
  ATEX QC defaults deliberately. Snapshot+verify then publish once. A missing
  marker alone cannot prove first boot rather than erased/corrupt state; an
  explicit migration decision is required. Never resurrect legacy keys after a
  migrated marker/record becomes unknown. Define NVS reset and downgrade behavior
  before enabling this migration. A downgrade using old `gld_app` keys could
  otherwise restore stale credentials/IDs and replay counters.
- Restrict all new paths by ATEX workflow profile; GLD1/GLD2 and existing
  packages retain their current preprocessor-selected implementation. The
  separate legacy keys should remain untouched until an approved migration and
  recovery strategy exists, without claiming interoperability with downgrade.

## Concrete implementation work

1. Replace the experimental 48-byte QC-only payload with a versioned full-app
   codec, a validated snapshot type, and maximum-length calculations; use only
   synthetic credentials in tests. Keep the raw-NVS backend API explicit about
   NOT_FOUND versus I/O errors and commit uncertainty. Verify buffers and NVS
   partition capacity for two snapshots and migration overhead.
2. Add an ATEX-only storage owner and lock; route `loadRuntimeConfig`,
   `saveRuntimeConfig`, `saveDownlinkReplayState`, every serial setter and any
   LoRa/MQTT writer through it. Refactor mutation sites to stage/validate a copy
   before committing, and apply it after definite success. Route automatic and
   manual radio start through its known/ready state. Define serial/UI responses
   and recovery for UNKNOWN without logging secrets.
3. Implement explicit first-time migration, corrupt-record and NVS-reset paths;
   specify downgrade, anti-replay, key-rotation, snapshot version and recovery
   contracts before shipping. Preserve GLD1/GLD2 binary/source isolation tests.
4. Integrate with the separately redesigned nonblocking QC radio scheduler;
   neither component alone makes QC complete or proves RF safety.

## Verification required

- Native tests exercising production codec/validation and storage owner with
  mock NVS: max-length UTF-8/ASCII strings, every field/round trip, invalid
  lengths/booleans/float/CRC/version, secrets absent from diagnostics, corrupted
  active pointer, truncated blob and namespace/I/O errors.
- Fault injection at each snapshot write/read, verification, marker write,
  commit, post-commit read, reopen and ACK boundary; simulate reboot after every
  stage. Assert no mixed config, no silent fallback, UNKNOWN disables TX, and
  no "error means old" promise when the final publication is uncertain.
- Actual command-handler integration with combined radio+network+AES payloads,
  each individual setter, device/CH ID, save failure and retry, radio reinit
  failure, all session/lease states, serial reentrancy and concurrent downlink.
- Replay and key-rotation tests: old/equal command IDs rejected after reboot,
  failed persistence never acknowledges a state change, full command executes
  at most once, no stale replay ID after migration or concurrent setter.
- Legacy: valid/invalid schema and ctrlword, old firmware without QC keys,
  missing/corrupt active marker versus genuinely uninitialized device, NVS
  reset, partially completed migration, downgrade/restore and device identity.
- Protected GLD1/GLD2 preprocessing, behavior tests and all previous packages;
  all three ATEX model builds with synthetic credentials; no production secret
  reads in test logs. Validate layout size and write/endurance assumptions.
- Only after authorization and existing release gates: real-board power-cut
  tests at write/commit phases, readback and recovery, NVS encryption and
  endurance checks, physical RF/alarm/power and model validation.

## Feasibility and effort

The full codec, mocked owner, commands and fault matrix can be implemented now
in a separate worktree with synthetic data. It requires coordinated ownership of
`GldUnifiedMain.cpp` with the QC radio worker, and an integration contract for
all existing command paths and downgrade; merging only the current QC prototype
would be unsafe. Estimate: roughly 2–4 focused engineering days for a complete
candidate and review, plus separate real-device power-cut, durability and model
validation. This is a planning estimate, not a completion or safety guarantee.
