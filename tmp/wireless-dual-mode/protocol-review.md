# GLD protocol2 Direct adapter review

Read-only GLD_Agent review, 2026-11-02 WIB. No device, COM, network, service,
firmware edit, build, upload, or credential action. Runtime edits belong to the
backend worker; this report is the reviewer's sole output file.

## Status

PASS — source/host review of the exact final adapter revision below. No
remaining concrete protocol or frozen-CSV blocker was found. Initial findings
were fixed by the backend owner and covered by regression tests.

Final adapter SHA256:
`b0843ab897abf3856ecda5f98d445a6144d192cfb9445df0fb59fc7ff9a95ab1`.

Independently executed, using the bundled Operator Python:

```powershell
& apps/gld-operator/python-embed/python.exe -m unittest discover -s apps/gld-operator/tests -p test_wireless_direct_collector.py -v
```

Result: **24/24 PASS**, 0.957 seconds. All peers were in-process fakes and all
storage test files were temporary; no server or network service was launched.

Initial adapter SHA256:
`d4b6cae0812161b45a5332ae0bca34ffe4244bb26e8a3a43c7e4bfc2c6a2c7b1`.
Intermediate adapter SHA256:
`cd303cc79dc82c41d3da6980a2359523056dcf7e887a45d1b18e7508cf1a5b01`.
Release-gate adapter SHA256:
`e7a4d70188f64c7fd1cef218a7fba758e438247286c1686ee16f28d74d1779e5`.

Protected collectors observed unchanged:

- `apps/gld-operator/wireless_dataset.py`: `7b371765307121c21953eafa414fb3fa4b87af4db76d759a473e48b03cf4e03e`
- `apps/gld-operator/wireless_dataset_replay.py`: `057e1ef21c6085ef6787ddde2e1614fbe319ac53e30f70b80d6a8bd0e2d27745`

## Findings delivered to root and backend owner

1. Explicit correlated START rejection originally entered owned cleanup even
   though firmware rejected the new session without registering it. Reconnect
   then failed session identity and permanently blocked a new attempt. The
   intermediate revision handles `device_rejected_start_dataset` separately.
2. Original CSV seek/truncate/flush/fsync/close failure was overwritten by a
   later cleanup error reset. The intermediate revision preserves a distinct
   sticky `original_csv_error` and makes export fail closed.
3. Failed private cleanup-sink initialization left an open file handle. The
   intermediate revision closes it before pausing and safely reopens from its
   durable offset.
4. START genuinely not delivered,
   followed by authoritative same-boot hello showing empty or previous session,
   must not become an unrecoverable owned-cleanup lock. Never Stop/Resume a
   foreign session or resend START. Accepted START with lost ACK must still
   clean up the exact owned session. The release-gate revision now releases only
   after a fully validated hello proves same-device new boot, or same-boot
   absent session with sampling stopped and `acked_next_seq == oldest_seq ==
   total_samples`. This gate sends no Stop/Resume to a foreign session. Active
   or retained foreign sessions remain paused. The backend worker added an
   explicit not-delivered regression test.

No remaining concrete protocol blocker was found in the release-gate revision.
This earlier gate check was followed by the final revision/test pass above;
neither is physical proof.

5. A later close-error hardening revision
   (`5f4349c7c54a7256925eb52338d64874fda3d179fd702ac4620219087f3ae00e`)
   introduced `_CleanupReplay._ledger_closed_cleanly`. Its no-stream close
   path could overwrite a first actual close failure: base `_finish` catches
   that failure and calls `_fatal`, whose second no-op `_close_file` sets the
   flag true. This could falsely confirm cleanup. Delivered the exact chain
   and requested sticky failure plus a one-shot-close-error regression. The
   final revision returns through the no-stream path without overwriting the
   prior outcome. Its `test_failed_private_close_cannot_confirm_cleanup`
   regression passed independently.

## Final checked boundaries

- Direct live capture still fsyncs each contiguous row before ACK, using the
  protected Replay validator and the unchanged eight-channel CSV schema.
- A loss freezes original path/session/count/history and file bytes; cleanup
  emits state events only, never user sample events or completion.
- Cleanup owns a separate private durable sink and transfers only the already
  persisted prefix. ACK-send failure after fsync is reconciled by Resume;
  partial/fsync-failed rows are rolled back before retry and never ACKed.
- Stop ID survives lost ACK; summary arriving first does not unlock. An owned
  retained session is released only after correlated Stop ACK, durable exact
  total, terminal summary, stopped acquisition and successful ledger close.
- Repeated cleanup disconnects retain the combined prefix; the window remains
  eight and 603 retained rows drain without touching the frozen original.
- Original-file storage failure stays visible and blocks unverified export.
  Private-sink failures pause ownership and require a successful durable retry.
- Rejected START and never-delivered START do not strand an absent session.
  An accepted START with lost ACK is cleaned only by exact owned identity.
- Active foreign, wrong-device/profile/label and malformed hello cannot obtain
  Stop/Resume or silently release ownership. Same-device new boot is treated
  as loss of the old RAM session, with no foreign Stop; the original CSV stays
  incomplete.
- Explicit disconnect pauses cleanup, clears its password, and stops its worker
  without releasing unresolved ownership. Credentials are absent from public
  state/event errors.
- Legacy protocol1 Direct and the protected Replay collector are unchanged.

Firmware source fingerprint reviewed:

- `firmware/gld/src/GldDatasetReplayWifi.cpp`: `d1deb165fa11c36a55e9857dcca6693361bf6855dac1ef9083016a6f951b63e8`
- `firmware/gld/include/GldDatasetReplayBuffer.h`: `34e578bbb4a54817b74033dafdef2990d727947eeef1fab2641bc05c0585b1e3`
- `firmware/gld/include/GldDatasetReplayWifi.h`: `e4c4d2f476791bf92cbaf43f7ffabff9fcfe1821cf16fb30b3c7fe4a14c7f509`

## Firmware invariants checked

- `firmware/gld/src/GldDatasetReplayWifi.cpp:302`: START idempotency;
  `:308`: rejects new START while sampling, retained rows, or summary pending.
- `:337`: RESUME requires boot/session/immutable label and an available durable
  prefix; it queues ACK and status before enabling sample streaming.
- `:355`: STOP requires current session and reuses the first registered STOP
  command ID. Reconnect must preserve an ambiguous prior STOP ID.
- `:207`: ACK validates boot/session and offered frontier before release.
- `:542`: summary requires stopped acquisition, empty ring and acknowledged
  prefix equal to total; terminal incomplete reasons remain sticky.
- `firmware/gld/include/GldDatasetReplayBuffer.h:58`: RESUME may advance the
  durable contiguous prefix. Therefore it must never use a device-advertised
  total instead of fsynced PC progress.

The composition of a frozen user recorder and a separate private durable
cleanup recorder fits these invariants. The current Resume-then-Stop ordering
is supported; any additional rows before Stop belong exclusively to the
private sink. Stop-before-Resume is also supported by firmware and would
reduce that acquisition interval, but is not required for correctness.

Final acceptance is source/host-only. It cannot establish real GLD transport,
ADS quality, radio reconnect timing, or Windows hardware behavior.
