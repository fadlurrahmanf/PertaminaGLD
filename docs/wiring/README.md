# Indeks Wiring dan PCB

Folder ini menyimpan artefak EasyEDA asli untuk GLD dan Cluster Head (CH).
Arsip sumber disusun ulang tanpa mengubah isinya; referensi teks yang terdampak
telah diperbarui. Pengelompokan versi di bawah menjadi indeks kerja yang jelas.

> **Batas identitas versi:** nama proyek di dalam EasyEDA bukan bukti tunggal
> versi produk. Contohnya, beberapa arsip GLD memakai nama internal `Ver1`,
> `Ver2`, atau `Ver3` yang tidak selalu sama dengan label produk GLD V1–V5.
> Baris yang belum memiliki manifest versi ditandai **perlu konfirmasi**.

## GLD

| Versi produk | Artefak sumber | Identitas pada source | Status pemetaan |
|---|---|---|---|
| **V1** | `GLD/V1/source-GLD_Project.zip` dan file ekstrak di folder yang sama | `GasLeakIntegratedVer2` | **Perlu konfirmasi.** Nama internal menyebut `Ver2`, sehingga source saja belum membuktikan ini V1 produk. |
| **V2** | `GLD/V2/source-GLD2.zip` | `MotherBoardGLDVer1`; ada gambar referensi modul sensor `TPS22919` | **Perlu konfirmasi.** Nama internal menyebut `Ver1`, bukan V2 produk. |
| **V3** | `GLD/V3/Board_GLD3.zip` | `MotherBoardGLDVer2` | **Perlu konfirmasi.** Nama file luar menunjukkan GLD3, tetapi identitas EasyEDA di dalamnya `Ver2`. |
| **V4** | `GLD/V4/GLD ATEX.zip` | `MotherBoardGLDVer2` | **Perlu konfirmasi.** Ini arsip board V4 yang tersedia; nama arsip lama dipertahankan apa adanya. |
| **V5** | `GLD/V5/GLD5.zip` dan `GLD/V5/board Sensor PCB.zip` | `MotherBoardAdapter` dan `SensorBoardAdapter` | **Teridentifikasi sebagai pasangan board.** Tetap perlu manifest produk untuk mengunci label V5. |

### Artefak GLD tambahan

| Artefak | Kegunaan | Catatan |
|---|---|---|
| `GLD/V3/SCH_GasLeakIntegratedVer3_2026-06-25.json` | Skematik EasyEDA lepas | Tidak disertai PCB/BOM pasangan dalam folder ini. |
| `GLD/V3/GLD3-v0.8.31-source-changes.zip` | Perubahan source firmware | Bukan source skematik/PCB. |
| `GLD/V3/GLD3-diagnostics-2026-09-17.md` | Catatan diagnostik | Bukan bukti desain PCB. |
| `GLD/_unassigned/SensorBoardMQ.zip` | Source board sensor MQ terpisah | Belum ada bukti cukup untuk memetakan board ini ke V1–V5. |

## Cluster Head (CH)

| Versi produk | Artefak sumber | Identitas pada source | Status pemetaan |
|---|---|---|---|
| **V1** | `CH/V1/Source_CH_Board_Kecil.zip` | Arsip internal `dualRadioCH_E220Ver5` | **Perlu konfirmasi.** Nama internal menyebut `Ver5`, bukan V1 produk. |
| **V2** | `CH/V2/ch-dual-radio-e220-ver4-2026-07-21/` | `dualRadioCH_E220Ver4` | **Teridentifikasi sebagai board bundar dual-radio.** Pemetaan ke label V2 produk tetap memerlukan manifest versi. |
| **V3** | `CH/V3/CHKecildenganWDT.zip` | Arsip internal `dualRadioCH_E220Ver5` | **Perlu konfirmasi.** Nama internal sama dengan kandidat V1, tetapi hash arsip dalam berbeda. |

## Data yang masih kurang

1. Manifest atau tabel rilis yang menghubungkan setiap label produk GLD V1–V5
   dan CH V1–V3 ke nama proyek/UUID EasyEDA yang tepat.
2. BOM per versi untuk mengonfirmasi perubahan IC tanpa mengandalkan nama atau
   tampilan PCB.
3. Catatan perubahan resmi per versi yang menjelaskan fungsi dan alasan setiap
   revisi board.
4. Untuk CH V1 dan V3, diff atau changelog antara dua arsip beridentitas
   internal sama (`dualRadioCH_E220Ver5`) tetapi memiliki hash berbeda.
5. Untuk GLD V5, dokumentasi kabel dan pemetaan pin antarpapan
   `MotherBoardAdapter` dan `SensorBoardAdapter`.

## Catatan penggunaan

- Buka file `*.json` di EasyEDA melalui **File > Open > EasyEDA**.
- Perlakukan ZIP dan JSON sebagai source evidence. Keberadaan file tidak
  membuktikan board telah diproduksi, diuji, atau dipasang di lapangan.
- Jika manifest versi tersedia, perbarui tabel ini dahulu sebelum mengubah
  label versi pada dokumen, firmware, atau presentasi.

## Referensi firmware yang sudah ada

- `firmware/platformio.ini`
- `firmware/gld/include/BoardPins.h`
- `firmware/gld/include/BoardPinsGLD2.h`
- `firmware/gld/include/BoardPinsGLD3.h`

## Pemetaan analog GLD yang telah diverifikasi

Artefak `GasLeakIntegratedVer2` dan skematik GLD Ver3 lepas menunjukkan
pemetaan blok sensor lokal berikut. Firmware memakai pemetaan ini di
`firmware/gld/include/BoardPins.h`.

| Input ADS1256 | Cabang TCA/MCP lokal |
|---:|---:|
| AIN0 | 7 |
| AIN1 | 6 |
| AIN2 | 5 |
| AIN3 | 0 |
| AIN4 | 1 |
| AIN5 | 2 |
| AIN6 | 3 |
| AIN7 | 4 |

Konstanta firmware: `SENSOR_TO_MUX_CH = {7, 6, 5, 0, 1, 2, 3, 4}` dan
`SENSOR_TO_ADS_CH = {0, 1, 2, 3, 4, 5, 6, 7}`.

## Wiring bench GLD saat ini

Board bench ESP32-S3-WROOM-1U-N16R8 memakai environment firmware `gldw`.

| Sinyal LoRa STAR | GPIO ESP32-S3 |
|---|---:|
| SCK | GPIO12 |
| MOSI | GPIO11 |
| MISO | GPIO13 |
| CS | GPIO7 |
| RST | GPIO2 |
| BUSY | GPIO15 |
| DIO1 | GPIO1 |
| RXEN | GPIO5 |
| TXEN | GPIO6 |

Karena wiring ini memakai GPIO1 dan GPIO2 untuk LoRa, environment WROOM
menonaktifkan output firmware lampu alarm dan buzzer lama yang sebelumnya
memakai kedua GPIO tersebut.
