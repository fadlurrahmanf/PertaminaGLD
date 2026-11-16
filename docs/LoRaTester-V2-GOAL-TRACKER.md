# LoRaTester V2 — Tracker

Last tracker heartbeat: 2026-11-16 21:46:48 WIB
Last evidence update: 2026-11-16 21:46:48 WIB

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
| V2-10 | Deferred | Ambang 10/5 dan ring interval sampel: build serta 110 host lulus | User meminta simpan untuk upload berikutnya; tes fisik tertunda |
| V2-11 | Open | User klarifikasi animasi terus selama PENGUJIAN, bukan sekadar awal | Pasang inline dua mode, upload dan cek visual |
| V2-12 | Open | Page0 saat Done duplikat page1 CH2→CH1 | Perbaiki navigasi dan uji |

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
| Coordinator | Backup COM5 dan verifikasi | 2026-11-16 21:39:56 WIB | 0:06:52 | Aktif |
| Display worker | Perbaiki animasi START | 2026-11-16 21:39:56 WIB | 0:06:52 | Aktif |

User meminta perbaikan sampai berjalan; COM5 upload diotorisasi. V2 thresholds 10/5 dan perbaikan ring ikut upload berikutnya. V2-09 minimal 60 fps semua frame tetap belum tercapai.
