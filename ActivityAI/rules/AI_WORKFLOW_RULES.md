# AI Workflow Rules - Pertamina GLD

Dokumen ini berisi perjanjian kerja untuk memakai beberapa AI agent, terutama
Codex dan Claude Code, dalam repo `D:\PertaminaGLD`.

## Tujuan

- Codex dan Claude Code boleh bekerja bersamaan.
- Pekerjaan paralel harus tetap aman, bisa dilacak, dan tidak saling menimpa.
- Hardware test tetap terkendali karena board fisik tidak bisa dipakai paralel sembarangan.

## Pola Kerja Paralel

Gunakan workspace dan branch terpisah.

Contoh:

```powershell
cd D:\PertaminaGLD
git worktree add D:\PertaminaGLD-Claude -b claude/step12-training
```

Pembagian default:

```text
Codex       -> D:\PertaminaGLD
Claude Code -> D:\PertaminaGLD-Claude
```

Branch boleh disesuaikan, tapi harus jelas agent mana bekerja di branch mana.

## Ownership File

Sebelum mulai kerja paralel, tentukan ownership file.

Contoh Step 12:

```text
Codex:
- dataset export
- training pipeline
- evaluation script
- docs/progress.md update setelah validasi

Claude Code:
- model metadata / sidecar spec
- firmware integration contract
- test scaffold
```

Aturan:

- Jangan dua agent edit file yang sama di waktu bersamaan.
- Jangan dua agent edit firmware runtime yang sama tanpa koordinasi.
- Jika file harus disentuh dua agent, satu agent menjadi owner utama dan agent lain memberi rekomendasi/diff terpisah.

## Hardware Access

Hardware tidak boleh dipakai paralel.

Board aktif:

```text
GLD     COM10
CH      COM3
Gateway COM38
```

Aturan:

- Upload/test board hanya satu agent pada satu waktu.
- Jangan Codex dan Claude upload ke COM10/COM3/COM38 bersamaan.
- Sebelum upload, agent harus menyebut target environment dan COM port.
- Upload langsung boleh dilakukan tanpa compile-only jika user sudah mengarahkan begitu.

## Save Rule

Saat user bilang `save`, update:

```text
docs/chat/fullchat.md
docs/chat/summary.md
docs/resume.md
```

`docs/resume.md` harus cukup lengkap untuk agent lain melanjutkan tanpa riwayat chat.

Isi minimal resume:

- firmware versions terbaru,
- progress step terbaru,
- file yang baru berubah,
- test/deploy/upload terakhir,
- blocker yang tersisa,
- environment bench,
- exact next commands.

## Low Usage Rule

Jika usage/context terlihat sudah di bawah 10%, save checkpoint dulu sebelum lanjut kerja panjang.

Jika agent tidak bisa mendeteksi usage otomatis, lakukan save saat:

- user melaporkan usage di bawah 10%,
- indikator usage terlihat,
- agent merasa context hampir penuh dan pekerjaan berikutnya berisiko panjang.

Save tetap harus mencakup:

```text
docs/chat/fullchat.md
docs/chat/summary.md
docs/resume.md
```

## Merge Rule

Hasil kerja paralel digabung lewat diff/review, bukan copy manual sembarang.

Rekomendasi alur:

1. Setiap agent menyelesaikan scope-nya di branch/worktree masing-masing.
2. Jalankan test yang relevan.
3. Bandingkan diff.
4. Review konflik file.
5. Merge hanya setelah user setuju atau setelah scope merge sudah jelas.

Jangan `git push` kecuali user meminta eksplisit.

## Baseline Commit

Sebelum kerja paralel besar, buat baseline commit lokal jika repo sudah siap.

Tujuannya:

- memudahkan rollback,
- memudahkan diff antar agent,
- mengurangi risiko file saling timpa.

Push tetap tidak dilakukan kecuali user meminta.

## Design File Rule

Jangan edit original imported design files:

```text
docs/design/gld/design.md
docs/design/ch/design.md
```

Jika perlu revisi desain, buat draft/copy:

```text
docs/design/gld/design.<topic>.draft.md
docs/design/ch/design.<topic>.draft.md
```

## Step 12 Suggested Parallel Split

Untuk Step 12 AI Model Training, pembagian awal yang direkomendasikan:

```text
Track A - Dataset / Training
- audit dataset source
- export dataset dari MySQL/CSV
- training script MVP
- train/test split
- confusion matrix
- model export

Track B - Model Contract / Firmware
- sidecar metadata schema
- modelProfileId / boundNullingProfileId rule
- feature_order and scaler metadata
- firmware loading/integration plan
- test scaffold
```

Setelah kedua track siap:

1. Review hasil Track A dan Track B.
2. Cocokkan model artifact dengan sidecar metadata.
3. Baru lanjut firmware integration.

## Bahasa

Gunakan Bahasa Indonesia jika user menulis dalam Bahasa Indonesia.

## Quick Start Besok

Kalau user berkata:

```text
mulai setup kerja paralel Codex-Claude
```

Langkah awal:

1. Baca `docs/resume.md`, `AGENTS.md`, `CLAUDE.md`, dan `ActivityAI/rules/AI_WORKFLOW_RULES.md`.
2. Pastikan repo dalam kondisi aman.
3. Buat baseline commit lokal jika user setuju.
4. Buat worktree/branch untuk Claude Code.
5. Tentukan ownership file.
6. Mulai Step 12 sesuai split paralel.
