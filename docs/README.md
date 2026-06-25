# Pertamina GLD Documentation Index

Dokumen di folder ini dibaca dengan urutan berikut.

## 1. Session Context

Gunakan hanya untuk memahami keputusan diskusi, bukan sebagai kontrak implementasi utama.

1. `docs/chat/summary.md`
2. `docs/chat/fullchat.md`

## 2. Final Current-State Design

File `final_design.md` adalah referensi canonical current-state. File `design.md`
tetap disimpan sebagai import original dan tidak diedit langsung.

1. `docs/design/gld/README.md`
2. `docs/design/gld/final_design.md`
3. `docs/design/ch/README.md`
4. `docs/design/ch/final_design.md`

## 3. Integration Contract

Ini sumber kebenaran utama untuk wire protocol GLD-CH-server phase awal.

1. `docs/design/gld-ch/payload-contract.draft.md`

## 4. Backbone / Gateway / Server Design

Gunakan setelah kontrak GLD-CH dibaca.

1. `docs/design/ch-gw/final_design.md`
2. `docs/design/gw/final_design.md`
3. `docs/design/gw-server/final_design.md`
4. `docs/design/server/final_design.md`
5. `docs/design/ch-ch/final_design.md`

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

## 6. Hardware Wiring

Gunakan saat mencocokkan pin firmware dengan schematic/board fisik.

1. `docs/wiring/README.md`
2. `docs/wiring/SCH_GasLeakIntegratedVer3_2026-06-25.json`

## Implementation Priority

Untuk mulai firmware, urutan kerja dokumentasi adalah:

1. Baca `payload-contract.draft.md`.
2. Baca `01-gld-reference-traceability.draft.md`.
3. Baca `02-gld-3-stage-plan.draft.md`.
4. Baca `03-phase-1-plan.draft.md`.
5. Baca `04-phase-1-implementation-checklist.draft.md`.
6. Baca `05-firmware-versioning-backup-policy.draft.md`.
7. Baca desain final boundary yang relevan:
   - `docs/design/ch-gw/final_design.md`
   - `docs/design/gw/final_design.md`
   - `docs/design/gw-server/final_design.md`
   - `docs/design/server/final_design.md`
   - `docs/design/ch-ch/final_design.md` untuk multi-hop.
8. Jika perlu audit sejarah, bandingkan dengan `design.md` dan `design.updated.draft.md`.

## Rules

- Jangan edit `docs/design/gld/design.md` dan `docs/design/ch/design.md`.
- Jika ada konflik antara original `design.md` dan `final_design.md`, pakai
  `final_design.md` untuk current implementation dan pakai original hanya untuk audit baseline.
- Firmware coding hanya dimulai setelah approval eksplisit dari user.
