# Pertamina GLD Documentation Index

Dokumen di folder ini dibaca dengan urutan berikut.

## 1. Session Context

Gunakan hanya untuk memahami keputusan diskusi, bukan sebagai kontrak implementasi utama.

1. `docs/chat/summary.md`
2. `docs/chat/fullchat.md`

## 2. Source Design Baselines

File `design.md` adalah import original dan tidak diedit langsung. Untuk implementasi, gunakan file updated draft.

1. `docs/design/gld/README.md`
2. `docs/design/gld/design.md`
3. `docs/design/gld/design.updated.draft.md`
4. `docs/design/ch/README.md`
5. `docs/design/ch/design.md`
6. `docs/design/ch/design.updated.draft.md`

## 3. Integration Contract

Ini sumber kebenaran utama untuk wire protocol GLD-CH-server phase awal.

1. `docs/design/gld-ch/payload-contract.draft.md`

## 4. Backbone / Gateway / Server Design

Gunakan setelah kontrak GLD-CH dibaca.

1. `docs/design/ch-gw/design.md`
2. `docs/design/gw/design.md`
3. `docs/design/gw-server/design.md`
4. `docs/design/server/design.md`
5. `docs/design/ch-ch/design.md`

Catatan:

- `ch-gw`, `gw`, `gw-server`, dan `server` sudah mengikuti bukti bench normal path terakhir.
- `ch-ch` adalah desain multi-hop draft dan belum live-tested.

## 5. Firmware Planning

Gunakan setelah kontrak integrasi dibaca.

1. `docs/firmware/01-gld-reference-traceability.draft.md`
2. `docs/firmware/02-gld-3-stage-plan.draft.md`
3. `docs/firmware/03-phase-1-plan.draft.md`
4. `docs/firmware/04-phase-1-implementation-checklist.draft.md`
5. `docs/firmware/05-firmware-versioning-backup-policy.draft.md`

## Implementation Priority

Untuk mulai firmware, urutan kerja dokumentasi adalah:

1. Baca `payload-contract.draft.md`.
2. Baca `01-gld-reference-traceability.draft.md`.
3. Baca `02-gld-3-stage-plan.draft.md`.
4. Baca `03-phase-1-plan.draft.md`.
5. Baca `04-phase-1-implementation-checklist.draft.md`.
6. Baca `05-firmware-versioning-backup-policy.draft.md`.
7. Baca desain boundary yang relevan:
   - `docs/design/ch-gw/design.md`
   - `docs/design/gw/design.md`
   - `docs/design/gw-server/design.md`
   - `docs/design/server/design.md`
   - `docs/design/ch-ch/design.md` untuk multi-hop draft.
8. Pakai `design.updated.draft.md` GLD/CH sebagai reference detail saat coding.

## Rules

- Jangan edit `docs/design/gld/design.md` dan `docs/design/ch/design.md`.
- Jika ada konflik antara original `design.md` dan updated draft/contract, kontrak GLD-CH dan updated draft menang.
- Firmware coding hanya dimulai setelah approval eksplisit dari user.
