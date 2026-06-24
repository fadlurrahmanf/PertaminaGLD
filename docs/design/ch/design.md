# DESAIN CLUSTER HEAD DUAL-LORA

**Document version:** v1 wiring-aligned  
**Basis utama arsitektur:** `meshLoRav2/doc/DESIGN.md`  
**Referensi hardware pin:** `wiring.png`  
**Sumber daya:** Panel surya + baterai  
**Radio:** E22-900MM22S / SX1262 SPI x 2  
**Firmware role:** Cluster Head dual-LoRa  
**Storage config:** ESP32 Preferences / NVS (to be discussed)  
**Payload:** compact binary  
**CRC:** CRC16-CCITT-FALSE  
**Endian:** big-endian untuk semua integer multibyte  

---

## 1. Ringkasan Sistem

Cluster Head (CH) adalah perangkat penghubung antara banyak node GLD/sensor dan Gateway. Fokus utama desain adalah stabil pada power panel surya/baterai, hemat payload, hemat airtime, minim retransmisi, dan tetap mudah diimplementasikan sebagai firmware. CH memakai dua radio LoRa:

| Radio        | Topologi  | Peran                 | Frekuensi  | Fungsi                                            |
|---|---|---|---|---|
| Radio A / U1 | STAR      | GLD/sensor node ke CH | 920-923 MHz | Menerima data node, mengirim ACK alarm, dan mengirim `NODE_DOWNLINK` sesuai status power GLD. |
| Radio B / U3 | MESH/TREE | CH ke parent/Gateway  | 920-923 MHz | Mengirim data ke Gateway dan menerima request/config/command dari server untuk CH target. |

Catatan: Radio A dan Radio B harus memakai frekuensi berbeda dalam range 920-923 MHz agar link STAR dan MESH tidak saling mengganggu.

Prinsip kerja:

- Node GLD mengirim `SENSOR_DATA` ke CH melalui STAR.
- Data GLD normal disimpan di latest cache per node dan tidak langsung dikirim ke gateway/server saat diterima.
- Jika `SENSOR_DATA` membawa `FLAG_ALARM_ACK`, CH mengirim ACK compact ke GLD, update latest cache, lalu langsung meneruskan alarm ke parent/gateway melalui priority `alarmQueue` tanpa menunggu server pull.
- Server/gateway mengambil data GLD normal dari CH target menggunakan `SERVER_PULL_REQUEST` level-CH, bukan request per GLD.
- CH target menjawab server dari latest cache menggunakan `CLUSTER_DATA_RESPONSE` yang dapat membawa beberapa record GLD normal selama total payload MESH masih muat.
- Request data tidak diteruskan ke GLD.
- Server/gateway mengirim command GLD ke CH target; CH menyimpannya sebagai pending downlink. Jika GLD Battery Mode, CH mengirim saat RX window setelah `SENSOR_DATA`; jika GLD External Power Mode, CH boleh mengirim langsung.
- Semua payload dibuat compact binary agar airtime LoRa tetap rendah.
- ACK hanya dipakai untuk frame dengan `FLAG_ALARM_ACK`; pesan lain tidak meminta ACK.
- CH menjalankan `CH_CONFIG`, `CH_HELLO`, failover parent, queue, power guard, dan watchdog.




## 2. Mekanisme Topologi


Topologi dasar:

```text
GLD-1  \
GLD-2   \
GLD-3    >  Radio A / STAR  >  Cluster Head   >  Radio B / MESH  >  Gateway   >  Server
GLD-N   /
```

Topologi TREE/MESH lanjut:

```text
GLD nodes -> CH child -> CH parent -> Gateway root -> Server/MQTT/Dashboard
```

Aturan parent:

| Field                | Definisi                                           |
|---|---|
| `cluster_id`         | ID CH saat ini.                                    |
| `parent_id`          | Parent aktif untuk uplink MESH.                    |
| `parent_id_alt`      | Parent alternatif untuk failover.                  |
| `gateway_id`         | Root tujuan akhir.                                 |
| `childrenClusterIds` | Daftar CH anak yang memakai CH ini sebagai parent. |

## 3. Kamus Istilah

Tabel ini menjadi rujukan istilah agar arah mekanisme firmware lebih jelas.

| Istilah | Definisi |
|---|---|
| Cluster Head / CH | Board penghubung antara banyak GLD dan Gateway. CH menyimpan data GLD, mengatur queue, dan meneruskan alarm/response ke MESH. |
| GLD | Gas Leak Detector node, yaitu node sensor gas yang mengirim data ke CH melalui LoRa STAR. |
| Gateway | Perangkat root yang menerima data dari CH melalui LoRa MESH dan menghubungkan sistem ke server/dashboard. |
| Server | Aplikasi atau dashboard yang meminta data ke CH, menyimpan hasil monitoring, dan dapat menitipkan command GLD ke CH target. |
| STAR | Topologi komunikasi banyak node GLD menuju satu CH. |
| MESH / TREE | Topologi backbone antar CH menuju Gateway. TREE berarti jalur parent-child menuju root. |
| Parent | Node MESH tujuan CH saat mengirim data ke Gateway. Parent bisa Gateway langsung atau CH lain. |
| Parent alternatif | Kandidat parent cadangan yang dipakai saat parent utama gagal. |
| Failover | Mekanisme pindah parent ketika parent aktif gagal menerima alarm atau ACK alarm. |
| AppFrame | Format frame utama berisi header, payload, dan CRC. |
| Payload | Isi data utama di dalam AppFrame. Payload dibuat compact binary agar hemat LoRa airtime. |
| CRC16 | Kode pengecekan error 16-bit untuk memastikan frame tidak rusak. |
| ACK | Acknowledgement, yaitu balasan bahwa frame diterima. |

| Istilah | Definisi |
|---|---|
| RSSI | Received Signal Strength Indicator, ukuran kekuatan sinyal diterima dalam dBm. |
| SNR | Signal to Noise Ratio, perbandingan sinyal terhadap noise. Nilai makin tinggi biasanya makin baik. |
| Cache | Penyimpanan data terakhir per GLD di RAM CH. Dipakai untuk menjawab request data terbaru. |
| Queue | Antrean data yang menunggu dikirim melalui MESH. Queue diprioritaskan agar alarm dan response penting tidak kalah oleh data normal. |
| Server pull | Mekanisme server meminta data ke CH. CH menjawab dari latest cache lokal, bukan meneruskan request ke GLD. |
| `NODE_DOWNLINK` | Frame STAR dari CH ke GLD yang membawa command tertunda dari server. Timing kirim mengikuti status power GLD: Battery Mode menunggu RX window, External Power Mode boleh langsung. |
| Wake event | Sinyal bahwa GLD baru bangun. Pada cache terbaru, waktunya memakai `lastSeenMs`. |
| NVS / Preferences | Kandidat penyimpanan non-volatile ESP32 untuk config, parent, dan kalibrasi. Keputusan final storage config masih TO BE DISCUSSED. |
| Watchdog | Pengawas runtime yang me-restart board jika firmware hang. |
| Non-blocking | Pola program tanpa delay panjang agar radio tetap responsif. |

---

## 4. Hardware Mapping Circuit

Bagian ini disesuaikan dari `wiring.png`. 

### 4.1 Ringkasan Pin ESP32-S3

| Fungsi              | Net pada Wiring | GPIO ESP32-S3 | Catatan                                     |
|---|---|---|---|
| Battery monitor     | `BATMON`        | IO4           | ADC pembaca VBAT melalui pembagi tegangan.  |
| Radio A TX enable   | `TXEN1`         | IO5           | Kontrol TXEN U1 jika RF switch dipakai.     |
| Radio A RX enable   | `RXEN1`         | IO6           | Kontrol RXEN U1 jika RF switch dipakai.     |
| Radio A reset       | `LRST1`         | IO7           | Reset U1.                                   |
| Radio A busy        | `BUSY1`         | IO15          | Busy SX1262 U1.                             |
| Radio A DIO1        | `DIO11`         | IO16          | Interrupt DIO1 U1.                          |
| Radio A chip select | `NSS1`          | IO17          | NSS/CS U1.                                  |
| I2C SDA             | `SDA`           | IO18          | Jalur I2C data, opsional.                   |
| LED activity        | `LED`           | IO19          | LED active LOW melalui resistor.            |
| Charger status 1    | `STAT1`         | IO3           | Status BQ25185.                             |
| Charger status 2    | `STAT2`         | IO46          | Status BQ25185.                             |
| I2C SCL             | `SCL`           | IO9           | Jalur I2C clock, opsional.                  |
| SPI MOSI            | `MOSI`          | IO11          | Shared SPI untuk U1 dan U3.                 |
| SPI SCK             | `SCK`           | IO12          | Shared SPI clock.                           |
| SPI MISO            | `MISO`          | IO13          | Shared SPI input.                           |
| Radio B chip select | `NSS2`          | IO14          | NSS/CS U3.                                  |
| Radio B busy        | `BUSY2`         | IO38          | Busy SX1262 U3.                             |
| Radio B RX enable   | `RXEN2`         | IO39          | Kontrol RXEN U3 jika RF switch dipakai.     |
| Radio B TX enable   | `TXEN2`         | IO40          | Kontrol TXEN U3 jika RF switch dipakai.     |
| Radio B reset       | `LRST2`         | IO41          | Reset U3.                                   |
| Radio B DIO1        | `DIO12`         | IO42          | Interrupt DIO1 U3.                          |

### 4.2 Shared SPI Bus

Dua radio memakai satu SPI bus. Pin pada bagian ini mengikuti circuit. Karena satu SPI dipakai dua radio, firmware library final wajib memakai mutex SPI jika menggunakan FreeRTOS.

| Sinyal  | Pin ESP32-S3 |
|---|---|
| `SCK`   | IO12         | 
| `MOSI`  | IO11         | 
| `MISO`  | IO13         | 


### 4.3 Radio A / U1 / STAR

| Fungsi Radio A  | Net     | GPIO ESP32-S3 | Pin E22 | Catatan |
|---|---|---|---:|---|
| Chip select     | `NSS1`  | IO17          | 14      | NSS/CS SX1262. |
| Reset           | `LRST1` | IO7           | 4       | Reset radio. |
| Interrupt       | `DIO11` | IO16          | 20      | DIO1 untuk RX/TX done. |
| Busy            | `BUSY1` | IO15          | 11      | Busy SX1262. |
| TX enable       | `TXEN1` | IO5           | 9       | Mode transmit. |
| RX enable       | `RXEN1` | IO6           | 10      | Mode receive. |
| SPI clock       | `SCK`   | IO12          | 15      | Shared SPI. |
| SPI MOSI        | `MOSI`  | IO11          | 13      | Shared SPI. |
| SPI MISO        | `MISO`  | IO13          | 12      | Shared SPI. |
| Antenna         | `ANT1`  | -             | 7       | Ke RF connector/antenna. |

Radio A dipakai untuk node GLD/sensor:

```text
Frequency  = 920.0 MHz
Bandwidth  = 125 kHz
SF         = 7
CodingRate = 5
SyncWord   = 0x12
Power      = 22 dBm
Preamble   = 8
TCXO       = 1.6 V
```

### 4.4 Radio B / U3 / MESH

| Fungsi Radio B | Net | GPIO ESP32-S3 | Pin E22 | Catatan |
|---|---|---:|---:|---|
| Chip select | `NSS2` | IO14 | 14 | NSS/CS SX1262. |
| Reset | `LRST2` | IO41 | 4 | Reset radio. |
| Interrupt | `DIO12` | IO42 | 20 | DIO1 untuk RX/TX done. |
| Busy | `BUSY2` | IO38 | 11 | Busy SX1262. |
| TX enable | `TXEN2` | IO40 | 9 | Mode transmit. |
| RX enable | `RXEN2` | IO39 | 10 | Mode receive. |
| SPI clock | `SCK` | IO12 | 15 | Shared SPI. |
| SPI MOSI | `MOSI` | IO11 | 13 | Shared SPI. |
| SPI MISO | `MISO` | IO13 | 12 | Shared SPI. |
| Antenna | `ANT2` | - | 7 | Ke RF connector/antenna. |

Radio B dipakai untuk MESH/Gateway:

```text
Frequency  = 921.0 MHz
Bandwidth  = 125 kHz
SF         = 9
CodingRate = 5
SyncWord   = 0x34
Power      = 22 dBm
Preamble   = 8
TCXO       = 1.6 V
```

### 4.5 Battery, Charger, LED, dan USB-UART

| Komponen | Net / Pin | GPIO / Nilai | Catatan |
|---|---|---:|---|
| Battery ADC | `BATMON` | IO4 | VBAT dibaca melalui divider R3/R4. |
| Voltage divider | R3/R4 | 200k/100k | Rasio 3.0. |
| Filter ADC | C7 | 100 nF | Filter noise BATMON. |
| Battery offset | firmware | +200 mV | Koreksi kalibrasi jika hasil ukur membutuhkan. |
| LED activity | `LED` | IO19 | Active LOW. |
| Charger status 1 | `STAT1` | IO3 | Output BQ25185. |
| Charger status 2 | `STAT2` | IO46 | Output BQ25185. |
| I2C clock | `SCL` | IO9 | Opsional untuk sensor/ekspansi. |
| I2C data | `SDA` | IO18 | Opsional untuk sensor/ekspansi. |
| USB-UART | `TXD0/RXD0` | UART0 | CH340C untuk debug/programming. |

Pembacaan baterai CH:

Tegangan baterai dibaca melalui pembagi tegangan:

```text
VBAT --- R3 200k --- BATMON / IO4 ADC --- R4 100k --- GND
                         |
                        C7 100nF
                         |
                        GND
```

Formula firmware:

```text
VBAT_MV = ADC_PIN_MV * 3.0 + BATTERY_OFFSET_MV
BATTERY_OFFSET_MV = 200
BATT_FULL_MV = 4200
BATT_DEAD_MV = 3000
```

Charger BQ25185 status:

| STAT1 | STAT2 | Kondisi |
|---|---|---|
| HIGH | HIGH | Charge complete / standby |
| HIGH | LOW | Charging berlangsung |
| LOW | HIGH | Recoverable fault |
| LOW | LOW | Non-recoverable fault |

Contoh debug:

```text
[BATT] adc=1170mV vbat=3710mV percent=59 offset=200mV
```

---

## 5. Parameter Radio dan Kebijakan Airtime

**Tujuan bab:** Menetapkan parameter radio final yang menyeimbangkan jangkauan, throughput, dan konsumsi energi untuk sistem lapangan.

### 5.1 Parameter Radio Final

| Parameter | Radio A / STAR | Radio B / MESH | Alasan Keputusan |
|---|---:|---:|---|
| Frekuensi | 920.0 MHz | 921.0 MHz | Dua domain frekuensi tidak saling interferensi |
| Bandwidth | 125 kHz | 125 kHz | Stabil dan umum untuk SX1262 |
| Spreading Factor | SF7 | SF9 | STAR SF7: cepat untuk banyak node; MESH SF9: noise margin lebih baik untuk backbone |
| Coding Rate | 4/5 | 4/5 | Efisien, cukup untuk deteksi error |
| Sync Word | 0x12 | 0x34 | Memisahkan domain STAR dan MESH |
| TX Power default | **17 dBm** | **17 dBm** | Mengurangi voltage sag pada baterai/surya |
| TX Power maksimum | 22 dBm | 22 dBm | Hanya jika link budget membutuhkan, konfigurasi via NVS |
| Preamble | 8 | 8 | Cukup untuk sinkronisasi |
| TCXO | 1.6 V | 1.6 V | Sesuai modul E22 |

**Catatan TX Power:** Default awal memakai 17 dBm untuk mengurangi voltage sag pada sistem panel surya/baterai. Nilai TX power tetap dapat di-adjust sesuai kebutuhan link budget, jarak, kualitas RSSI/SNR, dan kondisi power lapangan. Mode 22 dBm hanya dipakai jika benar-benar dibutuhkan dan baterai cukup stabil.

### 5.2 Kebijakan Airtime

| Aturan | Nilai | Alasan |
|---|---|---|
| Payload GLD maksimum | 64 byte | Airtime SF7 sekitar 45 ms, aman untuk banyak node. |
| Payload MESH satu frame | 80 byte | Batas total payload `CLUSTER_DATA_RESPONSE`, termasuk header response dan semua record GLD. |
| Pull response | 1 request = batch normal dari 1 CH | `CLUSTER_DATA_RESPONSE` membawa record GLD sebanyak yang muat; tidak memakai chunk. |
| `CH_HELLO` | Tanpa ACK | Heartbeat/topologi periodik, akan terkirim ulang pada interval berikutnya. |
| `CLUSTER_DATA_RESPONSE` | Tanpa ACK | Response dikirim sekali; retry ditangani oleh request server berikutnya jika perlu. |
| Alarm | Dengan ACK | Hanya frame dengan `FLAG_ALARM_ACK` yang meminta ACK. |
| Data normal GLD | Tidak push | Tunggu server pull. |

---

## 6. Power Guard untuk Panel Surya dan Baterai

**Fungsi bab:** Menetapkan kebijakan power final agar CH tidak crash saat baterai lemah atau saat radio TX menimbulkan voltage sag.

| Parameter | Nilai final | Fungsi |
|---|---:|---|
| `BATT_START_MV_DEFAULT` | 3500 mV | Radio baru diinisialisasi jika baterai stabil di atas nilai ini. |
| `BATT_RUN_MIN_MV_DEFAULT` | 3150 mV | Batas mulai blok TX `GLD_NORMAL` dan trafik non-alarm. |
| `BATT_CRITICAL_TX_MIN_MV` | 3100 mV | Batas bawah TX alarm/kritis. |
| `BATT_STABLE_SAMPLES_DEFAULT` | 8 sampel | Baterai harus stabil beberapa kali sebelum radio aktif. |
| `BATT_STABLE_GAP_MS` | 1000 ms | Jarak antarsampel stabilitas baterai. |
| `BATT_LOW_CHECK_MS` | 5000 ms | Interval cek recovery saat low power. |
| `LOCKOUT_RESTART_MS` | 180000 ms | Restart paksa jika terlalu lama di lockout. |
| `RADIO_BOOT_HOLD_MS` | 2000 ms | Radio ditahan reset saat boot. |
| `RADIO_RESET_LOW_MS` | 300 ms | Durasi reset radio LOW. |
| `RADIO_RESET_SETTLE_MS` | 500 ms | Waktu tunggu setelah reset radio. |

Alur power:

```text
ST_BOOT
-> tahan kedua radio di RESET
-> baca baterai
-> tunggu baterai stabil >= 3500 mV
-> restart SPI dan reset radio
-> init radio dengan retry
-> operasi normal
```

Saat runtime:

- Jika baterai turun di bawah `batteryRunMinMv`, TX `GLD_NORMAL` dan trafik non-alarm diblok.
- CH masuk `ST_LOW_POWER`.
- Data alarm (`FLAG_ALARM_ACK` / `GLD_ALARM`) masih boleh TX jika baterai masih >= `BATT_CRITICAL_TX_MIN_MV`.
- Jika baterai pulih stabil, board restart agar ESP32 dan radio bersih.
- Jika lockout terlalu lama, board restart paksa agar tidak diam selamanya.

Contoh debug:

```text
[POWER] guard start=3500mV run=3150mV critical=3100mV samples=8 tx=17dBm
[POWER] sample=1/8 batt=3.612V need>=3.500V
[POWER] stable, continue
```

---


## 7. Format Frame AppFrame

**Tujuan bab:** Mendefinisikan struktur frame tunggal yang berlaku untuk komunikasi STAR dan MESH. Format ini dibuat compact agar overhead LoRa rendah, tetapi tetap memiliki identitas frame, tipe pesan, alamat, sequence, panjang payload, dan CRC.

### 7.1 Struktur Wire Format

AppFrame memakai overhead tetap **10 byte** di luar payload. Payload memakai panjang variabel `P = payloadLen`.

| Offset | Field | Ukuran | Fungsi |
|---:|---|---:|---|
| 0 | `magic` | 1 | Selalu `0xAA`. Mendeteksi awal frame yang valid. |
| 1 | `typeFlags` | 1 | Gabungan `msgType` dan flag penting. |
| 2..3 | `srcId` | 2 | ID pengirim, big-endian. |
| 4..5 | `dstId` | 2 | ID tujuan, big-endian. `0xFFFF` = broadcast. |
| 6 | `seq` | 1 | Sequence number dari pengirim, rollover `0..255`. |
| 7 | `payloadLen` | 1 | Panjang payload `P` dalam byte. |
| 8..(7+P) | `payload` | P | Data compact binary. |
| (8+P)..(9+P) | `crc16` | 2 | CRC16-CCITT-FALSE atas header + payload, big-endian. |

Isi `typeFlags`:

| Bit | Mask | Fungsi |
|---:|---:|---|
| 0..5 | `0x3F` | `msgType` dari registry pesan, nilai `0..63`. |
| 6 | `0x40` | `FLAG_ALARM_ACK`, menandai alarm. Pada data alarm berarti meminta ACK; pada ACK compact berarti balasan alarm. |
| 7 | `0x80` | `FLAG_GLD_EXT_POWER`: status power GLD pada `SENSOR_DATA`. `0` = Battery Mode, `1` = External Power Mode. |

Nilai `msgType` yang ditempatkan pada bit `0..5`:

| Nilai | Nama | Link | Fungsi |
|---:|---|---|---|
| `0x10` | `SENSOR_DATA` | STAR/MESH | Data GLD ke CH atau alarm GLD yang diteruskan CH ke parent/gateway. |
| `0x14` | `NODE_DOWNLINK` | STAR | Downlink CH ke GLD berisi command tertunda dari server; Battery Mode menunggu RX window, External Power Mode boleh langsung. |
| `0x30` | `SERVER_PULL_REQUEST` | MESH | Gateway/server meminta data latest cache dari CH. |
| `0x31` | `CLUSTER_DATA_RESPONSE` | MESH | Response batch data GLD normal dari CH target. |
| `0x32` | `SERVER_NODE_COMMAND` | MESH | Server menitipkan command GLD ke CH target untuk dikirim sebagai `NODE_DOWNLINK` sesuai status power GLD. |
| `0x33` | `CH_HELLO` | MESH | Hello/topology update dari CH. |
| `0x34` | `CH_CONFIG_REQUEST` | MESH | Discovery parent/gateway. |
| `0x35` | `CH_CONFIG_RESPONSE` | MESH | Response kandidat parent/gateway. |

Contoh nilai `typeFlags`:

| Kasus | Rumus | Nilai `typeFlags` |
|---|---|---:|
| `SENSOR_DATA` normal battery | `0x10` | `0x10` |
| `SENSOR_DATA` normal external | `0x10 OR 0x80` | `0x90` |
| `SENSOR_DATA` alarm battery | `0x10 OR 0x40` | `0x50` |
| `SENSOR_DATA` alarm external | `0x10 OR 0x40 OR 0x80` | `0xD0` |
| ACK alarm compact | `0x10 OR 0x40`, payload kosong | `0x50` |
| `CLUSTER_DATA_RESPONSE` normal | `0x31` | `0x31` |

Ukuran total frame:

```text
totalLen = 10 + payloadLen
```


Contoh AppFrame `SENSOR_DATA` normal dari GLD `0x0005` ke CH `0x0064` dengan payload 8 byte:

| Offset | Byte | Field | Nilai normal | Keterangan |
|---:|---:|---|---|---|
| 0 | 1 | `magic` | `AA` | Marker AppFrame. |
| 1 | 1 | `typeFlags` | `10` | `SENSOR_DATA` normal Battery Mode: `0x10`. Jika External Power Mode, nilai menjadi `90`. |
| 2..3 | 2 | `srcId` | `00 05` | GLD node 5. |
| 4..5 | 2 | `dstId` | `00 64` | CH tujuan. |
| 6 | 1 | `seq` | `2A` | Sequence `42`. |
| 7 | 1 | `payloadLen` | `08` | Payload 8 byte. |
| 8..15 | 8 | `payload` | `01 0C E4 0E D8 00 64 00` | Payload GLD normal compact. |
| 16..17 | 2 | `crc16` | `XX XX` | CRC16 hasil hitung header + payload. |

Full AppFrame normal:

```text
AA 10 00 05 00 64 2A 08 01 0C E4 0E D8 00 64 00 XX XX
```

Total frame normal: `10 + 8 = 18 byte`.

Contoh AppFrame `SENSOR_DATA` alarm dari GLD `0x0105` / `261` ke CH `0x0064` dengan payload 8 byte:

| Offset | Byte | Field | Nilai alarm | Keterangan |
|---:|---:|---|---|---|
| 0 | 1 | `magic` | `AA` | Marker AppFrame. |
| 1 | 1 | `typeFlags` | `50` | `SENSOR_DATA` alarm Battery Mode: `0x10 OR 0x40`. Pada arah GLD -> CH, bit 6 berarti alarm dan meminta ACK. Jika External Power Mode, nilai menjadi `D0`. |
| 2..3 | 2 | `srcId` | `01 05` | GLD node 261, big-endian. |
| 4..5 | 2 | `dstId` | `00 64` | CH tujuan. |
| 6 | 1 | `seq` | `2B` | Sequence `43`. |
| 7 | 1 | `payloadLen` | `08` | Payload 8 byte. |
| 8..15 | 8 | `payload` | `02 03 E8 0E D0 01 64 01` | Payload GLD alarm compact. |
| 16..17 | 2 | `crc16` | `XX XX` | CRC16 hasil hitung header + payload. |

Full AppFrame alarm:

```text
AA 50 01 05 00 64 2B 08 02 03 E8 0E D0 01 64 01 XX XX
```

Total frame alarm: `10 + 8 = 18 byte`.

ACK alarm compact tidak memakai `msgType` baru. Penerima alarm membalas dengan AppFrame `SENSOR_DATA | FLAG_ALARM_ACK` (`typeFlags = 0x50`), `seq` sama dengan alarm yang diterima, dan `payloadLen = 0`. Bit 7 pada ACK compact harus `0` karena ACK tidak membawa status power GLD. Pengirim tidak membalas ACK kosong ini.

### 7.2 Batas Ukuran Payload

| Link | Maks payload | Maks total frame | Catatan |
|---|---:|---:|---|
| STAR/GLD | 64 byte | 74 byte | Untuk `SENSOR_DATA`, ACK compact payload kosong, dan `NODE_DOWNLINK`. |
| MESH | 80 byte | 90 byte | Untuk alarm `SENSOR_DATA`, ACK compact payload kosong, dan `CLUSTER_DATA_RESPONSE` berisi batch record GLD normal. |

Frame yang melebihi batas payload link harus ditolak sebelum CRC diproses lebih lanjut.

### 7.3 Aturan Encoding dan Validasi

- Semua integer multibyte menggunakan **big-endian**. Field 1 byte tidak memakai endian.
- CRC dihitung dari byte offset 0 sampai byte terakhir payload, tidak termasuk field `crc16`.
- Parser wajib menolak frame jika `magic`, `payloadLen`, `msgType`, atau CRC tidak valid.
- Kombinasi `srcId + seq` dipakai untuk dedup per node.
- Retry memakai `seq` yang sama; frame baru menaikkan `seq`.
- Tidak ada field `version`, `net`, atau `ttl` di AppFrame compact.
- Domain STAR dan MESH dibedakan oleh radio fisik, frekuensi, dan sync word.

---

## 8. Registry Pesan Final

**Tujuan bab:** Menetapkan kode pesan final tanpa konflik sehingga firmware GLD, CH, gateway, dan server memakai arti byte yang sama.

AppFrame compact memakai field `typeFlags` 1 byte:

```text
typeFlags = msgType | optional FLAG_ALARM_ACK | optional FLAG_GLD_EXT_POWER
msgType   = typeFlags & 0x3F
```

Karena `msgType` hanya memakai bit 0..5, semua kode pesan harus berada di range `0x00..0x3F`.

### 8.1 STAR Messages

STAR adalah link GLD <-> CH melalui Radio A / U1.

| Kode | Nama | Arah | Fungsi | ACK |
|---:|---|---|---|---|
| `0x10` | `SENSOR_DATA` | GLD -> CH | Membawa payload GLD terbaru. Normal/alarm, battery, health, dan wake ditandai lewat flags. | ACK hanya jika `FLAG_ALARM_ACK` aktif. |
| `0x14` | `NODE_DOWNLINK` | CH -> GLD | Membawa command tertunda dari server untuk GLD. Battery Mode dikirim pada RX window setelah `SENSOR_DATA`; External Power Mode boleh langsung. | Tidak memakai ACK default; alarm ACK tetap pakai frame compact `0x50`. |

ACK alarm di STAR tidak punya kode pesan sendiri. CH membalas alarm GLD dengan `typeFlags = 0x50` (`SENSOR_DATA | FLAG_ALARM_ACK`), `srcId = clusterId`, `dstId = nodeId`, `seq` sama dengan alarm GLD, dan `payloadLen = 0`. Bit 7 pada ACK compact harus `0` karena ACK tidak membawa status power GLD. Frame ACK kosong ini tidak dibalas lagi oleh GLD.

### 8.2 MESH Messages

MESH adalah link CH <-> parent/gateway melalui Radio B / U3.

| Kode | Nama | Arah | Fungsi | ACK |
|---:|---|---|---|---|
| `0x10` | `SENSOR_DATA` | CH -> Parent/Gateway | Forward alarm GLD dari `alarmQueue`. Payload tetap format data GLD. | ACK compact jika `FLAG_ALARM_ACK` aktif. |
| `0x30` | `SERVER_PULL_REQUEST` | Gateway/CH relay -> CH | Request data dari latest cache CH target. Dapat membawa `hopList[]`. | Tanpa ACK. |
| `0x31` | `CLUSTER_DATA_RESPONSE` | CH -> Gateway | Response batch data GLD normal dari latest cache CH target. | Tanpa ACK. |
| `0x32` | `SERVER_NODE_COMMAND` | Gateway/CH relay -> CH | Command dari server untuk GLD tertentu; CH target menyimpan sebagai pending downlink. | Tanpa ACK default. |
| `0x33` | `CH_HELLO` | CH -> Parent/Gateway | Hello/topology update CH. | Tanpa ACK. |
| `0x34` | `CH_CONFIG_REQUEST` | CH -> Broadcast | Discovery parent/gateway saat boot atau failover. | Tanpa ACK; dijawab dengan `CH_CONFIG_RESPONSE`. |
| `0x35` | `CH_CONFIG_RESPONSE` | Parent/Gateway -> CH | Response kandidat parent/gateway; membawa RSSI dan SNR link yang dilihat parent/gateway agar CH pengirim dapat memilih parent terbaik. | Tanpa ACK. |

ACK alarm pada link MESH memakai format compact yang sama: `typeFlags = 0x50` (`SENSOR_DATA | FLAG_ALARM_ACK`), payload kosong, bit 7 `0`, dan `seq` sama dengan alarm yang diterima.

### 8.3 `typeFlags`

| Bit | Mask | Nama | Fungsi |
|---:|---:|---|---|
| 0..5 | `0x3F` | `MSG_TYPE_MASK` | Mengambil `msgType` dari registry pesan. |
| 6 | `0x40` | `FLAG_ALARM_ACK` | Menandai frame alarm. Pada data alarm berarti meminta ACK; pada ACK compact berarti balasan alarm. |
| 7 | `0x80` | `FLAG_GLD_EXT_POWER` | Status power GLD pada `SENSOR_DATA`: `0` Battery Mode, `1` External Power Mode. Untuk pesan non-`SENSOR_DATA`, bit ini harus `0`. |

Aturan `FLAG_ALARM_ACK`:

- Hanya data alarm dan ACK alarm compact yang boleh mengaktifkan `FLAG_ALARM_ACK`.
- Frame non-alarm lain tidak boleh meminta ACK.
- ACK alarm compact memakai `typeFlags = 0x50` dengan payload kosong, bukan `msgType` terpisah.
- ACK alarm compact payload kosong tidak boleh dibalas lagi.
- Jika alarm dikirim ulang, gunakan `seq` yang sama agar ACK tetap mengacu ke event yang sama.

Contoh `typeFlags`:

| Kasus | Rumus | Nilai |
|---|---|---:|
| `SENSOR_DATA` normal battery | `0x10` | `0x10` |
| `SENSOR_DATA` normal external | `0x10 OR 0x80` | `0x90` |
| `SENSOR_DATA` alarm battery | `0x10 OR 0x40` | `0x50` |
| `SENSOR_DATA` alarm external | `0x10 OR 0x40 OR 0x80` | `0xD0` |
| ACK alarm compact | `0x10 OR 0x40`, payload kosong | `0x50` |

Contoh decode:

```cpp
const uint8_t MSG_TYPE_MASK = 0x3F;
const uint8_t FLAG_ALARM_ACK = 0x40;
const uint8_t FLAG_GLD_EXT_POWER = 0x80;

uint8_t msgType = typeFlags & MSG_TYPE_MASK;
bool alarmAck = (typeFlags & FLAG_ALARM_ACK) != 0;
bool gldExternalPower = (typeFlags & FLAG_GLD_EXT_POWER) != 0;
```

### 8.4 msgType Range dan Validasi typeFlags

`msgType` adalah identitas jenis pesan yang disimpan di bit `0..5` dari `typeFlags`. Karena hanya tersedia 6 bit, nilai `msgType` yang valid hanya `0x00..0x3F`. Bit 6 dan bit 7 bukan bagian dari `msgType`; bit 6 dipakai sebagai `FLAG_ALARM_ACK`, sedangkan bit 7 dipakai sebagai `FLAG_GLD_EXT_POWER` untuk status power GLD pada `SENSOR_DATA`.

Parser harus selalu mengambil `msgType` dengan mask:

```cpp
msgType = typeFlags & 0x3F;
```

Contoh: `typeFlags = 0xD0` berarti `msgType = 0x10` (`SENSOR_DATA`), `FLAG_ALARM_ACK` aktif, dan `FLAG_GLD_EXT_POWER` aktif. Jadi `0xD0` bukan kode pesan baru; itu adalah `SENSOR_DATA` alarm dari GLD External Power Mode.

Range kode dibagi supaya firmware mudah membedakan domain pesan dan mencegah konflik saat fitur bertambah.

| Range | Domain | Fungsi | Contoh |
|---:|---|---|---|
| `0x00..0x0F` | Reserved protocol/internal | Cadangan untuk marker internal, test frame, atau kontrol low-level. Tidak dipakai untuk pesan aplikasi normal. | Belum digunakan. |
| `0x10..0x1F` | STAR / GLD payload | Pesan yang membawa data atau command langsung terkait GLD. Umumnya lewat Radio A, tetapi `SENSOR_DATA` alarm boleh diteruskan ke MESH agar payload alarm tidak dibungkus ulang. | `0x10 SENSOR_DATA`, `0x14 NODE_DOWNLINK`. |
| `0x20..0x2F` | Reserved ekspansi | Cadangan untuk emergency push atau fitur baru yang belum dikunci. Jangan dipakai sebelum format payload dan aturan ACK didefinisikan. | Slot cadangan. |
| `0x30..0x3F` | MESH control | Pesan kontrol antar CH, parent, dan gateway melalui Radio B. | `0x30 SERVER_PULL_REQUEST`, `0x31 CLUSTER_DATA_RESPONSE`, `0x32 SERVER_NODE_COMMAND`, `0x35 CH_CONFIG_RESPONSE`. |

Aturan pemakaian:

- Gunakan range `0x10..0x1F` untuk pesan yang payload-nya milik GLD, seperti sensor, ACK STAR, atau downlink GLD.
- Gunakan range `0x30..0x3F` untuk pesan kontrol backbone MESH, seperti pull request dan config discovery.
- `SENSOR_DATA` alarm tetap memakai `msgType = 0x10`; saat diteruskan ke parent/gateway, CH mengaktifkan `FLAG_ALARM_ACK` dan mempertahankan `FLAG_GLD_EXT_POWER` sesuai status GLD.
- Jangan menganggap `0x50`, `0x90`, `0xD0`, atau nilai lain di atas `0x3F` sebagai `msgType`. Nilai seperti itu adalah `typeFlags`, bukan registry pesan.
- Bit `0..5` adalah field angka 6-bit, bukan bit flag one-hot. Artinya lebih dari satu bit boleh bernilai `1`; contoh `0x12` dan `0x31` tetap valid sebagai `msgType` jika terdaftar di registry.
- `FLAG_GLD_EXT_POWER` hanya bermakna pada `SENSOR_DATA` yang membawa status GLD. Untuk ACK compact payload kosong, `NODE_DOWNLINK`, dan pesan kontrol MESH non-`SENSOR_DATA`, bit 7 harus `0`.
- Saat menambah pesan baru, pilih kode kosong di range yang sesuai, pastikan nilainya `<= 0x3F`, lalu update registry pesan dan format payload-nya.

Contoh validasi cepat:

| `typeFlags` | Hasil decode | Status |
|---:|---|---|
| `0x10` | `msgType=0x10 SENSOR_DATA`, alarm ACK off, Battery Mode | Valid data normal battery. |
| `0x90` | `msgType=0x10 SENSOR_DATA`, alarm ACK off, External Power Mode | Valid data normal external. |
| `0x50` | `msgType=0x10 SENSOR_DATA`, alarm ACK on, Battery Mode | Valid data alarm battery. |
| `0xD0` | `msgType=0x10 SENSOR_DATA`, alarm ACK on, External Power Mode | Valid data alarm external. |
| `0x31` | `msgType=0x31 CLUSTER_DATA_RESPONSE`, bit 7 off | Valid response pull. |
| `0xB1` | `msgType=0x31 CLUSTER_DATA_RESPONSE`, bit 7 aktif | Invalid, karena `FLAG_GLD_EXT_POWER` tidak berlaku untuk pesan kontrol non-`SENSOR_DATA`. |

---

## 9. Flags Data GLD

**Tujuan bab:** Mengklasifikasikan payload `SENSOR_DATA` tanpa field tipe paket terpisah.

Payload GLD disimpan sebagai payload mentah. Status normal/alarm, data baterai, health, dan wake ditandai dengan `flags` yang disimpan di `NodeCache`.

| Bit | Mask | Nama | Fungsi |
|---:|---:|---|---|
| 0 | `0x01` | `NC_FLAG_ALARM` | Payload terakhir adalah alarm. Diambil dari `FLAG_ALARM_ACK` pada AppFrame. |
| 1 | `0x02` | `NC_FLAG_BATT_VALID` | Payload membawa nilai baterai GLD yang valid. |
| 2 | `0x04` | `NC_FLAG_HEALTH_PRESENT` | Payload membawa data health/status GLD. |
| 3 | `0x08` | `NC_FLAG_WAKE` | Payload membawa indikator wake. Waktu wake memakai `lastSeenMs`. |
| 4 | `0x10` | `NC_FLAG_EXT_POWER` | Status power GLD terakhir. `0` = Battery Mode, `1` = External Power Mode. Diambil dari `FLAG_GLD_EXT_POWER` pada `SENSOR_DATA`. |
| 5..7 | `0xE0` | Reserved | Harus `0` sampai didefinisikan. |

`GLD_NORMAL` berarti `NC_FLAG_ALARM` tidak aktif. `GLD_ALARM` berarti `NC_FLAG_ALARM` aktif. `NC_FLAG_EXT_POWER` menyimpan status power terakhir agar CH tahu apakah `NODE_DOWNLINK` boleh dikirim langsung. Data health tidak memakai pesan terpisah; field health ikut di payload normal/alarm dan ditandai oleh `NC_FLAG_HEALTH_PRESENT`.

---

## 10. Penyimpanan Lokal CH - Latest Cache

**Tujuan bab:** Menetapkan cache RAM di CH agar server dapat mengambil payload GLD terbaru tanpa menunggu GLD aktif.

Prinsip utama:

- Latest cache hanya menyimpan data terakhir per node, bukan histori.
- Satu node hanya memiliki satu payload latest, bukan slot `gas`, `battery`, `health`, atau `wake` terpisah.
- Klasifikasi isi payload memakai `flags` di `NodeCache`.
- Status data yang belum/sudah dikirim memakai perbandingan `currentSeq` dan `sentSeq`.
- Cache bukan queue. Queue MESH tetap diatur di Section 13.
- Data normal GLD disimpan di cache dan tidak langsung di-push ke gateway.
- Data alarm di-ACK ke GLD lebih dulu jika `FLAG_ALARM_ACK` aktif, lalu masuk `alarmQueue` untuk diteruskan segera; cache ikut di-update sebagai snapshot terakhir.
- Semua data runtime disimpan di RAM, bukan flash/NVS, agar tidak menyebabkan flash wear.
- Setelah restart, latest cache kosong sampai GLD mengirim data lagi.

### 10.1 Struktur `NodeCache`

Satu `NodeCache` mewakili satu GLD.

| Field | Ukuran | Fungsi |
|---|---:|---|
| `nodeId` | 2 | ID GLD. |
| `used` | 1 | Slot node sedang dipakai. |
| `currentSeq` | 1 | Seq terakhir dari GLD di header AppFrame. |
| `sentSeq` | 1 | Seq terakhir yang sudah masuk response normal atau alarm push dan TX sukses. |
| `flags` | 1 | Flags payload: alarm, battery valid, health present, wake, external power. |
| `lastSeenMs` | 4 | Waktu terakhir CH menerima frame valid dari node ini. |
| `lastSentMs` | 4 | Waktu terakhir data node berhasil dikirim ke gateway/server. |
| `battMv` | 2 | Tegangan baterai GLD terakhir jika payload membawanya. |
| `payloadLen` | 1 | Panjang payload GLD. |
| `payload[64]` | 64 | Payload GLD asli untuk response server pull. |

Status data:

```text
unsent = currentSeq != sentSeq
sent   = currentSeq == sentSeq
```

### 10.2 Dedup dan Update Rule

Alur update cache:

```text
Terima frame GLD
  validasi AppFrame dan CRC
  cari atau buat NodeCache berdasarkan srcId
  jika used && seq == currentSeq:
    duplicate -> jangan update cache
    jika FLAG_ALARM_ACK aktif:
      kirim ACK compact ulang ke GLD
    stop
  jika slot baru:
    sentSeq = seq - 1
  currentSeq = header.seq GLD
  lastSeenMs = now
  update flags dari AppFrame/payload, termasuk `NC_FLAG_EXT_POWER` dari bit 7 `typeFlags`
  update battMv jika payload membawa baterai valid
  payloadLen = AppFrame.payloadLen
  simpan payload asli jika payloadLen <= 64
  jika FLAG_ALARM_ACK aktif:
    set NC_FLAG_ALARM
    kirim ACK compact ke GLD
    enqueue alarmQueue
  jika FLAG_ALARM_ACK tidak aktif:
    clear NC_FLAG_ALARM
```

Aturan penting:

- Duplicate frame tidak mengubah cache.
- Slot baru wajib menginisialisasi `sentSeq` ke nilai yang berbeda dari `currentSeq` agar frame pertama dianggap `unsent`.
- Retry alarm memakai `seq` yang sama, sehingga tidak membuat record baru.
- Jika payload lebih dari 64 byte, frame ditolak dan tidak masuk cache.
- `NC_FLAG_WAKE` tidak membutuhkan waktu terpisah; waktu wake sama dengan `lastSeenMs`.
- Cache tidak disimpan ke NVS/flash.
- Cache tidak ikut antrean MESH; hanya response server pull yang masuk `responseQueue`.
- Jika TX alarm atau response ke gateway/server sukses, set `sentSeq = currentSeq` dan `lastSentMs = now`.
- Jika TX alarm atau response gagal, `sentSeq` tidak berubah sehingga data tetap `unsent`.

### 10.3 Cleanup Cache

| Parameter | Nilai | Fungsi |
|---|---:|---|
| `NODE_STALE_MS` | 300000 ms | Node dianggap stale setelah 5 menit tidak ada paket. |
| `NODE_OFFLINE_MS` | 1800000 ms | Node dianggap offline setelah 30 menit. |
| `CACHE_EXPIRE_MS` | 3600000 ms | Payload cache dihapus setelah 1 jam tidak ada update. |
| `CACHE_CLEANUP_MS` | 60000 ms | Interval cleanup cache, tiap 1 menit. |

Efek ke server pull:

- Belum ada payload valid di cache -> `DATA_NOT_AVAIL`.
- Semua payload valid sudah stale -> `DATA_STALE`.
- Ada payload valid tetapi tidak ada data normal `unsent` -> `DATA_EMPTY`.
- Ada minimal satu data normal `unsent` yang muat response -> `DATA_OK`.

---

## 11. Mekanisme Server Pull

**Tujuan bab:** Menjelaskan cara server mengambil batch data GLD normal dari latest cache CH target tanpa menunggu GLD aktif, sehingga GLD bisa tidur lebih lama dan hemat energi.

Server pull adalah request ke CH target, bukan request per GLD. CH target membaca `NodeCache`, memilih data normal yang belum terkirim, lalu membungkus beberapa record GLD ke satu `CLUSTER_DATA_RESPONSE` selama masih muat dalam `MESH_MAX_PAYLOAD = 80 byte`.

Aturan `seq` AppFrame untuk pull:

- `seq` berada di header AppFrame, bukan payload.
- `seq` dari `SERVER_PULL_REQUEST` tidak berubah di setiap hop.
- `seq` yang sama dipakai pada `CLUSTER_DATA_RESPONSE` sampai kembali ke server/gateway.
- `requestId` tetap ada di payload untuk korelasi transaksi pull.
- `seq` di record GLD berbeda fungsi; itu adalah `currentSeq` dari GLD di `NodeCache`.

### 11.1 SERVER_PULL_REQUEST - Format Payload

| Offset | Field | Ukuran | Fungsi |
|---:|---|---:|---|
| 0..1 | `requestId` | 2 | ID transaksi pull, big-endian. |
| 2..N | `hopList[]` | N | Daftar CH dari gateway menuju CH target, 2 byte per CH. Entry pertama adalah CH penerima saat ini; entry terakhir adalah CH target. |

Ukuran dan validasi:

```text
payloadLen = 2 + (hopCount * 2)
hopCount = (payloadLen - 2) / 2
```

Valid jika:

- `payloadLen >= 4`.
- `(payloadLen - 2) % 2 == 0`.
- `hopCount >= 1`.
- `hopList[0] == clusterId` CH penerima.
- Entry terakhir `hopList[]` adalah CH target.

Tidak ada `nodeId`, `dataType`, atau `targetCluster` terpisah. CH target selalu memilih data normal `unsent` dari seluruh `NodeCache`.

`hopList[]` hanya untuk arah gateway/server ke CH target.

Contoh:

```text
Gateway -> CH1 -> CH2 -> CH3 -> CH4
hopList[] = CH1, CH2, CH3, CH4
```

Saat gateway atau relay mengirim request, AppFrame `dstId` diisi dengan entry pertama `hopList[]`. Saat CH relay menerima request:

```text
jika hopList[0] != clusterId:
  drop

jika hopCount > 1:
  hapus hopList[0]
  payloadLen -= 2
  dstId = hopList[0] baru
  seq tetap sama
  requestId tetap sama
  forward

jika hopCount == 1:
  CH ini target
  proses NodeCache
```

Response balik tidak memakai reverse `hopList[]`; response mengikuti parent aktif CH menuju gateway/server.

Aturan invalid:

- Request dengan ukuran rusak, `hopList[]` rusak, atau `hopList[0]` tidak cocok dianggap `DATA_INVALID` jika CH masih bisa menjawab; jika frame bukan untuk CH ini, frame di-drop.
- Request valid tetapi CH sedang tidak bisa mengirim response karena radio/queue tertahan dijawab `DATA_BUSY` jika masih memungkinkan.

### 11.2 CLUSTER_DATA_RESPONSE - Format Payload

`CLUSTER_DATA_RESPONSE` dipakai untuk response normal hasil pull. Frame response memakai `typeFlags = CLUSTER_DATA_RESPONSE`, `seq` sama dengan request asal, dan dikirim balik melalui parent aktif CH.

Header response:

| Offset | Field | Ukuran | Fungsi |
|---:|---|---:|---|
| 0..1 | `requestId` | 2 | Sama dengan request asal. |
| 2 | `status` | 1 | Status response. |
| 3..4 | `chBatteryMv` | 2 | Tegangan baterai CH target saat response dibuat. |
| 5 | `recordCount` | 1 | Jumlah record GLD. |

Record GLD repeated:

| Field | Ukuran | Fungsi |
|---|---:|---|
| `nodeId` | 2 | ID GLD. |
| `seq` | 1 | `currentSeq` GLD dari `NodeCache`. |
| `flags` | 1 | Flags dari `NodeCache`. |
| `payloadLen` | 1 | Panjang payload GLD. |
| `payload` | N | Payload GLD asli. |

Ukuran:

```text
MESH_MAX_PAYLOAD = 80
responseHeader = 6
recordOverhead = 5
recordSize = 5 + payloadLen
total = 6 + sum(recordSize)
```

Valid jika:

```text
total <= 80
payloadLen tiap record <= 64
```

**Status response:**

| Kode | Nama | Fungsi |
|---:|---|---|
| `0x00` | `DATA_OK` | Ada minimal 1 record GLD normal dalam response. |
| `0x01` | `DATA_EMPTY` | Tidak ada normal `unsent`. |
| `0x02` | `DATA_NOT_AVAIL` | Cache belum punya payload valid. |
| `0x03` | `DATA_STALE` | Semua data valid sudah stale. |
| `0x04` | `DATA_BUSY` | Radio/queue belum bisa mengirim response. |
| `0x05` | `DATA_INVALID` | Request invalid, `hopList[]` rusak, atau ukuran tidak valid. |

Aturan status:

- `DATA_OK` wajib `recordCount > 0`.
- Status selain `DATA_OK` wajib `recordCount = 0`.
- Total payload response wajib `<= 80 byte`.
- Setiap record wajib memiliki `payloadLen <= 64`.

### 11.3 Aturan Pull 

- Request data dari server **tidak diteruskan ke GLD**.
- `SERVER_PULL_REQUEST` menuju CH target, bukan menuju GLD tertentu.
- CH target menjawab dengan `CLUSTER_DATA_RESPONSE` berisi batch data normal `unsent` dari `NodeCache`.
- Alarm tidak digabung dengan response normal; alarm selalu masuk `alarmQueue`.
- Jika server membutuhkan data lebih segar, server harus menunggu laporan GLD berikutnya lalu melakukan pull ulang. CH tidak mengirim command ke GLD hanya karena ada request server.

Saat `SERVER_PULL_REQUEST` sampai CH target:

1. Scan `NodeCache`.
2. Abaikan node kosong, stale, payload invalid, atau alarm.
3. Ambil hanya data normal `unsent`:

```text
currentSeq != sentSeq
NC_FLAG_ALARM tidak aktif
```

4. Urutkan oldest first berdasarkan `lastSeenMs`.
5. Masukkan record sebanyak yang muat.

Packing:

```text
used = 6
recordCount = 0

for node in normalUnsentOldestFirst:
  recordSize = 5 + node.payloadLen

  if used + recordSize > 80:
    continue

  add node to response
  used += recordSize
  recordCount++
```

Gunakan `continue`, bukan `stop`, agar node payload besar yang tidak muat tidak menghalangi node berikutnya yang lebih kecil.

Aturan status saat tidak ada record yang masuk response:

- Jika cache belum punya payload valid sama sekali, gunakan `DATA_NOT_AVAIL`.
- Jika semua payload valid sudah stale, gunakan `DATA_STALE`.
- Jika ada payload valid non-stale tetapi tidak ada data normal `unsent`, gunakan `DATA_EMPTY`.

Untuk `DATA_EMPTY`:

```text
status = DATA_EMPTY
recordCount = 0
```

Tidak refresh data lama secara default. Jika `CLUSTER_DATA_RESPONSE` berhasil TX ke gateway/server, CH menandai semua node yang masuk record sebagai terkirim:

```text
sentSeq = currentSeq
lastSentMs = now
```

Jika TX gagal:

```text
sentSeq tidak berubah
data tetap unsent
```

Contoh kapasitas jika `payloadLen GLD = 10 byte`:

```text
recordSize = 5 + 10 = 15
sisa record = 80 - 6 = 74
maks record = floor(74 / 15) = 4
```

Jadi 10 GLD normal butuh:

```text
Pull 1: 4 GLD
Pull 2: 4 GLD
Pull 3: 2 GLD
```

Jika ada 1 GLD alarm di tengah:

```text
alarm langsung push via alarmQueue
tidak menunggu pull
tidak digabung dengan normal batch
```

Contoh debug:

```text
[PULL] request from=0x006F request=44 hops=1 target=0x0064
[PULL_RESP] request=44 status=DATA_OK records=4 bytes=66
```

---

## 12. Command Server dan Downlink GLD

**Tujuan bab:** Menegaskan batas komunikasi command: server tidak berbicara langsung ke GLD. Server menitipkan command ke CH target melalui MESH, lalu CH mengirim command itu ke GLD sebagai `NODE_DOWNLINK` sesuai status power GLD.

Keputusan final:

- `SERVER_PULL_REQUEST` tetap hanya mengambil latest cache di CH target; request data tidak diteruskan ke GLD dan tidak memilih `nodeId` tertentu.
- Command GLD dari server masuk ke CH target memakai `SERVER_NODE_COMMAND`.
- CH menyimpan command sebagai **pending downlink** per `nodeId` di RAM.
- Jika status terakhir GLD adalah Battery Mode atau belum diketahui, CH tidak membangunkan GLD dan menunggu RX window setelah `SENSOR_DATA`.
- Jika status terakhir GLD adalah External Power Mode (`NC_FLAG_EXT_POWER = 1`), CH boleh mengirim `NODE_DOWNLINK` langsung tanpa menunggu `SENSOR_DATA` berikutnya.
- GLD Battery Mode dianggap siap menerima downlink hanya pada RX window setelah CH menerima `SENSOR_DATA` dari GLD tersebut.
- Jika `SENSOR_DATA` adalah alarm, CH wajib mengirim ACK alarm compact lebih dulu, baru boleh mengirim `NODE_DOWNLINK` jika ada pending command.
- Jika tidak ada pending command untuk node tersebut, CH tidak mengirim `NODE_DOWNLINK`.

### 12.1 Pesan yang Diizinkan dari Server/Gateway ke CH

| Pesan | Fungsi | Boleh diteruskan ke GLD? |
|---|---|---|
| `SERVER_PULL_REQUEST` | Mengambil batch data GLD normal `unsent` dari latest cache CH target. | Tidak. |
| `SERVER_NODE_COMMAND` | Menitipkan command untuk GLD tertentu ke CH target. | Tidak langsung; disimpan dulu sebagai pending downlink. |
| `CH_CONFIG_RESPONSE` | Balasan discovery/config untuk CH. | Tidak. |
| `SENSOR_DATA OR FLAG_ALARM_ACK` payload kosong | ACK compact untuk alarm MESH yang diterima parent/gateway. | Tidak. |

### 12.2 Pesan yang Diizinkan dari GLD ke CH

| Pesan | Fungsi | Efek ke downlink |
|---|---|---|
| `SENSOR_DATA` normal | Update latest cache CH dan status power dari bit 7 `typeFlags`. | Jika Battery Mode, CH boleh mengirim `NODE_DOWNLINK` pada RX window ini. Jika External Power Mode, pending command bisa dikirim langsung tanpa menunggu window ini. |
| `SENSOR_DATA` alarm | Update latest cache dan status power dari bit 7 `typeFlags`; ACK alarm didahulukan, lalu masuk `alarmQueue`. | ACK alarm compact dikirim lebih dulu; setelah itu CH boleh mengirim `NODE_DOWNLINK` jika ada pending command. |
| Flags battery/health/wake dalam payload `SENSOR_DATA` | Update `flags`, `battMv` jika ada, dan payload latest di `NodeCache`. | Power status berasal dari bit 7 `typeFlags`; wake tetap menandai RX window untuk Battery Mode. |

### 12.3 `SERVER_NODE_COMMAND` ke Pending Downlink

`SERVER_NODE_COMMAND` adalah pesan MESH dari server/gateway menuju CH target. Pesan ini tidak dikirim langsung ke GLD. CH target menyimpan command sebagai pending downlink untuk `nodeId` yang dituju.

Isi minimal pending downlink:

| Field | Fungsi |
|---|---|
| `nodeId` | GLD tujuan command. |
| `commandId` | ID command dari server untuk dedup/status. |
| `commandLen` | Panjang payload command. |
| `commandPayload[]` | Isi command yang akan dikirim ke GLD lewat `NODE_DOWNLINK`. |
| `createdMs` / `ttlMs` | Waktu masuk dan masa berlaku command. |

Policy pending downlink awal: satu pending command per GLD. Jika command baru datang untuk node yang sama sebelum command lama terkirim, policy overwrite/drop masih **to be discussed**.

### 12.4 `NODE_DOWNLINK` STAR

`NODE_DOWNLINK` (`0x14`) adalah frame STAR dari CH ke GLD yang membawa command tertunda dari server.

Aturan pengiriman:

- Untuk GLD Battery Mode atau status belum diketahui, `NODE_DOWNLINK` hanya boleh dikirim pada RX window setelah CH menerima `SENSOR_DATA` valid dari GLD yang sama.
- Untuk GLD External Power Mode, `NODE_DOWNLINK` boleh dikirim langsung setelah `SERVER_NODE_COMMAND` disimpan, tanpa menunggu `SENSOR_DATA` berikutnya.
- Untuk alarm, ACK compact `typeFlags = 0x50` wajib dikirim lebih dulu sebelum `NODE_DOWNLINK`.
- `NODE_DOWNLINK` tidak dipicu oleh `SERVER_PULL_REQUEST`.
- Jika payload command melebihi batas STAR, command ditolak atau ditandai invalid sebelum disimpan.
- Setelah `NODE_DOWNLINK` dikirim, CH menandai command sebagai terkirim atau menunggu status command sesuai policy yang masih **to be discussed**.

### 12.5 Implikasi ke Server Pull

Jika server membutuhkan data GLD yang lebih baru:

1. Server mengirim `SERVER_PULL_REQUEST` ke CH.
2. CH menjawab dari latest cache dengan batch data normal `unsent` yang masih muat 80 byte.
3. Jika data belum ada, tidak ada normal `unsent`, atau semua data stale, CH menjawab status `DATA_NOT_AVAIL`, `DATA_EMPTY`, atau `DATA_STALE`.
4. Server menunggu siklus laporan GLD berikutnya, lalu melakukan pull ulang.

Jika server ingin memberi perintah ke GLD, server mengirim `SERVER_NODE_COMMAND` ke CH target. Untuk Battery Mode, command itu tidak memaksa GLD bangun; CH baru mengirimnya sebagai `NODE_DOWNLINK` saat GLD mengirim `SENSOR_DATA` berikutnya. Untuk External Power Mode, CH boleh mengirim `NODE_DOWNLINK` langsung berdasarkan status power terakhir di `NodeCache`.

### 12.6 Ringkasan Batas Domain

```text
GLD <-> CH      : STAR only
CH  <-> Gateway : MESH only
Server -> CH    : pull/config/command
Server -> GLD   : tidak langsung; lewat pending downlink di CH
CH -> GLD       : NODE_DOWNLINK langsung jika external power; Battery Mode menunggu RX window; ACK alarm tetap prioritas pertama
GLD -> Server   : tidak langsung; selalu melalui cache/queue CH
```

## 13. Queue MESH

**Tujuan bab:** Menjelaskan antrean pengiriman MESH agar pesan penting tetap terkirim saat link buruk atau gateway sibuk, tanpa memenuhi RAM.

### 13.1 Struktur Queue

| Queue | Kapasitas | Prioritas | Isi |
|---|---:|---:|---|
| `alarmQueue` | 8 | 1 (tertinggi) | Alarm GLD dan charger fault kritis yang harus di-push segera ke parent/gateway. |
| `responseQueue` | 8 | 2 | `CLUSTER_DATA_RESPONSE`, response kritis. |
| `helloQueue` | 4 | 3 (terendah) | `CH_HELLO`. |

Urutan proses TX: **alarm -> response -> hello**.

### 13.2 Kebijakan Queue Penuh

| Kondisi | Tindakan |
|---|---|
| Response queue penuh | Tolak response baru dengan status `DATA_BUSY` jika masih bisa dijawab, atau log drop jika radio/queue benar-benar penuh. |
| Hello queue penuh | Skip `CH_HELLO` periode ini. |
| Alarm queue penuh | Pertahankan alarm terlama yang belum dikirim, log warning. |
| Frame terlalu besar | Skip record yang tidak muat. Jika request/format rusak, kirim `DATA_INVALID`; pull tidak memakai chunk. |

---

## 14. ACK, Retry, dan Failover Parent

**Tujuan bab:** Menetapkan reliabilitas MESH untuk alarm tanpa membebani airtime pesan normal.

### 14.1 Aturan ACK

- ACK hanya dipakai untuk frame dengan `FLAG_ALARM_ACK`.
- Frame alarm wajib membawa `FLAG_ALARM_ACK`.
- Frame non-alarm tidak meminta ACK, termasuk `CH_HELLO` dan `CLUSTER_DATA_RESPONSE`.
- Jika pengirim menerima ACK compact `SENSOR_DATA | FLAG_ALARM_ACK` dengan payload kosong dan `seq` yang sama, alarm dianggap sampai ke next hop/parent.
- Jika ACK alarm tidak diterima sampai timeout, alarm di-retry sesuai `ALARM_RETRY_MAX`.

### 14.2 Parameter Retry Alarm

| Parameter | Nilai | Fungsi |
|---|---:|---|
| `ALARM_ACK_TMO_MS` | 1500 ms | Timeout tunggu ACK compact untuk frame alarm. |
| `ALARM_RETRY_MAX` | 5 | Retry maksimum untuk alarm/kritis. |
| Backoff alarm | 200 ms * 2^attempt | Jeda eksponensial antar retry alarm. |
| `PARENT_FAIL_TH` | 3 | Failover setelah alarm gagal ACK 3 kali berturut-turut ke parent yang sama. |
| `NO_ACK_RECOVERY_TH` | 5 | Reset radio setelah no-ACK alarm 5 kali beruntun. |
| `FAILOVER_CDN_MS` | 60000 ms | Cooldown anti parent-flapping. |

### 14.3 ACK Alarm Compact

ACK alarm tidak memakai payload khusus dan tidak punya `msgType` sendiri.

| Field | Nilai |
|---|---|
| `typeFlags` | `SENSOR_DATA OR FLAG_ALARM_ACK` (`0x50`), bit 7 harus `0`. |
| `srcId` | ID penerima alarm. |
| `dstId` | ID pengirim alarm. |
| `seq` | Sama dengan alarm yang diterima. |
| `payloadLen` | `0`. |
| `payload` | Kosong. |

Aturan interpretasi:

- `FLAG_ALARM_ACK` aktif dengan `payloadLen > 0` berarti data alarm. Nilai `typeFlags` bisa `0x50` untuk Battery Mode atau `0xD0` untuk External Power Mode.
- `typeFlags = 0x50` dengan `payloadLen = 0` berarti ACK compact. Bit 7 pada ACK compact harus `0`.
- Format ACK compact ini dipakai di STAR dan MESH.

### 14.4 Alur Failover

```text
TX alarm ke parent, menunggu ACK
  ACK diterima:
    failCnt = 0
    alarm dianggap sampai ke next hop
  ACK timeout:
    retry alarm sampai ALARM_RETRY_MAX
    failCnt++
  Jika failCnt >= PARENT_FAIL_TH:
    coba parentAlt jika ada
    jika sukses, swap parent/parentAlt dan kirim CH_HELLO berikutnya
    jika gagal, jalankan CH_CONFIG ulang
  Jika noAckBurst >= NO_ACK_RECOVERY_TH:
    reset radio U3
```

Queue tidak dihapus saat failover. Data tetap tersimpan dan dikirim ke parent baru.

---

## 15. CH_CONFIG dan CH_HELLO

**Fungsi bab:** Menentukan mekanisme topologi dan hello CH. Monitoring tegangan baterai CH dikirim di header setiap `CLUSTER_DATA_RESPONSE`.

### 15.1 CH_CONFIG

**Fungsi subbab:** Menemukan parent terbaik saat boot/recovery.

- CH broadcast `CH_CONFIG_REQUEST`.
- Parent/gateway membalas `CH_CONFIG_RESPONSE`.
- CH memilih RSSI terbaik sebagai `parent_id`.
- Kandidat kedua menjadi `parent_id_alt`.
- Parent disimpan ke storage config persisten setelah discovery sukses.

### 15.2 CH_HELLO

**Fungsi subbab:** Memberitahu gateway/server bahwa CH aktif, parent valid, dan mendukung capability final.

Payload ringkas:

| Field | Ukuran | Fungsi |
|---|---:|---|
| `clusterId` | 2 | ID CH. |
| `parentId` | 2 | Parent aktif. |
| `gatewayId` | 2 | Gateway root. |
| `batteryMv` | 2 | Tegangan CH saat hello dikirim. |
| `stat1` | 1 | Charger status. |
| `stat2` | 1 | Charger status. |
| `uptimeS` | 4 | Uptime detik. |
| `meshDepth` | 1 | Jumlah hop dari CH ke gateway melalui parent aktif; hanya informasi topologi. |
| `protocolVersion` | 1 | Versi protokol. |
| `role` | 1 | Role CH. |
| `caps` | 2 | Capability bitmask. |

Interval final `CH_HELLO`: 300 detik.

`CH_HELLO` tidak meminta ACK agar airtime hemat. Untuk monitoring yang lebih sering, server membaca `chBatteryMv` dari setiap `CLUSTER_DATA_RESPONSE`.

---

## 16. Alur Lengkap: RX STAR dari GLD

**Tujuan bab:** Menetapkan urutan pemrosesan saat CH menerima data dari GLD.

```text
GLD mengirim SENSOR_DATA
  CH: validasi AppFrame (magic, typeFlags, payloadLen, CRC)
    CRC gagal -> buang, log [STAR_RX] CRC_ERR
  CH: periksa dstId (harus = clusterId atau broadcast)
  CH: periksa dedup (srcId + currentSeq per node)
    Duplicate -> jangan update cache
  CH: update NodeCache (data terbaru)

  Jika FLAG_ALARM_ACK aktif:
    Kirim ACK compact ke GLD lebih dulu: typeFlags=0x50, seq=sama dengan alarm, payloadLen=0
    Jangan kirim `NODE_DOWNLINK`/pending command ke GLD sebelum ACK alarm selesai
    Set `NC_FLAG_ALARM`; set/clear `NC_FLAG_EXT_POWER` dari bit 7 `typeFlags`; set `NC_FLAG_WAKE` jika payload membawa indikator wake
    Pastikan frame forward ke MESH membawa FLAG_ALARM_ACK
    Masukkan alarm ke alarmQueue untuk diteruskan ke parent/gateway dan tunggu ACK compact
    Pada proses TX MESH berikutnya, jika TX alarm ke parent/gateway sukses:
      sentSeq = currentSeq
      lastSentMs = now
    Jika TX alarm gagal:
      sentSeq tidak berubah, alarmQueue retry sesuai aturan alarm

  Jika FLAG_ALARM_ACK tidak aktif:
    Tidak kirim ACK
    Clear `NC_FLAG_ALARM`; set/clear `NC_FLAG_EXT_POWER` dari bit 7 `typeFlags`; set `NC_FLAG_WAKE` jika payload membawa indikator wake
    Data tetap `unsent` sampai masuk `CLUSTER_DATA_RESPONSE` dan TX sukses

  Setelah ACK/cache/alarm diproses:
    Jika ada pending downlink untuk srcId dan GLD Battery Mode:
      Kirim `NODE_DOWNLINK` ke GLD pada RX window saat ini
      Payload `NODE_DOWNLINK` = `commandPayload[]` dari `SERVER_NODE_COMMAND`
      Tandai command terkirim atau tunggu status command sesuai policy
```

---
## 17. Alur Lengkap: RX MESH dari Gateway

**Tujuan bab:** Menetapkan urutan pemrosesan saat CH menerima pesan dari gateway atau parent CH.

```text
Frame MESH masuk
  Validasi AppFrame (magic, typeFlags, payloadLen, CRC)
    CRC gagal -> buang
  Periksa dstId
    Bukan untuk CH ini -> buang atau forward jika CH adalah relay

  Jika FLAG_ALARM_ACK aktif dan payloadLen > 0:
    Kirim ACK compact ke pengirim:
      typeFlags=0x50, seq=sama dengan alarm, payloadLen=0

  Jika typeFlags=0x50 dan payloadLen=0:
    Selesaikan TX alarm aktif yang menunggu ACK

  Jika tidak ada FLAG_ALARM_ACK:
    Tidak kirim ACK

  Dispatch berdasarkan msgType:
    SENSOR_DATA alarm        -> update/relay alarm sesuai route MESH
    SERVER_PULL_REQUEST      -> handleServerPull()
                                validasi `hopList[]`
                                forward jika CH ini masih relay
                                jika CH target, pack normal `unsent` dari `NodeCache`
    SERVER_NODE_COMMAND      -> simpan pending downlink untuk nodeId tujuan
                                jika `NodeCache` `nodeId` menunjukkan External Power Mode, kirim `NODE_DOWNLINK` langsung
    CH_CONFIG_REQUEST        -> kirim CH_CONFIG_RESPONSE jika parent valid
    CH_HELLO dari child      -> catat children (untuk tree routing)
```

---
## 18. Persistent Storage Config (TO BE DISCUSSED)

**Fungsi bab:** Menentukan data apa yang boleh disimpan permanen. Mekanisme final masih TO BE DISCUSSED; kandidat utama adalah ESP32 Preferences / NVS.

| Data | Disimpan permanen | Alasan |
|---|---|---|
| `cluster_id` | Ya | Identitas board. |
| `gateway_id` | Ya | Root tujuan. |
| `parent_id` | Ya | Mempercepat boot berikutnya. |
| `parent_id_alt` | Ya | Failover awal. |
| `statusMs` | Ya | Tuning airtime. |
| `helloMs` | Ya | Tuning topologi. |
| `batteryStartMv` | Ya | Tuning panel surya/baterai. |
| `batteryRunMinMv` | Ya | Tuning power guard. |
| `txPwr` | Ya | Tuning link budget. |
| Cache GLD | Tidak | Menghindari flash wear. |
| Queue | Tidak | Runtime RAM saja. |

Jika NVS dipilih, namespace kandidat: `chdual`.

Aturan tulis storage persisten

- Parent baru disimpan hanya setelah CH_CONFIG sukses atau failover stabil.
- Tambahkan debounce: jangan simpan parent jika belum berhasil 2 kali dengan parent yang sama.
- Cache dan queue **tidak** disimpan ke storage persisten.

---



## 19. State Machine

**Tujuan bab:** Mendefinisikan state operasional CH agar transisi power, radio, parent, queue, dan cache berlangsung deterministik serta mudah di-debug.

Request MESH dari server dapat membawa `hopList[]` menuju CH target. Response dari CH target kembali ke gateway melalui parent aktif, bukan memakai `hopList[]` request.

### 19.1 Daftar State

| State | Fungsi utama | Radio | TX MESH |
|---|---|---|---|
| `ST_BOOT` | Inisialisasi awal: serial, pin, watchdog, load config. | Radio ditahan reset. | Tidak boleh. |
| `ST_WAIT_BATT` | Menunggu baterai stabil sebelum radio aktif. | Radio tetap reset. | Tidak boleh. |
| `ST_RADIO_INIT` | Init SPI, U1 STAR, dan U3 MESH. | Sedang init/reset. | Tidak boleh. |
| `ST_JOINING` | Mencari/validasi parent melalui `CH_CONFIG`. | STAR/MESH sudah siap. | Hanya `CH_CONFIG_REQUEST`. |
| `ST_JOINED` | Operasi normal. | STAR/MESH aktif. | Queue aktif sesuai prioritas. |
| `ST_LOW_POWER` | Baterai di bawah `batteryRunMinMv`. | Radio tetap aktif jika masih aman. | Alarm saja jika `batteryMv >= BATT_CRITICAL_TX_MIN_MV`. |
| `ST_PARENT_FAILOVER` | Memindahkan parent karena ACK alarm gagal atau parent hilang. | MESH aktif. | `CH_CONFIG_REQUEST`, alarm retry, lalu queue ke parent baru. |
| `ST_RECOVERY` | Recovery radio setelah error/no-ACK beruntun. | Radio di-reset ulang. | Ditahan sementara. |
| `ST_RESTART` | Restart terkontrol. | Tidak relevan. | Tidak boleh. |

### 19.2 Diagram Transisi

```text
ST_BOOT
  -> ST_WAIT_BATT
  -> ST_RADIO_INIT
  -> ST_JOINING
  -> ST_JOINED

ST_JOINED
  -> ST_LOW_POWER          jika batteryMv < batteryRunMinMv
  -> ST_PARENT_FAILOVER    jika parent gagal ACK alarm >= PARENT_FAIL_TH
  -> ST_RECOVERY           jika radio error atau noAckBurst >= NO_ACK_RECOVERY_TH

ST_LOW_POWER
  -> ST_RESTART            jika baterai pulih stabil atau lockout terlalu lama
  -> ST_RECOVERY           jika radio error saat alarm

ST_PARENT_FAILOVER
  -> ST_JOINED             jika parentAlt atau CH_CONFIG sukses
  -> ST_JOINING            jika belum ada parent valid
  -> ST_RECOVERY           jika radio MESH perlu reset

ST_RECOVERY
  -> ST_RADIO_INIT

ST_RESTART
  -> reboot ESP32
```

### 19.3 Tabel Transisi Detail

| Dari | Kondisi | Ke | Aksi |
|---|---|---|---|
| `ST_BOOT` | Setup dasar selesai. | `ST_WAIT_BATT` | Tahan U1/U3 reset, mulai sampling baterai. |
| `ST_WAIT_BATT` | Baterai stabil `>= BATT_START_MV_DEFAULT`. | `ST_RADIO_INIT` | Lepas reset radio sesuai `RADIO_BOOT_HOLD_MS`, lalu init SPI. |
| `ST_WAIT_BATT` | Lockout `>= LOCKOUT_RESTART_MS`. | `ST_RESTART` | Restart agar board tidak diam selamanya. |
| `ST_RADIO_INIT` | U1 dan U3 berhasil init. | `ST_JOINING` | Apply parameter radio Section 5, mulai discovery parent. |
| `ST_RADIO_INIT` | Init radio gagal. | `ST_RECOVERY` | Reset radio dengan `RADIO_RESET_LOW_MS` dan `RADIO_RESET_SETTLE_MS`. |
| `ST_JOINING` | Parent dari config valid atau `CH_CONFIG_RESPONSE` diterima. | `ST_JOINED` | Set `parentId`, enqueue `CH_HELLO`, mulai RX penuh. |
| `ST_JOINING` | Belum ada parent. | `ST_JOINING` | Retry `CH_CONFIG_REQUEST` dengan interval/backoff. |
| `ST_JOINED` | Baterai `< batteryRunMinMv`. | `ST_LOW_POWER` | Tahan TX normal; cache tetap update. |
| `ST_JOINED` | Alarm gagal ACK ke parent `>= PARENT_FAIL_TH`. | `ST_PARENT_FAILOVER` | Coba `parentIdAlt`, lalu `CH_CONFIG` jika perlu. |
| `ST_JOINED` | `noAckBurst >= NO_ACK_RECOVERY_TH` atau radio error. | `ST_RECOVERY` | Reset radio yang bermasalah; queue tidak dihapus. |
| `ST_LOW_POWER` | Baterai masih `< BATT_CRITICAL_TX_MIN_MV`. | `ST_LOW_POWER` | Blok semua TX radio; tetap sampling baterai. |
| `ST_LOW_POWER` | Baterai `>= BATT_CRITICAL_TX_MIN_MV`. | `ST_LOW_POWER` | Alarm boleh TX; `GLD_NORMAL` tetap diblok. |
| `ST_LOW_POWER` | Baterai pulih stabil. | `ST_RESTART` | Restart bersih agar ESP32/radio kembali normal. |
| `ST_PARENT_FAILOVER` | Parent baru valid. | `ST_JOINED` | Simpan parent setelah stabil, kirim `CH_HELLO`, lanjutkan queue. |
| `ST_PARENT_FAILOVER` | Tidak ada parent valid. | `ST_JOINING` | Discovery parent ulang. |
| `ST_RECOVERY` | Reset radio selesai. | `ST_RADIO_INIT` | Init ulang radio. |
| `ST_RESTART` | Aksi restart dipanggil. | - | `ESP.restart()`. |

### 19.4 Aturan Per State

| State | STAR RX dari GLD | MESH RX dari parent/gateway | Queue MESH | Cache GLD |
|---|---|---|---|---|
| `ST_BOOT` | Tidak aktif. | Tidak aktif. | Ditahan. | RAM di-init kosong. |
| `ST_WAIT_BATT` | Tidak aktif. | Tidak aktif. | Ditahan. | Tidak update. |
| `ST_RADIO_INIT` | Tidak aktif sampai init selesai. | Tidak aktif sampai init selesai. | Ditahan. | Tidak update. |
| `ST_JOINING` | Boleh aktif setelah U1 siap. | Hanya untuk `CH_CONFIG_RESPONSE`. | Alarm boleh disimpan, TX ditahan sampai parent valid. | Update jika STAR RX aktif. |
| `ST_JOINED` | Aktif penuh. | Aktif penuh. | Aktif sesuai Section 13. | Update sesuai Section 10. |
| `ST_LOW_POWER` | Aktif jika radio aman. | Aktif jika radio aman. | Hanya alarm jika baterai cukup. | Tetap update untuk data masuk. |
| `ST_PARENT_FAILOVER` | Tetap aktif. | Terbatas untuk parent discovery/ACK. | Queue ditahan sementara, alarm tetap prioritas. | Tetap update. |
| `ST_RECOVERY` | Pause sementara. | Pause sementara. | Tidak dihapus. | Tidak dihapus. |
| `ST_RESTART` | Tidak aktif. | Tidak aktif. | Hilang setelah restart karena RAM-only. | Hilang setelah restart karena RAM-only. |

### 19.5 Event yang Mengubah State

| Event | Sumber | Efek |
|---|---|---|
| `EV_BATT_STABLE` | Power guard | `ST_WAIT_BATT -> ST_RADIO_INIT`. |
| `EV_BATT_LOW` | Power guard | `ST_JOINED -> ST_LOW_POWER`. |
| `EV_BATT_RECOVERED` | Power guard | `ST_LOW_POWER -> ST_RESTART`. |
| `EV_RADIO_INIT_OK` | Radio init | `ST_RADIO_INIT -> ST_JOINING`. |
| `EV_RADIO_INIT_FAIL` | Radio init | `ST_RADIO_INIT -> ST_RECOVERY`. |
| `EV_PARENT_FOUND` | `CH_CONFIG_RESPONSE` atau config valid | `ST_JOINING -> ST_JOINED`. |
| `EV_PARENT_ACK_FAIL` | Alarm ACK timeout | `ST_JOINED -> ST_PARENT_FAILOVER`. |
| `EV_NO_ACK_BURST` | Retry alarm | `ST_JOINED -> ST_RECOVERY`. |
| `EV_RADIO_ERROR` | Driver radio | State aktif -> `ST_RECOVERY`. |
| `EV_LOCKOUT_TIMEOUT` | Power guard | `ST_WAIT_BATT`/`ST_LOW_POWER -> ST_RESTART`. |

### 19.6 Variabel State Minimum

| Variabel | Fungsi |
|---|---|
| `chState` | State aktif saat ini. |
| `stateSinceMs` | Waktu masuk state, untuk timeout/debug. |
| `batteryMv` | Nilai baterai terakhir. |
| `parentId` | Parent MESH aktif. |
| `parentIdAlt` | Kandidat parent cadangan. |
| `parentFailCnt` | Hitungan gagal ACK alarm ke parent aktif. |
| `noAckBurst` | Hitungan no-ACK beruntun untuk recovery radio. |
| `radioStarOk` | Status U1 STAR. |
| `radioMeshOk` | Status U3 MESH. |
| `lockoutSinceMs` | Waktu mulai lockout power. |

### 19.7 Contoh Log Debug

```text
[STATE] ST_BOOT -> ST_WAIT_BATT reason=boot
[POWER] sample=8/8 batt=3612mV need>=3500mV
[STATE] ST_WAIT_BATT -> ST_RADIO_INIT reason=battery_stable
[RADIO] init ok star=1 mesh=1
[STATE] ST_RADIO_INIT -> ST_JOINING reason=radio_ok
[CONFIG] parent=0x0001 alt=0x0002 rssi=-83
[STATE] ST_JOINING -> ST_JOINED reason=parent_found
[STATE] ST_JOINED -> ST_LOW_POWER reason=batt_low batt=3120mV
[STATE] ST_LOW_POWER -> ST_RESTART reason=batt_recovered_stable
```

## 20. Boot Sequence Produksi

**Tujuan bab:** Menetapkan urutan boot yang aman untuk board lapangan agar ESP32, radio STAR, radio MESH, power guard, cache, queue, dan parent routing masuk kondisi yang jelas sebelum operasi normal.

Prinsip boot:

- Radio U1 STAR dan U3 MESH ditahan reset saat awal boot untuk mencegah TX liar dan mengurangi risiko voltage sag.
- Radio baru diinisialisasi setelah baterai stabil `>= BATT_START_MV_DEFAULT`.
- Cache GLD dan queue MESH selalu mulai dari RAM kosong setelah restart.
- Config persisten boleh dipakai sebagai default awal, tetapi parent tetap harus dianggap valid hanya setelah discovery/validasi.
- TX MESH normal tidak boleh berjalan sebelum CH masuk `ST_JOINED`.

### 20.1 Urutan Boot Ringkas

```text
ST_BOOT
  -> setup serial, pin, watchdog, RAM runtime
  -> tahan U1/U3 reset LOW
  -> load config persisten
  -> cek baterai stabil
ST_WAIT_BATT
  -> tunggu batteryMv >= BATT_START_MV_DEFAULT beberapa sampel
ST_RADIO_INIT
  -> init SPI
  -> reset dan init U1 STAR
  -> reset dan init U3 MESH
ST_JOINING
  -> jalankan CH_CONFIG / validasi parent
ST_JOINED
  -> enqueue CH_HELLO
  -> start loop produksi
```

### 20.2 Langkah Boot Detail

| Langkah | State | Aksi | Catatan |
|---:|---|---|---|
| 1 | `ST_BOOT` | `Serial.begin(115200)`. | Cetak reset reason dari `esp_reset_reason()`. |
| 2 | `ST_BOOT` | Set `chState = ST_BOOT`, `stateSinceMs = millis()`. | State awal harus eksplisit. |
| 3 | `ST_BOOT` | Setup pin output/input. | Pin reset radio langsung diset LOW. |
| 4 | `ST_BOOT` | Tahan U1/U3 `RESET` LOW selama `RADIO_BOOT_HOLD_MS`. | Default 2000 ms, berbeda dari reset ulang radio biasa. |
| 5 | `ST_BOOT` | Init watchdog. | Default 60 detik. Feed watchdog selama boot panjang. |
| 6 | `ST_BOOT` | Init struktur RAM runtime. | `NodeCache`, `alarmQueue`, `responseQueue`, dan `helloQueue` dikosongkan. |
| 7 | `ST_BOOT` | Load config persisten. | `cluster_id`, `gateway_id`, `parent_id`, `parent_id_alt`, interval, power guard, dan radio tuning. |
| 8 | `ST_BOOT` | Validasi config. | Jika invalid, pakai default aman dan log warning. |
| 9 | `ST_WAIT_BATT` | Baca baterai berulang. | Butuh `BATT_STABLE_SAMPLES_DEFAULT` sampel dengan gap `BATT_STABLE_GAP_MS`. |
| 10 | `ST_WAIT_BATT` | Jika baterai belum stabil, tetap tahan radio reset. | Tidak ada TX radio. |
| 11 | `ST_WAIT_BATT` | Jika lockout `>= LOCKOUT_RESTART_MS`, restart. | Mencegah board diam selamanya. |
| 12 | `ST_RADIO_INIT` | Init SPI bus. | Setelah baterai stabil. |
| 13 | `ST_RADIO_INIT` | Reset U1/U3 dengan `RADIO_RESET_LOW_MS` dan `RADIO_RESET_SETTLE_MS`. | Default 300 ms LOW, lalu 500 ms settle. |
| 14 | `ST_RADIO_INIT` | Init U1 STAR. | Apply frekuensi, bandwidth, SF, CR, preamble, sync word, CRC, dan TX power Section 5. |
| 15 | `ST_RADIO_INIT` | Init U3 MESH. | Parameter sama prinsipnya dengan U1, sesuai channel MESH. |
| 16 | `ST_RADIO_INIT` | `startReceive()` U1 dan U3. | RX siap sebelum discovery parent. |
| 17 | `ST_JOINING` | Jalankan parent discovery. | Kirim `CH_CONFIG_REQUEST` dan tunggu `CH_CONFIG_RESPONSE`. |
| 18 | `ST_JOINING` | Pilih `parentId` dan `parentIdAlt`. | Gunakan kualitas link/config terbaik yang tersedia. |
| 19 | `ST_JOINED` | Enqueue `CH_HELLO`. | Memberi tahu parent bahwa CH aktif. |
| 20 | `ST_JOINED` | Masuk loop produksi. | Lanjut ke Section 21. |

### 20.3 Detail Power Saat Boot

```text
Masuk ST_WAIT_BATT:
  radio U1/U3 tetap reset LOW
  baca batteryMv
  jika batteryMv >= BATT_START_MV_DEFAULT sebanyak N sampel:
    lanjut ST_RADIO_INIT
  jika belum stabil:
    tetap tunggu, feed watchdog
  jika lockout terlalu lama:
    ST_RESTART
```

Aturan:

- `BATT_START_MV_DEFAULT` adalah syarat untuk mulai init radio, bukan syarat operasi normal.
- `BATT_RUN_MIN_MV_DEFAULT` dipakai setelah runtime untuk membatasi TX normal.
- Jika baterai drop saat boot radio, pindah kembali ke `ST_WAIT_BATT` dan tahan radio reset.
- Tidak ada `GLD_NORMAL` atau response server pull yang dikirim sebelum `ST_JOINED`.

### 20.4 Detail Init Radio

Urutan init radio harus deterministik:

1. Pastikan reset U1/U3 LOW saat awal boot.
2. Setelah baterai stabil, init SPI.
3. Reset U1/U3: LOW `RADIO_RESET_LOW_MS`, lalu release HIGH.
4. Tunggu `RADIO_RESET_SETTLE_MS`.
5. Init U1 STAR.
6. Init U3 MESH.
7. Apply parameter radio Section 5.
8. Aktifkan CRC radio dan CRC AppFrame.
9. Jalankan `startReceive()` untuk U1 dan U3.

Jika salah satu radio gagal init:

- Masuk `ST_RECOVERY`.
- Reset radio yang gagal.
- Ulang dari `ST_RADIO_INIT`.
- Queue/cache tidak perlu dihapus saat recovery.

### 20.5 Parent Discovery Saat Boot

Parent discovery dilakukan setelah U3 MESH siap.

```text
ST_JOINING:
  jika config parent tersimpan tersedia:
    gunakan sebagai kandidat awal
  kirim CH_CONFIG_REQUEST
  tunggu CH_CONFIG_RESPONSE
  pilih parent utama dan parent cadangan
  jika parent valid:
    masuk ST_JOINED
  jika belum valid:
    ulangi CH_CONFIG_REQUEST dengan jeda/backoff
```

Catatan:

- `CH_CONFIG_REQUEST` tidak memakai ACK.
- `CH_CONFIG_RESPONSE` tidak memakai ACK.
- Jika belum ada parent valid, TX queue normal tetap ditahan.
- Alarm yang masuk dari STAR saat parent belum valid boleh disimpan di `alarmQueue`, lalu dikirim setelah parent valid.
- `CH_HELLO` pertama dikirim setelah `parentId` valid.

### 20.6 Pseudocode Boot

```cpp
void boot_ch() {
  chState = ST_BOOT;
  Serial.begin(115200);
  print_reset_reason();

  setup_pins();
  hold_radios_reset_low();
  init_watchdog();
  init_runtime_ram();
  load_and_validate_config();

  chState = ST_WAIT_BATT;
  if (!wait_battery_stable()) {
    chState = ST_RESTART;
    ESP.restart();
  }

  chState = ST_RADIO_INIT;
  init_spi();
  if (!init_star_radio() || !init_mesh_radio()) {
    chState = ST_RECOVERY;
    recover_radios();
    return;
  }

  start_star_rx();
  start_mesh_rx();

  chState = ST_JOINING;
  if (!discover_parent()) {
    return;
  }

  chState = ST_JOINED;
  enqueue_ch_hello();
}
```

### 20.7 Contoh Log Boot

```text
[BOOT] reset_reason=POWERON fw=ch-24052026
[STATE] ST_BOOT -> ST_WAIT_BATT reason=boot_ready
[POWER] sample=1/8 batt=3460mV need>=3500mV
[POWER] sample=8/8 batt=3612mV need>=3500mV stable=1
[STATE] ST_WAIT_BATT -> ST_RADIO_INIT reason=battery_stable
[RADIO] boot_hold=2000ms reset_low=300ms settle=500ms
[RADIO] U1 STAR init ok freq=920.8MHz sf=7 bw=125kHz
[RADIO] U3 MESH init ok freq=923.2MHz sf=9 bw=125kHz
[STATE] ST_RADIO_INIT -> ST_JOINING reason=radio_ok
[CONFIG] tx CH_CONFIG_REQUEST cluster=0x0002
[CONFIG] parent=0x0001 alt=0x0003 rssi=-82
[STATE] ST_JOINING -> ST_JOINED reason=parent_valid
[HELLO] enqueue parent=0x0001 cluster=0x0002
```

## 21. Loop Produksi

**Tujuan bab:** Menjelaskan pola loop utama yang responsif tanpa blocking panjang.

```cpp
loop():
  esp_task_wdt_reset()
  handlePowerState()           // cek baterai, kelola ST_LOW_POWER/ST_RECOVERY
  if (f1) handleStarRx()       // ISR flag dari U1 DIO1
  if (f3) handleMeshRx()       // ISR flag dari U3 DIO1
  processMeshTxQueue()         // kirim item queue terbaik jika ada
  if (cukup_waktu) enqueueChHello()     // tiap g_helloMs
  if (cukup_waktu) doHousekeeping()     // tiap 60 detik
```

Loop tidak boleh memiliki `delay()` panjang kecuali di dalam prosedur terkontrol seperti `waitBattStable()` saat boot.

---

## 22. Housekeeping dan Cleanup

**Tujuan bab:** Menetapkan tugas pemeliharaan background yang menjaga RAM, queue, dan state tetap bersih dalam jangka panjang.

| Tugas | Interval | Fungsi |
|---|---:|---|
| Cleanup NodeCache | 60 detik | Hapus entry yang tidak aktif > CACHE_EXPIRE_MS. |
| Cleanup queue | 30 detik | Bersihkan item queue yang sudah terkirim atau tidak relevan. |
| Debug summary | 60 detik | Cetak heap, node count, queue depth, parent RSSI. |

Contoh debug summary:

```text
[HOUSEKEEP] heap=198432 nodes=12 stale=2 alarmQ=0 respQ=1 helloQ=1 par=0x006F
```

---

## 23. Format Debug Serial

**Tujuan bab:** Menetapkan prefix log agar output serial di lapangan mudah di-filter dan dianalisis.

| Prefix | Event |
|---|---|
| `[BOOT]` | Boot, reset reason, config load. |
| `[POWER]` | Battery guard, lockout, recovery. |
| `[RADIO]` | Reset/init/recovery radio. |
| `[STAR_RX]` | Frame GLD masuk. |
| `[ALARM_ACK]` | ACK compact untuk alarm dikirim/diterima. |
| `[MESH_TX]` | Frame dikirim ke parent. |
| `[MESH_RX]` | Frame dari gateway/parent masuk. |
| `[CACHE]` | Update latest cache node. |
| `[PULL]` | Server pull request. |
| `[PULL_RESP]` | Response batch data GLD normal dikirim. |
| `[CH_CONFIG]` | Parent discovery. |
| `[CH_HELLO]` | Hello topologi. |
| `[FAILOVER]` | Failover parent. |
| `[RECOVERY]` | Reset/re-init radio. |
| `[HOUSEKEEP]` | Ringkasan periodik. |
| `[WDT]` | Watchdog info. |

---

## 24. Keputusan Final Lapangan

**Tujuan bab:** Merangkum keputusan desain final sebagai checklist cepat saat implementasi firmware, pengujian protokol, dan validasi lapangan.

### 24.1 Keputusan Protokol

| Area | Keputusan final |
|---|---|
| Topologi | GLD terhubung ke CH lewat STAR. CH terhubung ke gateway lewat MESH dengan parent aktif dan `parentIdAlt` sebagai cadangan. |
| Routing MESH | Request dari server dapat membawa `hopList[]` menuju CH target. Response dari CH target kembali ke gateway melalui parent aktif. |
| AppFrame | Format compact dengan overhead tetap 10 byte: `magic`, `typeFlags`, `srcId`, `dstId`, `seq`, `payloadLen`, `payload`, `crc16`. |
| Endian | Semua integer multibyte memakai big-endian. Field 1 byte tidak punya endian. |
| CRC | Semua AppFrame memakai `CRC16-CCITT-FALSE` atas header + payload, tidak termasuk field `crc16`. |
| `typeFlags` | Bit `0..5` = `msgType`, bit `6` = `FLAG_ALARM_ACK`, bit `7` = `FLAG_GLD_EXT_POWER` (`0` Battery Mode, `1` External Power Mode pada `SENSOR_DATA`). |
| Payload STAR | Maksimum 64 byte payload, maksimum 74 byte total AppFrame. |
| Payload MESH | Maksimum 80 byte payload, maksimum 90 byte total AppFrame. |
| Data normal GLD | `GLD_NORMAL` update payload latest dan flags di `NodeCache`. Tidak langsung dikirim ke gateway. |
| Data alarm GLD | `GLD_ALARM` update payload latest dan flags, ACK alarm didahulukan, lalu masuk `alarmQueue` dan diteruskan ke parent/gateway dengan `FLAG_ALARM_ACK`. |
| Server pull | `SERVER_PULL_REQUEST` mengambil batch data GLD normal `unsent` dari cache CH target. Payload request berisi `requestId + hopList[]`, tanpa `nodeId`, `dataType`, atau `targetCluster` terpisah. |
| Pull response | `CLUSTER_DATA_RESPONSE` membawa `requestId`, `status`, `chBatteryMv`, `recordCount`, dan repeated GLD records sebanyak yang muat `MESH_MAX_PAYLOAD = 80 byte`. Tidak memakai chunk. |
| Data segar dari GLD | Server tidak bisa memaksa GLD membaca ulang. Server menunggu siklus laporan GLD berikutnya lalu melakukan pull ulang. |
| Command GLD dari server | Ada melalui `SERVER_NODE_COMMAND` ke CH target. CH menyimpan sebagai pending downlink dan tidak mengirim langsung ke GLD. |
| Downlink CH ke GLD | `NODE_DOWNLINK` membawa command tertunda dari server. Battery Mode dikirim pada RX window setelah `SENSOR_DATA`; External Power Mode boleh dikirim langsung; ACK alarm tetap didahulukan. |
| ACK | ACK hanya untuk frame alarm dengan `FLAG_ALARM_ACK`. Frame non-alarm tidak meminta ACK. |
| ACK alarm compact | Tidak punya `msgType` sendiri. Memakai `SENSOR_DATA OR FLAG_ALARM_ACK` (`0x50`) dengan payload kosong di STAR dan MESH. |
| Retry alarm | Alarm di-retry sampai `ALARM_RETRY_MAX`; `seq` tetap sama selama retry event yang sama. |
| Failover parent | Failover aktif jika alarm gagal ACK ke parent sebanyak `PARENT_FAIL_TH`. Queue tidak dihapus saat failover. |
| Queue MESH | Tiga queue RAM: `alarmQueue`, `responseQueue`, dan `helloQueue`. Pending downlink GLD disimpan terpisah per node. Urutan TX MESH: alarm, response, hello. |
| Cache GLD | Latest cache RAM-only, bukan histori. Cache menyimpan satu payload latest per node beserta `currentSeq`, `sentSeq`, `flags`, `lastSeenMs`, `lastSentMs`, dan payload asli. |
| Storage persisten | Simpan config dan parent. Jangan simpan cache, queue, atau pending downlink. |

### 24.2 Keputusan Radio, Hardware, dan Power

| Area | Keputusan final |
|---|---|
| Radio STAR | U1 / Radio A untuk GLD, frekuensi 920.0 MHz, SF7, BW 125 kHz, CR 4/5, sync word `0x12`. |
| Radio MESH | U3 / Radio B untuk backbone, frekuensi 921.0 MHz, SF9, BW 125 kHz, CR 4/5, sync word `0x34`. |
| Preamble | STAR dan MESH memakai preamble 8. |
| TCXO | Modul E22 memakai TCXO 1.6 V. |
| TX power | Default 17 dBm. Dapat dinaikkan sampai 22 dBm jika link budget membutuhkan dan baterai stabil. |
| SPI | U1 dan U3 berbagi SPI bus. Jika firmware memakai FreeRTOS, akses SPI wajib dimutex. |
| Reset radio boot | U1/U3 ditahan reset saat boot dengan `RADIO_BOOT_HOLD_MS`. |
| Reset radio recovery | Recovery radio memakai `RADIO_RESET_LOW_MS`, lalu tunggu `RADIO_RESET_SETTLE_MS`. |
| Battery ADC | `BATMON` IO4 membaca VBAT melalui divider 200k/100k, rasio 3.0, offset awal +200 mV. |
| Charger | `STAT1` IO3 dan `STAT2` IO46 membaca status BQ25185. |
| LED | LED activity di IO19, active LOW. |
| Power boot | Radio hanya diinisialisasi jika baterai stabil `>= BATT_START_MV_DEFAULT`. |
| Power runtime | Jika baterai `< batteryRunMinMv`, TX `GLD_NORMAL` dan trafik non-alarm diblok. |
| Alarm saat low power | Alarm masih boleh TX jika baterai `>= BATT_CRITICAL_TX_MIN_MV`. |
| Lockout | Jika lockout terlalu lama, board restart terkontrol agar tidak diam selamanya. |

### 24.3 Nilai Parameter 

| Parameter | Nilai final | Catatan |
|---|---:|---|
| `BATT_START_MV_DEFAULT` | 3500 mV | Syarat mulai init radio saat boot. |
| `BATT_RUN_MIN_MV_DEFAULT` | 3150 mV | Batas blok TX normal saat runtime. |
| `BATT_CRITICAL_TX_MIN_MV` | 3100 mV | Batas bawah TX alarm/kritis. |
| `BATT_STABLE_SAMPLES_DEFAULT` | 8 sampel | Jumlah sampel stabil baterai. |
| `BATT_STABLE_GAP_MS` | 1000 ms | Jarak antarsampel baterai. |
| `LOCKOUT_RESTART_MS` | 180000 ms | Restart paksa setelah lockout panjang. |
| `RADIO_BOOT_HOLD_MS` | 2000 ms | Durasi tahan reset radio saat boot. |
| `RADIO_RESET_LOW_MS` | 300 ms | Durasi reset LOW saat recovery/init ulang. |
| `RADIO_RESET_SETTLE_MS` | 500 ms | Jeda setelah reset radio dilepas. |
| `STAR_MAX_PAYLOAD` | 64 byte | Payload maksimum link STAR/GLD. |
| `MESH_MAX_PAYLOAD` | 80 byte | Payload maksimum link MESH. |
| `APPFRAME_OVERHEAD` | 10 byte | Overhead AppFrame di luar payload. |
| `NODE_CACHE_MAX` | 32 node | Jumlah GLD maksimum di cache CH. |
| `alarmQueue` | 8 item | Prioritas tertinggi. |
| `responseQueue` | 8 item | Untuk response pull dan response kritis. |
| `helloQueue` | 4 item | Untuk `CH_HELLO`. |
| `ALARM_ACK_TMO_MS` | 1500 ms | Timeout ACK compact alarm. |
| `ALARM_RETRY_MAX` | 5 kali | Retry maksimum alarm. |
| `PARENT_FAIL_TH` | 3 kali | Failover parent setelah gagal ACK alarm. |
| `NO_ACK_RECOVERY_TH` | 5 kali | Reset radio setelah no-ACK beruntun. |
| `FAILOVER_CDN_MS` | 60000 ms | Cooldown anti parent-flapping. |
| `CH_HELLO` interval | 300 detik | Hello/topology update. |

### 24.4 Checklist Implementasi

| Checklist | Wajib |
|---|---|
| Parser menolak `magic` salah, `payloadLen` melebihi batas link, `msgType` tidak dikenal, penggunaan bit 7 pada pesan non-`SENSOR_DATA`, atau CRC salah. | Ya |
| `NodeCache` memakai `currentSeq` untuk dedup frame per node. | Ya |
| `NodeCache` menyimpan satu payload latest melalui `sentSeq`, `flags`, `lastSentMs`, `payloadLen`, dan `payload[64]`. | Ya |
| Slot `NodeCache` baru menginisialisasi `sentSeq` berbeda dari `currentSeq` agar frame pertama selalu `unsent`. | Ya |
| Status `unsent` dihitung dari `currentSeq != sentSeq`; status `sent` dari `currentSeq == sentSeq`. | Ya |
| Semua field multibyte encode/decode big-endian. | Ya |
| `SERVER_PULL_REQUEST` validasi `payloadLen >= 4`, `(payloadLen - 2) % 2 == 0`, `hopCount >= 1`, dan `hopList[0] == clusterId`. | Ya |
| `SERVER_PULL_REQUEST` tidak membawa `nodeId`, `dataType`, atau `targetCluster` terpisah. | Ya |
| `seq` request tidak berubah saat forwarding dan dipakai lagi pada `CLUSTER_DATA_RESPONSE`. | Ya |
| `CLUSTER_DATA_RESPONSE` selalu membawa `requestId`, `status`, `chBatteryMv`, dan `recordCount` di header response. | Ya |
| `recordCount` valid terhadap status: `DATA_OK` wajib `recordCount > 0`, status lain wajib `recordCount = 0`. | Ya |
| Total payload `CLUSTER_DATA_RESPONSE <= 80 byte`, dan setiap record `payloadLen <= 64`. | Ya |
| Normal data dipilih dari `NodeCache` dengan aturan `unsent`, non-alarm, valid, non-stale, oldest first. | Ya |
| `FLAG_ALARM_ACK` hanya dipasang pada data alarm dan ACK alarm compact. | Ya |
| ACK alarm compact memakai `typeFlags = 0x50`, payload kosong, dan tidak dibalas lagi. | Ya |
| Frame non-alarm tidak menunggu ACK. | Ya |
| `GLD_NORMAL` hanya update cache dan tidak masuk `alarmQueue`. | Ya |
| `GLD_ALARM` mengirim ACK alarm ke GLD lebih dulu, update cache, lalu masuk `alarmQueue` dan dikirim prioritas tertinggi tanpa menunggu pull. | Ya |
| Setelah TX alarm atau response sukses, update `sentSeq = currentSeq` dan `lastSentMs = now`; jika TX gagal, `sentSeq` tidak berubah. | Ya |
| `SERVER_PULL_REQUEST` tidak meneruskan request ke GLD. | Ya |
| `SERVER_NODE_COMMAND` hanya menyimpan pending downlink di CH target. | Ya |
| `NODE_DOWNLINK` Battery Mode hanya dikirim pada RX window setelah `SENSOR_DATA`; External Power Mode boleh dikirim langsung. | Ya |
| Cache dan queue hanya RAM runtime. | Ya |
| Failover parent tidak menghapus queue. | Ya |
| Boot menahan radio reset sampai baterai stabil. | Ya |
| Loop utama tidak memakai delay panjang di luar prosedur boot/recovery terkontrol. | Ya |
| Watchdog di-feed selama proses tunggu baterai, init radio, dan parent discovery. | Ya |

### 24.5 Hal yang Masih Perlu Diputuskan

| Area | Status |
|---|---|
| Mekanisme storage persisten | Masih TO BE DISCUSSED. Kandidat utama: ESP32 Preferences / NVS namespace `chdual`. |
| Nilai final kalibrasi `BATTERY_OFFSET_MV` | Default awal +200 mV, perlu validasi pengukuran board nyata. |
| Policy detail parent scoring | Saat ini RSSI terbaik menjadi parent utama dan kandidat kedua menjadi `parentIdAlt`; scoring tambahan dapat ditambahkan setelah uji lapangan. |
| Policy pending downlink GLD | Overwrite/drop untuk command baru saat masih ada command lama masih TO BE DISCUSSED. |
