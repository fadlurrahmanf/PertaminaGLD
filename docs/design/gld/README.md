# GLD Design

This folder stores the Gas Leak Detector design baseline for the Pertamina GLD monorepo.

- `design.md` is imported from `D:\GasleakDetectorDesign\design.md`.
- Treat `design.md` as the immutable imported baseline. **Never edit `design.md` directly.**
- `design_update.md` is the living, adjusted copy of the baseline - see the rule below.
- `design.updated.draft.md` and `design.current-firmware.draft.md` are historical draft material and are not the current implementation contract.
- Use `docs/design/gld-ch/payload-contract.draft.md` for the current GLD-CH payload and crypto contract.

## Rule: proposing an adjustment to `design.md`

`design.md` stays untouched, exactly as imported. If implementation reveals that anything in it needs adjusting (firmware behaves differently, a value changed, a section is stale, etc.):

1. Copy `design.md` as-is to `design_update.md` in this same folder (only do this once - if `design_update.md` already exists, reuse it instead of re-copying over it).
2. Apply the adjustment to `design_update.md`, not to `design.md`. Prefer editing in place next to the relevant section (e.g. an inline `>` blockquote note) over appending a separate changelog, so the doc reads as a single coherent reference.
3. `design.md` itself is never touched.

`design_update.md` is the one and only place that tracks how the design has evolved since import - there is no separate "current firmware mirror" document.
