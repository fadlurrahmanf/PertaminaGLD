# Compact CSV integration audit

Scope: read-only source/test review by Integration_Agent. Parent owns every
production edit and all service/hardware actions. This worker writes only this
report. No COM, WLAN, firmware, service, user CSV or source change.

## Contract and protected boundaries

- New public CSV has exactly 12 base columns: device time in milliseconds,
  complete test label, eight sensor voltages in canonical feature order,
  Predicted Class, and Confidence. Gain/status each add a complete eight-column
  group only when selected. Their defaults are off.
- Prediction checkbox remains an acquisition/model-readiness decision; it no
  longer determines whether the final two headers exist. Disabled/invalid
  predictions produce empty cells. Class zero and confidence zero remain real
  numeric values when valid. Confidence retains its prior 0..1 scale.
- Full wire/canonical JSONL keeps session/boot/sequence/model/profile IDs,
  timestamps, complete prediction status and timing, gain and status, regardless
  of public CSV selection. No wire or firmware change is needed.
- Existing CSV files must not be rewritten. Existing create-exclusive,
  hash/schema/config identity, same-file Continue and Reset/new-file guards
  remain authoritative.

## Source findings before implementation

1. `csv_columns` and `project_record` are workflow-specific. Old Stage1/Replay
   collectors do not import them, so the boundary is naturally narrow.
2. Production `_verify()` zips public CSV with the full canonical ledger and
   already checks `record['row_id'] == count`. It does not require a public
   row_id column; preserve that internal check unchanged.
3. `_open_first()` freezes the chosen headers/config; `_open_append()` enforces
   both file digests, schema configuration, device/model/profile and label
   timestamp. Do not loosen these while removing public metadata.
4. `_persist()` writes and fsyncs both canonical and CSV before ACK. Direct
   cleanup writes quarantine metadata privately. No reason to modify this
   transaction, rollback or ownership behavior.
5. Existing test helpers and timestamp assertions reference old CSV names and
   must be adapted. Their canonical row/segment/sequence assertions remain
   useful and should not be removed.
6. The earlier real-wire simulation verifier indexes public CSV by session_id
   and seq. Compact CSV fixtures must pair rows with canonical records in row
   order rather than restore technical IDs to the public file for tests.
7. The current onscreen table uses public-looking Baris/Waktu headings and
   conditional prediction headers. If aligned with the new export it should
   derive its twelve values from canonical history and retain ten visible rows;
   chart/acquisition history need not change.

## Regression acceptance

- Independently assert exact 12/20/28 header sets, no partial optional groups,
  no public technical metadata, and full private metadata.
- Check disabled/warmup/error/not_ready blanks, normal valid predictions and
  zero-valued valid class/confidence.
- Preserve Pause/Resume, Stop verification, Continue new SID/global row order,
  Direct cutoff/private cleanup, Replay same-file recovery, unknown control
  reconciliation, fsync failure/no ACK and tampered-file rejection.
- Validate browser download equals the actual saved compact CSV. Pair public
  rows with ledger order in independent verification.
- Before activation, parent must recheck stock service idle. If recording,
  connected or owning a continuation file, do not restart it merely to deploy
  this schema revision.

## Final source review and verification

Parent source-ready notification received. Compared the current backend, UI and
HTML against `before/` backups. Backend diff is limited to public headers,
projection and gain/status defaults. AST comparison of every service method
confirms that only `_clear_form` changed; persistence, ACK transaction,
verification, continuation, cleanup, recovery and controls remain unchanged.

The UI removes timing from the visible options and always submits timing=false;
gain/status defaults are off. Prediction model-readiness gates remain intact.
All internal metadata is retained because the unchanged canonical writer still
serializes the complete record before projecting the public CSV.

Verification run by this worker:

- **174 GLD Python tests PASS**, 13.418 seconds. Includes the new exact-header,
  all optional-group combinations, canonical metadata, disabled/invalid and
  zero-valued prediction, and tamper-preservation cases; existing Pause/Resume,
  Stop/Continue, Direct/Replay, ambiguity, failure/durability and bounded-history
  tests also pass.
- **Node workflow UI PASS**: cumulative steps, controls, locking, stale updates,
  error behavior and verified-only popup.
- **Node shared chart PASS**: Running baseline remains unchanged; workflow
  chart retains its independent feed/time/eight traces/gaps.
- No service, native WLAN, COM, firmware, upload, persistent recording or user
  file operation was issued by this worker. Browser download and idle service
  activation remain parent-owned gates, not claimed here.

One nonblocking presentation boundary: the website's existing last-ten-sample
table still displays row identity and omits the full label, while the exported
CSV is compact. This does not change its underlying sample values; do not claim
that table headers are identical to export headers unless separately updated.

Conclusion: **PASS for the inspected source and automated regression scope**.
No durability/control regression or exported metadata leakage found in this
patch. Existing on-disk CSVs are not migrated or rewritten.

## Operational follow-up: duplicate GLD hosts

Parent reported a later full-Hub instance with GLD/CH/Gateway children alongside
the earlier no-children Hub and standalone GLD replacement. This section is a
read-only source audit, not process or flow-state confirmation.

Relevant current source:

- `operator-hub/bridge.py:983` launches each child once; it does not monitor and
  automatically restart a manually replaced GLD process.
- With a broker configured, GLD receives `--mqtt-broker-host` and
  `--mqtt-broker-port`; authentication is passed only in child environment
  variables `GLD_BENCH_MQTT_USER` and `GLD_BENCH_MQTT_PASSWORD`.
- The exact private source in current code is
  `archive/apps/runtime/operator-hub/credentials.local.json`. Do not call
  `load_or_create_broker_config()` to inspect it: that function writes the file
  and may rotate an absent/short password.
- GLD owns the embedded broker in the same process as its HTTP bridge. Killing
  that GLD can therefore disrupt MQTT even if workflow/COM snapshots are idle.
- `/api/health` exposes public broker running/host/port/authRequired, but does
  not expose broker client or legacy MQTT Dataset monitor counts. The broker's
  established TCP connections and GLD outbound monitor connections need a
  read-only OS ownership check before replacement.

Safest GLD-only replacement gate for the parent:

1. Identify all actual GLD HTTP owners by command path/process ownership; do not
   stop unrelated Hub, CH, or Gateway processes.
2. Verify no workflow, old wireless collector, serial slot, owned CSV/cleanup,
   or established embedded-broker/MQTT monitor connection is active. If MQTT
   clients are active, do not treat empty workflow snapshots as restart consent.
3. Read the existing private broker JSON in memory only. Match host and port to
   old-child arguments and public health metadata. Preserve credentials without
   printing/logging them or placing them in a command line; retain the same
   broker host/port arguments and inject authentication through the environment.
   Do not silently change a no-longer-local LAN bind address.
4. Once the idle gate is established, remove the duplicate GLD HTTP owners and
   start exactly one current GLD bridge with the preserved broker configuration.
   Leave the existing full Hub, CH, Gateway and their environments unchanged.
5. Confirm one listener/owner, stable API defaults gain=false/status=false over
   fresh connections, health identity, broker running state and current UI.
   Token uniqueness can be checked through hashes/counts without exposing token
   values if duplicate request routing remains uncertain.

No actual process, port, broker client or service-state inspection/mutation was
performed by this worker in the operational follow-up; the parent owns those
checks and any restart.
