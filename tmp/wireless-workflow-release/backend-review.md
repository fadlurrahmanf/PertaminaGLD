# Independent workflow backend review

Reviewer: GLD_Agent, 2026-11-02 WIB. Scope: read-only production source review,
this report and `apps/gld-operator/tests/test_workflow_adversarial.py` only.
No compiler, COM, device, native WLAN/file dialog, network, or service action.
Firmware and the three validated package families remain frozen.

Status: **PASS at source/host level** for the exact frozen revisions below.
No remaining concrete protocol, ownership, transaction or frozen-public-file
blocker was found after the backend owner fixed the reported cases.

- `dataset_workflow.py`: `f10997f3f18ebbefbbac744b0cd55c06f18883f41440555564aa1d8eff5a39a8`
- `wireless_dataset_workflow.py`: `fe606f103a6b23e9bdb5b4140cfa7e5464d24c1540f84f11cffdb52e14f131d4`
- Owned adversarial tests: `421fdad05c19d7f388b864ab3153fe8719ee2aac7498ee24401b28cf3ee23b98`
- Platform source reviewed: `914d5b5649968cb181d10521815f9cd14fc8e40788261fdc0c54c8eaa44b2107`

Final independent result: **17/17 PASS**, 0.074 seconds. Backend worker also
reports its separate 22 service tests passing; the 17-test result is the
reviewer's independently executed evidence.

## Concrete findings delivered to backend owner and root

1. Running heartbeat refreshed the sample-progress clock, defeating sample
   silence detection while acquisition stalled. Fixed: running status alone
   does not count as a new sample; paused/control liveness is handled separately.
2. Accepted Pause with lost ACK followed by pending-ACK retention expiry is a
   legitimate terminal `paused=false, sampling=false, incomplete=true` state
   with the accepted transition sequence. The first draft rejected this hello
   and stranded recoverable owned rows. Fixed: terminal state supersedes the
   Pause expectation without resuming acquisition or creating a new session.
3. A zero-public-row Direct cutoff could expose `state=complete` after private
   cleanup, despite logical `complete=false`. The final-state override depended
   on truthy row count. Fixed and covered by a real header-only CSV regression.
4. Initial private-ledger creation failure assigned its path before exclusive
   open succeeded. Retry used `r+` on a nonexistent path, stranding cleanup after
   storage repair. Fixed and covered by one-shot open failure. Missing ledgers
   with nonzero durable prefix still fail closed and are never recreated.
5. Pending Stop may be orphaned by a late rejected Pause/Continue: the error
   clears transition control, while future paused heartbeats never dispatch the
   stable queued Stop or trigger sample-silence recovery. Fixed: correlated
   transition rejection dispatches the already-requested Stop with the original
   stable ID. The independent late-rejection regression now passes.

The final service also keeps private-close failure sticky across a later no-op
Disconnect; only a successful reopen/fsync can clear that storage uncertainty.
It does not certify cleanup merely because a second close had no stream.

## Independent adversarial coverage

The owned test suite uses an inert socket, a durable-ledger fake, and actual
temporary public/canonical files. It does not implement a competing firmware
state machine or invoke the native platform.

- All eight sensor values and quality metadata are persisted before ACK.
- Persistence failure cannot advance ACK/prefix; changed duplicate prediction
  content cannot be acknowledged as the same row.
- Invalid predicted-class/gas-class mapping fails closed.
- Wrong Start/Pause ACK transition frontiers cannot confirm a control.
- Running status cannot mask lost samples; paused empty status is valid liveness.
- Terminal retention can supersede ambiguous accepted Pause.
- Partial public write and public fsync failure roll back both canonical and
  public tails; retry writes exactly one committed row.
- Verification reads actual complete files even with empty UI history.
- External CSV mutation blocks append without changing either existing file.
- Empty Direct public file remains incomplete after private cleanup.
- Initial private-ledger open failure can recover, while missing durable-prefix
  ledger is not recreated.
- A queued stable Stop must survive late transition rejection.

Latest run: 17 tests, all PASS, including the previously failing Stop-dispatch
regression and initial private-ledger creation repair.
Command:

```powershell
& apps/gld-operator/python-embed/python.exe -m unittest discover -s apps/gld-operator/tests -p test_workflow_adversarial.py -v
```

## Native platform and admission review

Source review found no concrete ABI or injection blocker in
`workflow_platform.py`: GUID, WLAN interface/header offset, connection parameters
and OPENFILENAME use full-width pointers and the expected Windows layout. SSID
is restricted to `GLD-DATASET-<4 hex digits>`. Password is escaped into an
in-memory XML text node and supplied through native WLAN API, without command
line or plaintext temporary XML. Native file selection uses a native buffer;
the HTTP API cannot provide an arbitrary path. Existing destination files are
rejected and actual first creation is exclusive.

Bridge admission uses one shared guard for legacy/workflow Connect, Start,
Continue and acquisition Resume versus COM probe/connect/upload. Paused,
recovering and cleanup ownership stays reserved. Serial/write does not open a
closed COM port, so that route is not a new auto-open bypass.

Native residual limits: first WLAN adapter selection, association/routing,
Windows permission/localization, and dialog behavior have not been executed.
The authenticated protocol hello still must match the selected device ID.

## Evidence limits

These are source/host results. Full wizard integration, actual GLD control,
real sensor quality, WLAN behavior, timing and reboot behavior require separate
authorized device testing. The C++ protocol3 builds prove compilation and image
identity, not physical 500 ms performance or runtime heap headroom.
