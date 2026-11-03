# Shared three-model binding UI — revision 6

Owner: Integration_Agent. Date: 2026-11-03. Source and inert test work only. No firmware/model, build, package, COM/NVS, credentials, service or Hub launch/restart was performed. Future Hub launches must remain visible and accessible as instructed by the user; this worker launched none.

## Change and frozen result

One common `modelBindingState(status)` evaluator now drives Running and Expert for all three models. A green/matched result requires explicit true production approval, valid binding and matching model, together with equal finite positive integer bound/active nulling profile IDs. It rejects explicit false approval or profile readiness from either model/readiness metadata; contradictory explicit false flags win. Missing, nonnumeric, fractional, zero, negative or otherwise invalid profile IDs remain unknown rather than becoming green through Number coercion. Missing legacy approval/binding metadata stays unknown.

Distinct reasons identify unapproved model, invalid binding, mismatched model, different profile IDs, profile not ready and incomplete metadata. Running displays the detailed reason and marks explicit failures with the existing error style. Expert uses the same value and reason, shows a short reason in the binding-row label and full detail in its tooltip/first-blocker hint. These are snapshot display rules; firmware remains authoritative for inference and all writes.

The Bind button now shows the unapproved-model reason before any NVS confirmation/command when production approval is explicitly false. Unknown legacy approval preserves its prior explicit confirmation and firmware-authoritative Bind command. No serial, alarm, chart, Pause/replay or other control behavior was changed. The main cache reference was bumped; stateful serial module URLs were kept consistent to avoid accidentally creating duplicate module instances. Static bridge responses already use no-store.

## Verification

All passed:

- New `test_model_binding_status.cjs`: actual shared evaluator, Running renderer, Expert renderer and actual Bind event callback; Models 1/2/3 matched, bound #1 versus active #2, wrong model, explicit unapproved, explicit profile/readiness failures, contradictory readiness, missing/invalid IDs and legacy unknown. The unapproved click sends no confirmation or Bind; unknown legacy still confirms and sends the existing command.
- Existing workflow chart test: shared Running baseline retained; eight traces, timing and Pause/session gaps protected.
- Existing workflow UI test: prerequisite gates, locks and Start/Pause/Stop/Continue behavior retained.
- Existing native alarm source contract: PASS.
- Existing nulling stability UI test: PASS.
- Existing workflow route/ownership tests: 4 PASS.
- Scoped `git diff --check`: PASS.

No physical inference, fresh browser rendering or release upload is claimed. Root owns Model 2 approval, three-model compilation and synchronized release packaging.

## Frozen SHA-256

| File | SHA-256 |
| --- | --- |
| `apps/gld-operator/js/model-binding.js` | `b773f90d4bf2f9a2d2ba12446789a9cc5398c5b0bd069e5738e7c6de4fdca90e` |
| `apps/gld-operator/js/serial-protocol.js` | `acfa69a6960ca71b53a738787e6b9c000bc120cf344647ecb4e8e5e4f66cd6ca` |
| `apps/gld-operator/js/expert.js` | `d92c5a6b297a7f2612e649a7dae7bdae354d4c2d6ef75ee1d524a3457155875f` |
| `apps/gld-operator/js/main.js` | `9a59b143601063209c2e866e1697081c746a222f5f2f2668ab1788185e5d690e` |
| `apps/gld-operator/index.html` | `41d0e339cb5cfab964e1200ceda6d60d82693f7ae2d61499d16c26996906c5d1` |
| `apps/gld-operator/tests/test_model_binding_status.cjs` | `e164642759398c27d66f64daeb2621bde1de6dfad8c02e0e8a6aa6e59cf8242a` |
