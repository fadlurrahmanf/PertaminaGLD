# LoRaTester V2 — Tracker

Last tracker heartbeat: 2026-11-16 22:33:26 WIB
Last evidence update: 2026-11-16 22:33:26 WIB

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall** | **93%** | Waiting for hardware calibration | Uji bench utama lulus; ADC dan uji jarak belum. |
| 1. Baseline V1 dan V2 terpisah | 100% | Done | 28 file diverifikasi; 3 path build dan 1 path tes disesuaikan. |
| 2. CH1/CH2 V2 | 90% | Waiting for hardware | Transisi diperbaiki; build dan host lulus. |
| 3. Display V2 | 90% | Waiting for hardware | Build dan 91 host lulus; visual fisik belum. |
| 4. Integrasi dan verifikasi | 95% | Waiting for hardware | Belum ada uji komunikasi gabungan/fisik. |

## Progress calculation

Bobot 20% + 30% + 30% + 20%; progress tiap fase adalah rata-rata work item.

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Baseline | 20% | 100% | Done | 28 file dibandingkan; 3 path build dan 1 path tes disesuaikan |
| 2. CH | 30% | 90% | Waiting for hardware | Build dan fault host lulus |
| 3. Display | 30% | 90% | Waiting for hardware | Build dan 91 host lulus |
| 4. Integrasi | 20% | 95% | Waiting for hardware | Review selesai; end-to-end fisik ditunda |

## Issue register

| ID | Status | Evidence | Next gate |
|---|---|---|---|
| V2-01 | Open | Jalur ADC dan divider display belum terpasang | Tegangan/kalibrasi tidak boleh dinyatakan terukur |
| V2-02 | Open | CH2 belum tentu dalam jangkauan 2.4 GHz | Ready via jalur yang benar dan Unknown saat status usang |
| V2-03 | Solved | PDR 100/100 dua arah; realtime, STOP, reset display, kedua READY lulus | Uji lapangan terpisah |
| V2-04 | Solved | Tombol batas 799/800/801ms, ikon direvisi | 91 host lulus dan build display lulus |
| V2-05 | Deferred | Mitigasi transisi START/STOP dan poll lolos host | Ukur timing dan RF pada perangkat |
| V2-06 | Solved | Umur efektif memakai timestamp STATUS | Host batas stale, sentinel dan wrap lulus |
| V2-07 | Solved | Indikator PDR saat koneksi pulih | 91 tes host dan build display lulus |
| V2-08 | Deferred | Guard reset, timeout dan retry ACK lulus host/build dan review | Uji timing dan RF pada perangkat |
| V2-09 | Open | 40MHz realtime 63–65 blit/s saat animasi; refresh penuh 26,3ms, 80MHz 17,1ms | Minimum 60 pada semua frame belum tercapai; perlu solusi dan uji lanjut |
| V2-10 | Open | User minta upload ambang 15/5; host batas kedua arah lulus | Backup, upload dan uji fisik |
| V2-11 | Deferred | Animasi inline terunggah; user melihat versi awal, versi event-driven lulus host dan radio nyata | Visual ritme terakhir belum bisa dilihat dari serial |
| V2-12 | Solved | User mengonfirmasi urutan; versi akhir serial 4→2→1→3→4 | — |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Salin checkpoint ke V1 | 100% | Done | 28 file terverifikasi | 3 path build dan 1 path tes disesuaikan |
| 1.2 | Buat basis V2 terpisah | 100% | Done | Salinan siap dikembangkan | Tidak sentuh firmware asli |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Baterai dan status CH | 100% | Prepared | Kalibrasi dan uji fisik | Build dan host lulus; ADC default unknown |
| 2.2 | Direct/relay dan perlindungan sesi tes | 80% | Waiting for hardware | Uji RF fisik | Transisi dan kehilangan ACK lulus host |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Baterai dan status display | 100% | Prepared | Kalibrasi dan uji fisik | ADC nonaktif; host lulus |
| 3.2 | Menu dan animasi yang disetujui | 80% | Waiting for hardware | QA visual dan waktu fisik | Debounce, umur data dan ikon diperbaiki |

### Phase 4 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 4.1 | Integrasi serta tes V1/V2 | 90% | Waiting for hardware | Uji perangkat | Build dan tes host terpisah lulus |
| 4.2 | Dokumen wiring dan batas verifikasi | 100% | Prepared | Verifikasi wiring fisik | README tersedia |

## Current work / agent state

| Worker | Active work | Started at | Elapsed | State |
|---|---|---|---|---|
| Coordinator | Backup, upload dan uji COM5 | 2026-11-16 22:33:26 WIB | 00:00:00 | Aktif |

User mengizinkan upload display. COM5 terdeteksi dan realtime sebelumnya dihentikan terkonfirmasi STOP. Tidak mengakses COM4/6/7, NVS tidak akan dihapus. Pengujian host boundary lulus; pengujian RF nyata belum berarti sampel tepat batas.
