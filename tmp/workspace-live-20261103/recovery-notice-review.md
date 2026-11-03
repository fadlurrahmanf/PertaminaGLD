# Replay recovery notice review — revision 4

Updated: 2026-11-03T12:48:28.941737+07:00

## Change

The service no longer maps an ordinary active Replay transport outage to the generic unconfirmed-action error. Suppression is limited to transport_lost, reconnect_failed, and sample_silence_resume_required while recovery is active, START was previously confirmed, and neither a transition nor Stop is pending.

Unknown START/PAUSE/CONTINUE/STOP and command results keep the generic notice. A service-owned transient notice clears only after the engine confirms a connected stream, clears its error/recovery state, and has no pending control/transition/Stop. Genuine engine notices and unrelated service errors are not automatically cleared. Terminal CSV verification, direct cutoff, disk and cleanup branches are unchanged.

## Verification

- 35 Dataset workflow tests passed, including six new recovery/notice regressions.
- 82 aggregate workflow Python tests passed in 9.236 seconds.
- Diff whitespace check passed.
- No firmware, build, hardware, network, service, tracker, or user-data action by this worker.

## Ownership

- `apps/gld-operator/dataset_workflow.py` SHA-256 `b87037be27630f1901ccb2037ead6d9a433bc26a68fb5cacee3fef27e36bfef4`
- `apps/gld-operator/tests/test_dataset_workflow.py` SHA-256 `1ca60fb4cd87c1937d820be24cae55532f0a7199ba2c2d31a745aff438ac8d2a`

Parent owns reload and actual outage/status screenshot validation. This report proves only source/inert fixture behavior; it does not claim a new physical test.
