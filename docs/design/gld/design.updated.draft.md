# Gas Leak Detector - Firmware Design Document

**Document version:** v1.8.19  
**Project:** Gas Leak Detector Firmware  
**Target MCU:** ESP32-S3  
**Scope:** Firmware-centric design document for `Sensor Node`, focusing on behavior, interfaces, and signals visible to `ESP32-S3`.

**Source Alias:** `DESIGN_v1_3.md` = `BaseDesign`, `designApply.md` = `FieldReference`

**Document Convention:** `BaseDesign` menjadi prioritas isi utama. `FieldReference` dipakai hanya untuk perilaku runtime tervalidasi, konteks migrasi, atau konflik yang perlu disebut eksplisit.

**Updated Draft Note 2026-06-15:** File ini adalah versi updated draft dari `design.md`. File original tidak diubah. Jika isi historis di bawah bertentangan dengan dokumen berikut, keputusan updated draft ini mengikuti:

- `docs/design/gld-ch/payload-contract.draft.md`
- `docs/firmware/01-gld-reference-traceability.draft.md`
- `docs/firmware/02-gld-3-stage-plan.draft.md`
- `docs/firmware/03-phase-1-plan.draft.md`

Ringkasan override utama:

- Running LoRa payload GLD adalah plaintext 4 byte (`gasClass`, `confidence`, `batteryMv`) yang dienkripsi AES-128-GCM menjadi payload 29 byte.
- Format LoRa lama `NORMAL`, `ALARM`, `HEALTH`, `sensorMv[8]`, raw sensor, health/status internal, nulling snapshot, dan dataset data tidak masuk running LoRa.
- Alarm running ditentukan oleh `gasClass != clearGas && confidence >= GLD_LEL_THRESHOLD_PERCENT`; default awal threshold adalah `30`.
- Dataset hanya berjalan di external power, tidak menjalankan nulling otomatis sebelum start, dan wajib memakai active `nulling_profile_id`.
- Dataset record memakai `sensor_voltage[8]` dari `movingAverageVoltage` / `voltage_after_gain_compensation`, `sensor_gain[8]`, dan canonical `feature_order`.
- `mappingChannel`, `power_mode`, dan `nulling_profile_version` tidak menjadi field dataset record final.
- Nulling profile memakai satu ID monotonic: setiap nulling sukses menaikkan `nullingProfileId`; dataset/model lama untuk profile sebelumnya tidak valid untuk running production.
- Running production diblok jika active `nullingProfileId` tidak cocok dengan `boundNullingProfileId` pada metadata model.
- Downlink command penuh lewat LoRa ditahan untuk phase berikutnya; phase awal hanya membutuhkan ACK alarm compact.

---

## 1. Project Overview 

### 1.1 Tujuan Proyek 

Firmware ini dibuat untuk mendeteksi indikasi kebocoran gas menggunakan **8 jenis sensor MQ**. Sistem membaca sensor secara berkala, melakukan nulling, filtering, automatic gain control, kalibrasi, dan feature extraction, lalu menerapkan **inferensi model AI** yang sebelumnya sudah dibangun.

Apabila hasil inferensi menunjukkan kondisi berbahaya atau alarm, firmware mengaktifkan **alarm visual berupa lampu** dan **alarm suara berupa buzzer**. Selain itu, hasil inferensi model AI dan status perangkat dikirimkan melalui **LoRa**.

Firmware juga dirancang untuk mendukung:

- **Nulling / Setup Calibration Service**
- **Dataset Generation Stage**, dikendalikan melalui MQTT saat mode external power
- **Inference Stage**
- **Modbus RTU Slave** melalui RS485 agar perangkat eksternal dapat membaca status board
- **Power source / power mode detection** berdasarkan 24V power-good dan battery monitor
- **Battery inference mode** menggunakan TPL5110 power gating

### 1.2 System Overview 

```text
8x MQ Sensor Bridge
        ->
INA333 Instrumentation Amplifier, gain 1x, per channel
        ->
ADS1256 24-bit ADC, 8-channel single-ended
        ->
ESP32-S3
        ->
Filtering + Calibration + Feature Preparation
        ->
NeuralNetwork / tfmicro Inference
        ->
Alarm Lamp + Buzzer + LoRa Transmission
```

Nulling path:

```text
ESP32-S3
   -> I2C
TCA9548A I2C Multiplexer
   ->
8x MCP4725 DAC
   ->
8x LM321 (REF-buffer: MCP4725 DAC output -> INA333 REF pin, auto-nulling path)
   ->
INA333 REF offset-control path
```

Power path:

```text
External 24VDC -> Buck Converter -> 5V Rail

Lithium Battery -> TPL5110 -> Boost Converter -> 5V Rail
```

---

## 2. Scope and Goals 

### 2.1 In Scope 

- Desain firmware ESP32-S3 untuk gas leak detector dengan 8-channel MQ sensor array
- Interface hardware yang diakses firmware pada board target
- Auto-nulling per channel via MCP4725 DAC melalui TCA9548A I2C mux
- Pipeline akuisisi sinyal dari sudut pandang firmware
- Klasifikasi pola gas menggunakan model `NeuralNetwork` dengan runtime `tfmicro`
- Telemetri hasil inferensi via LoRa
- Dataset Generation Stage via Wi-Fi + MQTT
- Modbus RTU Slave via RS-485
- Monitoring tegangan baterai dan manajemen daya

### 2.2 Out of Scope 
Source: BaseDesign.

- Cloud backend atau dashboard monitoring
- Training model AI di device
- Firmware untuk perangkat selain node sensor

### 2.3 Goals 

- Mengadopsi pinout dan signal map board target dari sudut pandang firmware
- Meniru perilaku `Sensor Node` yang telah berhasil di lapangan
- Menjaga konsistensi antara hardware mapping, acquisition flow, calibration flow, dan inference flow

---

## 3. Hardware Decision 

### 3.1 Hardware Summary 
Source: BaseDesign.

| Komponen | Spesifikasi |
|---|---|
| MCU | ESP32-S3-WROOM-1U-N16R8 / ESP32-S3 class target |
| Gas sensors | MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2 (board channel order) |
| ADC | ADS1256, 24-bit, 8-channel, single-ended |
| ADS1256 VREF | 2.497V precision reference |
| ADS1256 PGA gain | 1x, 2x, 4x, 8x, 16x, 32x, 64x |
| Amplifier | INA333 instrumentation amplifier per sensor channel |
| INA333 gain | 1x |
| REF buffer | LM321 per sensor channel, buffering MCP4725 output to INA333 REF |
| DAC | MCP4725 12-bit DAC per sensor channel |
| DAC access | Through TCA9548A I2C multiplexer |
| LoRa module | E22-900MM22S / SX1262-class RadioLib target |
| LoRa library | RadioLib |
| RS485 driver | THVD1410DR |
| Output driver | ULN2003 |
| Modbus role | Modbus RTU Slave |
| AI runtime | NeuralNetwork + tfmicro |
| Power | 24VDC external or lithium battery |

Catatan:
Ringkasan ini hanya memuat komponen yang langsung memengaruhi firmware; detail wiring, layout, dan PCB tidak dibahas di sini.

> Firmware target harus dibangun dengan asumsi memori `ESP32-S3-WROOM-1U-N16R8`, yaitu `16MB Flash` dan `8MB PSRAM`. Profil memori build yang tidak sesuai dapat menyebabkan boot failure sebelum aplikasi masuk ke `setup()`.

### 3.2 Hardware Topology from ESP32-S3 Perspective
Source: BaseDesign.

```text
ESP32-S3
+-- ADS1256
|   +-- AIN0..AIN7
|       +-- 8x analog sensor path
|           +-- INA333 per channel
|           +-- MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
+-- TCA9548A
|   +-- CH0..CH7
|       +-- 8x MCP4725
|           +-- 8x LM321 (REF-buffer: MCP4725 DAC output -> INA333 REF pin)
|               +-- INA333 REF offset-control path per sensor channel
+-- E22-900MM22S / SX1262
|   +-- LoRa RF uplink path
+-- THVD1410DR
|   +-- RS485 / Modbus RTU bus
+-- ULN2003
|   +-- Alarm Lamp / Buzzer / Fan driver path
+-- TPL5110
    +-- battery power-cycle control
```

Topologi ini menunjukkan hubungan koneksi dan dependency hardware dari sudut pandang firmware: `ESP32-S3` adalah root, IC yang terhubung langsung ke `ESP32-S3` berada pada level kedua, dan jalur turunan atau subsystem berada di bawah parent yang relevan.

### 3.3 Sensor List 
Source: BaseDesign.

| Channel | Sensor | Fungsi Umum |
|---:|---|---|
| 0 | MQ8 | Hydrogen |
| 1 | MQ135 | Air quality, benzene, smoke, VOC |
| 2 | MQ3 | Alcohol, ethanol, VOC |
| 3 | MQ5 | Natural gas, LPG |
| 4 | MQ4 | Methane, CNG |
| 5 | MQ7 | Carbon monoxide |
| 6 | MQ6 | LPG, butane |
| 7 | MQ2 | LPG, methane, propane, smoke |

Klasifikasi utama dilakukan oleh model AI berdasarkan pola respons 8 sensor, bukan rule-based per sensor.

### 3.4 Physical Sensor Channel Mapping 
Source: BaseDesign.

Firmware memakai mapping ini sebagai sumber utama hubungan `channel -> ADC input -> DAC nulling`. Untuk board ini, referensi authoritative adalah `D:\GLD\GLD\test_device.md`.

| Posisi Board | Sensor Channel | MQ Sensor | TCA9548A CH (DAC) | ADS1256 Input |
|---:|---:|---|---:|---|
| 1 | CH0 | MQ8 | 7 | AIN0 |
| 2 | CH1 | MQ135 | 6 | AIN1 |
| 3 | CH2 | MQ3 | 5 | AIN2 |
| 4 | CH3 | MQ5 | 4 | AIN3 |
| 5 | CH4 | MQ4 | 3 | AIN4 |
| 6 | CH5 | MQ7 | 2 | AIN5 |
| 7 | CH6 | MQ6 | 0 | AIN6 |
| 8 | CH7 | MQ2 | 1 | AIN7 |

Catatan:
Urutan `Sensor Channel`, `ADS1256 Input`, dan `feature index` dibuat lurus; hanya mapping `TCA9548A CH (DAC)` yang tidak lurus sehingga nulling harus selalu mengikuti tabel ini.

---

## 4. Key IC Roles

### 4.1 ESP32-S3
Source: BaseDesign.

- Peran: root controller yang menjalankan acquisition, nulling, inference, LoRa, Modbus, dan power handling
- Interface utama: `GPIO(ADS1256(DRDY,SYNC/PDWN), LORA(BUSY,DIO1,RST,RXEN,TXEN), ULN2003(Alarm-Lamp,Buzzer,Fan), TPL5110(DONE), POWER(BATMON,PG24), RS485(DIR), BOARD(Status-LED))`, `I2C(SDA, SCL)`, `SPI(MOSI, SCK, MISO, CS)`, `UART(RX, TX, DIR)`, `Wi-Fi(internal)`
- Library used: `none(Arduino core / framework-managed)`

#### 4.1.1 ADS1256
Source: BaseDesign + FieldReference.

- Peran: ADC utama 8 channel sensor yang menjadi titik akuisisi analog sistem, menyediakan `raw ADC count` untuk firmware, menjadi basis konversi count-to-voltage, dan menyediakan `PGA gain` untuk `automatic gain`
- Interface utama: `SPI(SCK, MOSI, MISO, CS)`, `GPIO(DRDY, SYNC/PDWN)`, `Analog(AIN0..AIN7)`
- Fungsi operasional: membaca `AIN0..AIN7`, menyediakan `raw ADC count`, melakukan `convertToVoltage()`, dan mendukung pengaturan `PGA gain` untuk `automatic gain`
- Alur kerja wajib menurut runtime reference `(field approved)`:

**Startup ADS**

| Step | Operasi | Keterangan | Contoh call |
|---|---|---|---|
| 1 | Start SPI ADS | Mulai bus `SPI_ADS` khusus untuk ADS1256 | `SPI_ADS.begin(PIN_SCK_ADS, PIN_MISO_ADS, PIN_MOSI_ADS, PIN_CS_ADS);` |
| 2 | Setup pin kontrol | Set `DRDY`, `SYNC/PDWN`, dan `CS`; lalu idle-kan `CS` ke `HIGH` | `pinMode(PIN_DRDY, INPUT); pinMode(PIN_SYNC, OUTPUT); digitalWrite(PIN_CS_ADS, HIGH);` |
| 3 | Control reset via `SYNC/PDWN` | Sebelum inisialisasi, firmware memberi pulse kontrol pada `SYNC/PDWN` karena board ini tidak mengekspos pin `RESET` terpisah | `digitalWrite(PIN_SYNC, LOW); delay(100); digitalWrite(PIN_SYNC, HIGH); delay(100);` |
| 4 | Initialize dan verifikasi | Jalankan init ADC, baca register ID, lalu validasi device | `A.InitializeADC(); checkADS1256();` |
| 5 | Set konfigurasi dasar | Terapkan `PGA_SETTING` dan `DRATE_SETTING` untuk mode awal | `A.setPGA(PGA_SETTING); A.setDRATE(DRATE_SETTING);` |

**Runtime per channel**

| Step | Operasi | Keterangan | Contoh call |
|---|---|---|---|
| 1 | AGC per channel | Pilih MUX channel, baca `raw`, ubah ke voltage absolut, lalu tentukan gain yang sesuai | `A.setMUX(SING_0 + (channel * 16)); long raw = A.readSingle(); float absVolt = abs(A.convertToVoltage(raw));` |
| 2 | Apply gain baru bila berubah | Jika gain channel berubah, update PGA, tunggu stabil, lalu flush satu bacaan | `A.setPGA(pga_settings[pgaValues[channel]]); delay(20); A.readSingle();` |
| 3 | Akuisisi channel normal | Pilih MUX channel, buang bacaan pertama, baca `raw` valid, lalu konversi ke voltage | `A.setMUX(SING_0 + (ch * 16)); A.readSingle(); long raw = A.readSingle(); float voltage = A.convertToVoltage(raw);` |

**Full scan 8 channel**

| Step | Operasi | Keterangan | Contoh call |
|---|---|---|---|
| 1 | Loop 8 channel | Ulangi pembacaan untuk `chs=0..7` | `for (uint8_t chs = 0; chs < 8; chs++) { ... }` |
| 2 | Akuisisi per iterasi | Pada setiap iterasi, jalankan pola `setMUX -> buang pertama -> baca valid -> convertToVoltage` | `A.setMUX(SING_0 + (chs * 16)); A.readSingle(); adcValues[chs] = A.readSingle(); voltValues[chs] = A.convertToVoltage(adcValues[chs]);` |

> Poin yang paling wajib dari runtime reference adalah: pilih `MUX` per channel; `ADS1256-main` memberi `delay(10)` internal di `setMUX()`; setelah itu firmware membuang bacaan pertama sebagai `flush read`, memakai `raw ADC count` kedua sebagai data valid, lalu mengonversinya ke voltage. `Automatic gain` juga diterapkan per channel melalui `gainCalibrate(channel)`. `(field approved)`
- Library used: `ADS1256-main` `(field approved)`

#### 4.1.2 TCA9548A
Source: BaseDesign + FieldReference.

- Peran: mux I2C utama untuk memilih satu jalur DAC nulling aktif pada satu waktu
- Interface utama: `I2C(SDA, SCL)`, `ADDR(0x71)`, `MUX-CH(0..7)`
- Fungsi operasional: memilih channel `MCP4725` yang aktif karena semua DAC berbagi alamat I2C yang sama
- Alur kerja wajib menurut runtime reference `(field approved)`:

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Startup | Mulai `Wire`, lalu deteksi `TCA9548A` di alamat `0x71` | `Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN); if (!mux.begin()) { ... }` |
| Select channel | Sebelum akses DAC, firmware memilih satu channel mux yang aktif | `mux.selectChannel(ch);` |

> Poin yang paling wajib dari runtime reference adalah: semua DAC berada di alamat I2C yang sama, jadi firmware harus selalu `selectChannel()` lebih dulu. Tanpa pemilihan channel ini, akses DAC tidak akan terarah ke sensor yang dimaksud. `(field approved)`
- Library used: `TCA9548-master` `(field approved)`

Catatan: alamat authoritative untuk board ini adalah `0x71` sesuai `D:\GLD\GLD\test_device.md`.

#### 4.1.2.1 MCP4725
Source: BaseDesign + FieldReference.

- Peran: DAC per channel untuk nulling
- Interface utama: `I2C(SDA, SCL, 0x60)`, `MUX-CH(CH0..CH7)`
- Fungsi operasional: menghasilkan tegangan DAC yang kemudian dibuffer oleh `LM321` sebelum masuk ke pin `INA333 REF`, dan menerima write DAC setelah channel mux dipilih
- Alur kerja wajib menurut runtime reference `(field approved)`:

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Write satu channel | Setelah mux memilih channel aktif, firmware memulai akses DAC lalu menulis nilai baru | `dac.begin(); dac.setValue(wiperArr[ch]);` |

> Poin yang paling wajib dari runtime reference adalah: MCP4725 tidak memilih channel sendiri; dia hanya menerima write DAC pada channel yang sudah lebih dulu dipilih oleh `TCA9548A`. Setelah channel aktif, firmware memakai `dac.begin()` lalu `dac.setValue(...)` untuk menerapkan nilai DAC pada channel itu, dan nilai tersebut kemudian dibuffer oleh `LM321` sebelum masuk ke pin `INA333 REF`. `(field approved)`
- Library used: `MCP4725-master` `(field approved)`

#### 4.1.3 E22-900MM22S / SX1262
Source: BaseDesign + FieldReference.

- Peran: radio LoRa untuk uplink hasil inferensi dan penerimaan command / packet node
- Interface utama: `SPI(SCK, MOSI, MISO, CS/NSS)`, `GPIO(BUSY, DIO1, RST, RXEN, TXEN)`
- Fungsi operasional: menginisialisasi radio, masuk ke mode receive, mengirim payload saat diminta, lalu kembali ke mode receive dengan pola runtime non-blocking
- Parameter `radio.begin(...)` pada startup LoRa:

| Parameter | Nilai runtime reference | Makna |
|---|---|---|
| Frequency | `id.loraFreq` | frekuensi kerja LoRa per board / deployment |
| Bandwidth | `125.0` | bandwidth LoRa `125 kHz` |
| Spreading Factor | `9` | `SF9` |
| Coding Rate | `7` | coding rate yang dipakai runtime reference |
| Sync Word | `RADIOLIB_SX127X_SYNC_WORD` | sync word radio untuk jaringan LoRa node |
| Output Power | `17` | daya pancar `17 dBm` |
| Preamble Length | `8` | panjang preamble packet |
| TCXO voltage | `1.6` | argumen `tcxoVoltage` default RadioLib SX1262 |

> Catatan: `radio.begin()` pada SX1262 (RadioLib) memiliki signature `begin(freq, bw, sf, cr, syncWord, power, preambleLength, tcxoVoltage)`. Argumen ke-8 adalah `tcxoVoltage`, bukan `gain`. Ini berbeda dari SX127x yang memakai `gain` sebagai argumen terakhir.

- Alur kerja wajib menurut runtime reference `(field approved)`:

**Startup LoRa**

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Startup LoRa | Mulai SPI, inisialisasi radio dengan frekuensi / bandwidth / SF / CR target | `radio.begin(id.loraFreq, 125.0, 9, 7, 0x12, 17, 8);` |
| Register interrupt | Hubungkan `DIO1` ke handler yang akan set `operationDone = true` saat operasi radio selesai | `radio.setDio1Action(LoRaInterruptHandler);` |
| Masuk receive mode | Setelah init berhasil, radio langsung diset untuk menerima packet | `radio.startReceive();` |

**Saat menerima data**

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Operation done by ISR | Saat operasi receive selesai dan `DIO1` memicu interrupt, handler hanya menandai `operationDone = true` | `void LoRaInterruptHandler() { operationDone = true; }` |
| Classify receive event | Loop utama mendeteksi `operationDone == true` dan `transmitFlag == false`, sehingga event diperlakukan sebagai receive selesai | `if (operationDone && !transmitFlag) { ... }` |
| Read packet | Saat packet diterima, firmware membaca panjang packet lalu mengambil isi data radio | `uint8_t length = radio.getPacketLength(); int len = radio.readData(buffer, length);` |
| Process packet | Firmware deserialize payload, baca RSSI/SNR/frequency error, lalu proses sesuai tujuan packet | `deserializeMessage(buffer, length, &receivedData);` |

**Saat transmit data**

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Trigger transmit | Saat `sendSta` aktif atau interval kirim terpenuhi, firmware menyiapkan payload kirim | `prepareDataToSend();` |
| Start transmit | Firmware memanggil `startTransmit()` lebih dulu; jika start kirim berhasil, baru `transmitFlag = true` | `int state = radio.startTransmit(buffer, len); if (state == RADIOLIB_ERR_NONE) { transmitFlag = true; }` |
| Operation done by ISR | Saat transmit selesai dan `DIO1` memicu interrupt, handler hanya menandai `operationDone = true` | `void LoRaInterruptHandler() { operationDone = true; }` |
| Mark transmit done | Loop utama mendeteksi `operationDone == true` dan `transmitFlag == true`, sehingga event diperlakukan sebagai transmit selesai | `if (operationDone && transmitFlag) { ... }` |
| Clear transmit flag | Setelah dipastikan transmit selesai, firmware membersihkan `transmitFlag` | `transmitFlag = false;` |
| Buka receive window | Setelah transmit selesai, radio dikembalikan ke receive mode untuk membuka receive window singkat default `2000 ms` | `radio.startReceive();` |
| Terima ACK / command | Selama receive window default `2000 ms`, firmware dapat menerima ACK atau command downlink dari server sebelum siklus battery berakhir | `if (operationDone && !transmitFlag) { radio.readData(buffer, length); }` |

Catatan: runtime radio memakai pola non-blocking; radio dijaga di receive mode, transmit dipicu saat perlu, dan `transmitFlag` hanya boleh aktif jika `startTransmit()` benar-benar berhasil dimulai. Pada battery mode, receive mode setelah transmit juga berfungsi sebagai receive window singkat default `2000 ms` untuk ACK atau command downlink sebelum node sleep lagi.

Catatan interrupt: `operationDone` hanya menandakan bahwa operasi radio aktif telah selesai. Firmware lalu memeriksa `transmitFlag` untuk membedakan apakah event yang selesai adalah `transmit` atau `receive`.

> Poin yang paling wajib dari runtime reference adalah: radio di-start dalam receive mode, transmit hanya dipicu saat ada request / interval, lalu setelah transmit selesai radio kembali lagi ke receive mode untuk menerima ACK atau command downlink sebelum siklus battery diakhiri. `(field approved)`
- Library used: `RadioLib` `(field approved)`

#### 4.1.4 THVD1410DR
Source: BaseDesign.

- Peran: transceiver RS485 half-duplex yang menghubungkan UART node ke bus Modbus RTU slave eksternal
- Interface utama: `UART(TX, RX)`, `GPIO(DIR)`
- Fungsi operasional: menjaga node tetap pada mode receive saat idle, lalu mengalihkan arah bus ke transmit hanya saat slave perlu mengirim balasan Modbus
- Alur kerja target design:

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Startup RS485 | Inisialisasi UART Modbus dengan `9600 8N1`, lalu set direction default ke receive | `Serial2.begin(9600, SERIAL_8N1, PIN_RS485_RX, PIN_RS485_TX); digitalWrite(PIN_RS485_DIR, LOW);` |
| Listen request | Saat idle, transceiver tetap pada mode receive agar node bisa membaca query dari Modbus master | `digitalWrite(PIN_RS485_DIR, LOW);` |
| Send response | Saat slave perlu mengirim balasan, set `DIR` ke transmit, kirim frame, tunggu kirim selesai, lalu kembalikan ke receive | `digitalWrite(PIN_RS485_DIR, HIGH); Serial2.write(frame, len); Serial2.flush(); digitalWrite(PIN_RS485_DIR, LOW);` |

Catatan: karakter utama THVD1410DR pada desain ini adalah half-duplex direction control. Default aman adalah receive; mode transmit hanya aktif selama pengiriman balasan slave berlangsung.

Catatan: detail `register address map`, `command register`, dan `command code` Modbus didokumentasikan di `Section 12.4` dan `Section 12.5`.
- Library used: `none(Arduino UART / RS485 flow)`

#### 4.1.5 TPL5110
Source: BaseDesign.

- Peran: timer / power gate untuk battery mode
- Interface utama: `GPIO(DONE)`
- Fungsi operasional: membangunkan node secara periodik pada battery mode, membiarkan firmware menjalankan satu siklus kerja singkat, lalu mematikan lagi daya setelah menerima sinyal `DONE`
- Alur kerja target design:

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Wake by timer | TPL5110 menghidupkan rail battery path dan memulai satu wake cycle firmware | `battery wake cycle started by hardware timer` |
| Run one-shot task | Firmware menjalankan siklus singkat battery mode: power check, load config, inference, LoRa transmit, lalu receive window bila diperlukan | `runBatteryInferenceCycle();` |
| Pulse DONE | Setelah siklus selesai, atau saat error / config invalid menghentikan siklus lebih awal, firmware memberi pulse `DONE` ke TPL5110 | `digitalWrite(PIN_TPL5110_DONE, HIGH); delay(TPL5110_DONE_PULSE_MS); digitalWrite(PIN_TPL5110_DONE, LOW);` |

Urutan kejadian battery mode:

1. TPL5110 berada pada kondisi sleep dan node tidak aktif.
2. Saat timer hardware mencapai interval wake, TPL5110 menyalakan rail dan node mulai boot.
3. ESP32 menjalankan satu siklus kerja singkat battery mode.
4. Setelah inference, LoRa transmit, dan receive window selesai, atau saat siklus dihentikan oleh error / config invalid, firmware memberi pulse `DONE`.
5. Setelah `DONE` diterima TPL5110, siklus aktif berakhir dan node kembali ke kondisi sleep.

Catatan: karakter utama TPL5110 pada desain ini adalah hardware-controlled wake cycle, bukan scheduler firmware berulang. Setelah `DONE` dipulse, node diasumsikan keluar dari siklus aktif battery mode.
- Library used: `none(GPIO-based power control)`

Catatan: IC ini hanya relevan untuk `BaseDesign`; `FieldReference` tidak merepresentasikan board dengan `battery mode`.

#### 4.1.6 ULN2003
Source: BaseDesign.

- Peran: output driver untuk beban board yang tidak digerakkan langsung oleh ESP32
- Interface utama: `GPIO(IN1..INn)`, `Driver-OUT(Alarm-Lamp, Buzzer, Fan)`
- Fungsi operasional: menerima kontrol digital dari ESP32 lalu menggerakkan output board melalui jalur transistor array sebagai low-side driver
- Alasan digunakan, bukan GPIO langsung:

| Alasan | Penjelasan |
|---|---|
| Arus beban | `Alarm-Lamp`, `Buzzer`, dan `Fan` adalah beban output yang dapat membutuhkan arus lebih besar daripada yang aman bila didorong langsung dari GPIO ESP32 |
| Switching driver | ULN2003 menyediakan jalur transistor sink/driver sehingga GPIO cukup memberi sinyal kontrol kecil, bukan arus beban utama |
| Isolasi beban | Beban output tidak langsung dibebankan ke pin MCU, sehingga risiko stress pada GPIO lebih kecil |
| Kesesuaian beban board | Untuk output seperti lamp, buzzer, dan fan, pola driver transistor array lebih cocok daripada output logic langsung |

- Alur kerja target design:

| Flow | Inti langkah | Contoh call |
|---|---|---|
| Set output command | ESP32 mengubah GPIO kontrol sesuai status alarm atau kebutuhan runtime | `digitalWrite(PIN_ALARM_LAMP, HIGH);` |
| ULN2003 drive load | Sinyal GPIO masuk ke input ULN2003 lalu driver men-switch beban board terkait | `ULN2003 input follows GPIO state` |
| Release load | Saat status output tidak diperlukan lagi, GPIO dimatikan dan ULN2003 melepas beban | `digitalWrite(PIN_ALARM_LAMP, LOW);` |

Catatan: pada board ini, `Status-LED` bukan jalur ULN2003; yang melewati ULN2003 adalah `Alarm-Lamp`, `Buzzer`, dan `Fan`.
- Library used: `none(GPIO-based output driver)`

---

## 5. Pin Assignments 

Catatan: section ini adalah `firmware pin map`, bukan referensi wiring fisik board.

### 5.1 I2C Bus 
Source: BaseDesign.

| Signal | ESP32-S3 Pin | Connected Device | Notes |
|---|---:|---|---|
| SDA | GPIO8 | TCA9548A | I2C data |
| SCL | GPIO9 | TCA9548A | I2C clock |

### 5.2 SPI Bus 
Source: BaseDesign.

| Signal | ESP32-S3 Pin | Connected Device | Notes |
|---|---:|---|---|
| SPI SCK | GPIO12 | ADS1256 + LoRa | Shared SPI clock |
| SPI MOSI | GPIO11 | ADS1256 + LoRa | Shared SPI MOSI |
| SPI MISO | GPIO13 | ADS1256 + LoRa | Shared SPI MISO |
| CS ADS1256 | GPIO47 | ADS1256 | ADC chip select |
| CS LoRa | GPIO15 | LoRa | LoRa chip select |

Shared SPI rule:

```text
- Hanya satu device boleh aktif pada satu waktu.
- Sebelum akses ADS1256, CS LoRa harus HIGH.
- Sebelum akses LoRa, CS ADS1256 harus HIGH.
```

### 5.3 ADS1256 Pin Assignment 
Source: BaseDesign.

| ADS1256 Signal | ESP32-S3 Pin | Direction | Notes |
|---|---:|---|---|
| SCK | GPIO12 | Output | Shared SPI |
| DIN / MOSI | GPIO11 | Output | Shared SPI |
| DOUT / MISO | GPIO13 | Input | Shared SPI |
| CS | GPIO47 | Output | Dedicated ADC CS |
| DRDY | GPIO10 | Input | Data ready signal |
| SYNC / PDWN | GPIO18 | Output | ADC sync / power-down control |

### 5.4 LoRa Pin Assignment 
Source: BaseDesign.

| LoRa Signal | ESP32-S3 Pin | Direction | Notes |
|---|---:|---|---|
| SCK | GPIO12 | Output | Shared SPI |
| MOSI | GPIO11 | Output | Shared SPI |
| MISO | GPIO13 | Input | Shared SPI |
| CS / NSS | GPIO15 | Output | Dedicated LoRa CS |
| RST | GPIO39 | Output | LoRa reset |
| BUSY | GPIO7 | Input | LoRa busy status |
| TXEN | GPIO6 | Output | RF transmit enable |
| RXEN | GPIO5 | Output | RF receive enable |
| DIO1 | GPIO40 | Input | LoRa interrupt |

### 5.5 Digital Output and Utility Pins 
Source: BaseDesign.

| Function | ESP32-S3 Pin | Direction | Notes |
|---|---:|---|---|
| Status LED | GPIO41 | Output | Target design active high |
| Alarm Lamp | GPIO1 | Output | Target design active high |
| Buzzer | GPIO2 | Output | Target design active high |
| DC Fan | GPIO42 | Output | Target design active high |
| TPL5110 DONE | GPIO14 | Output | Power timer handshake |
| Battery Monitor | GPIO4 | Analog input | ADC battery measurement |
| 24V Power Good | GPIO45 | Digital input | Power-good input |
| Config Input | GPIO16 | Digital input | Active low |

### 5.6 RS485 / Modbus Pins 
Source: BaseDesign.

| Signal | ESP32-S3 Pin | Direction | Function |
|---|---:|---|---|
| RO / RX | GPIO20 | Input | RS485 receive |
| DI / TX | GPIO21 | Output | RS485 transmit |
| RE + DE | GPIO19 | Output | Direction control |

### 5.7 `board_pins.h` Direction
Source: BaseDesign.

Konstanta pin dasar yang harus dianggap sebagai target design:

```cpp
#define PIN_SPI_SCK          12
#define PIN_SPI_MOSI         11
#define PIN_SPI_MISO         13
#define PIN_ADS1256_CS       47
#define PIN_ADS1256_DRDY     10
#define PIN_ADS1256_SYNC     18
#define PIN_LORA_CS          15
#define PIN_LORA_RST         39
#define PIN_LORA_BUSY        7
#define PIN_LORA_TXEN        6
#define PIN_LORA_RXEN        5
#define PIN_LORA_DIO1        40
#define PIN_I2C_SDA          8
#define PIN_I2C_SCL          9
#define PIN_STATUS_LED       41
#define PIN_ALARM_LAMP       1
#define PIN_BUZZER           2
#define PIN_DC_FAN           42
#define PIN_USER_BUTTON      16
#define PIN_TPL5110_DONE     14
#define PIN_BATTERY_VOLTAGE  4
#define PIN_24V_POWER_GOOD   45
#define PIN_RS485_RX         20
#define PIN_RS485_TX         21
#define PIN_RS485_DIR        19
```

---

## 6. Firmware Operation Stages 

Section ini menegaskan bahwa firmware berjalan sebagai stage machine operasional, bukan sekadar loop polling tunggal. Setiap stage memiliki trigger masuk, izin jalan, dan output yang berbeda. 

Firmware memiliki dua stage runtime utama dan satu service prasyarat. 

```text
1. Nulling Service / Setup Calibration
2. Dataset Generation Stage
3. Inference Stage
```

| Stage | Tujuan | Output Utama |
|---|---|---|
| Nulling Service / Setup Calibration | Menentukan DAC nulling code per sensor channel agar stage lain dapat membaca sensor dengan valid | Nulling profile |
| Dataset Generation Stage | Mengambil data sensor untuk dataset training/validasi AI | Dataset rows via MQTT |
| Inference Stage | Menjalankan model `NeuralNetwork` dengan runtime `tfmicro` untuk deteksi gas | Label, confidence, alarm, LoRa packet |

Runtime equivalence. 

| Stage | Runtime Mode |
|---|---|
| Nulling Service / Setup Calibration | `SETUP` |
| Dataset Generation Stage | `TRAINING` |
| Inference Stage | `RUNNING` |

Catatan:
- `Stage` dipakai untuk arsitektur
- `Mode` dipakai untuk runtime referensi lapangan
- pemetaan di atas bersifat operasional, bukan identitas satu banding satu
- `SETUP CALIBRATION` diperlakukan sebagai aktivitas di dalam runtime mode `SETUP`
- nulling bukan mode runtime jangka panjang; nulling adalah service transien yang harus sudah pernah berhasil dijalankan sebelum `Dataset` atau `Inference` memakai nilai sensor sebagai data valid
- setelah `NullingProfile` tersedia dan valid, stage lain boleh memakai hasilnya sampai profile perlu diperbarui

### 6.1 Nulling / Setup Calibration 

#### 6.1.1 Tujuan 
Source: BaseDesign.

Nulling stage digunakan untuk menentukan **nilai DAC minimum** yang mulai menghasilkan perubahan pembacaan ADC pada setiap channel sensor.

Flow stage nulling:

| Langkah | Nama Flow | Keterangan |
|---|---|---|
| 1 | Validate Power | Pastikan node berada pada external power dan nulling diizinkan |
| 2 | Select Channel | Pilih channel sensor dan channel mux yang sesuai |
| 3 | Read Baseline | Set DAC awal lalu baca ADC baseline |
| 4 | Search Transition | Jalankan exponential search dan binary search untuk mencari titik perubahan pertama |
| 5 | Confirm Result | Validasi kandidat DAC dengan pengecekan around-result |
| 6 | Store Validated Channel Result | Simpan hasil DAC valid untuk channel aktif ke `NullingProfile` / `wiperArr`, lalu commit ke EEPROM |
| 7 | Finalize Full Profile | Setelah semua channel selesai, tandai profile siap dipakai oleh stage lain |

#### 6.1.2 Power Policy 

Power policy nulling ditetapkan sebagai berikut. 
```text
External 24VDC mode : allowed
Battery mode        : not allowed
```

#### 6.1.3 Algoritma Nulling yang Dipakai

Ringkasan algoritma:

```text
1. Set ADC gain nulling = tinggi / fixed nulling gain.
2. Set DAC = 0.
3. Baca ADC awal sebagai baseline.
4. Lakukan exponential search untuk menemukan range transisi.
5. Lakukan binary search untuk menemukan DAC code pertama yang memicu perubahan ADC.
6. Lakukan confirmation di bawah / titik hasil / di atas titik hasil.
7. Jika nilai DAC valid, simpan hasil ke `wiperArr[channel]` dan commit ke EEPROM.
```

**Binary Search**

```text
1. Hitung mid = (low + high) / 2.
2. Set DAC = mid.
3. Baca ADC.
4. Jika ADC belum berubah melebihi threshold -> low = mid.
5. Jika ADC sudah berubah melebihi threshold -> high = mid.
6. Ulangi sampai jarak low dan high tinggal 1.
7. Kandidat hasil adalah high, lalu lanjut confirmation.
```

Contoh iterasi: `32..64 -> 48 -> 56 -> 52 -> 54 -> 53`, sehingga kandidat hasil `53`.

#### 6.1.4 Field-Aligned Nulling Flow `(field approved)`
Source: FieldReference.

```text
setAllWiper(1)
-> preheat sensor
-> pilih channel mux
-> set PGA calibration = tinggi
-> ukur baseline dari DAC 0..10
-> lakukan binary search 1..4095
-> simpan hasil ke wiperArr[channel]
-> jika hasil valid, simpan ke EEPROM
```

#### 6.1.5 Nulling Config 

Parameter target design nulling:
| Parameter | Target Design |
|---|---|
| DAC range | `0..4095` |
| ADC gain | `ADS1256_NULLING_GAIN` |
| ADC change threshold | `100 counts` |
| ADC average sample count | `8` |
| Settling time | `5 ms` |
| Exponential initial step | `1` |
| Exponential max step | `2048` |
| Confirmation below/above offset | `1` |
| Confirmation sample count | `5` |
| Primary algorithm | `Exponential + Binary + Confirmation` |
| Debug fallback | `Linear sweep` |

Parameter runtime lama yang masih relevan `(field approved)`:
| Parameter | Field Reference |
|---|---|
| DAC range | `1..4095` |
| Baseline pre-scan | `0..10` |
| Threshold tegangan | `0.001f` |
| Gain for calibration | `PGA_64` |

Threshold final tetap harus divalidasi terhadap noise floor aktual saat gain nulling aktif.

#### 6.1.6 Nulling Data Structure 

Struktur data nulling target harus cukup untuk menyimpan hasil kalibrasi per channel dan metadata error dasarnya. 
```cpp
struct NullingResult {
    uint8_t channel;
    uint16_t dacCode;
    int32_t baselineAdc;
    int32_t nullAdc;
    int32_t deltaCount;
    bool success;
    int errorCode;
};

struct NullingProfile {
    uint16_t profileId;
    NullingResult results[8];
    bool allSuccess;
    uint32_t createdAtMs;
};
```

`wiperArr` lama tetap dipertahankan hanya untuk kompatibilitas lapangan.

#### 6.1.7 Default Wiper untuk 8 Sensor MQ pada Satu Board 
Source: FieldReference.

`wiperArr[8]` adalah delapan nilai default untuk delapan sensor MQ pada satu board ESP32. Label `Board1`, `Board2-2`, dan seterusnya hanya label deployment multi-board.

| Referensi Lapangan | Default `wiperArr[8]` |
|---|---|
| `Board1` | `961, 236, 124, 1035, 879, 1043, 1027, 1044` |
| `Board2-2` | `1020, 1, 1027, 984, 1049, 988, 1033, 1044` |
| `Board3` | `1029, 336, 697, 452, 1041, 224, 42, 740` |
| `Board4` | `189, 477, 1, 409, 144, 144, 42, 1` |
| `Board5` | `790, 296, 1, 38, 1, 985, 672, 735` |
| `Board6` | `256, 193, 1028, 1036, 1045, 1040, 844, 1044` |
| `Board7` | `50, 674, 2049, 553, 465, 686, 702, 725` |
| `Board9` | `806, 314, 2049, 369, 649, 444, 529, 915` |
| `Board10` | `675, 385, 541, 560, 661, 435, 752, 1` |
| `Board11` | `204, 53, 2049, 32, 52, 1, 1, 1` |

Catatan: nilai ini hanya default awal; hasil nulling valid yang tersimpan di EEPROM tetap menjadi sumber utama.

#### 6.1.8 Nulling Request Direction
Source: BaseDesign.

Request nulling sebaiknya membawa asal dan alasan operasi:

```cpp
enum class NullingRequestSource : uint8_t {
    BOOT             = 0,
    MQTT             = 1,
    LORA             = 2,
    SERIAL_PORT      = 3,
    DRIFT_DETECTION  = 4,
    MODBUS           = 5,
    BUTTON           = 6
};

enum class NullingReason : uint8_t {
    BOOT               = 0,
    BEFORE_DATASET     = 1,
    BEFORE_INFERENCE   = 2,
    DRIFT_CORRECTION   = 3,
    MANUAL             = 4,
    PERIODIC           = 5
};

struct NullingRequest {
    NullingRequestSource source;
    NullingReason reason;
    bool saveProfile;
    bool force;
    bool runFanBeforeNulling;
    uint32_t requestedAtMs;
};
```

#### 6.1.9 NullingService Interface
Source: BaseDesign.

Interface target:

```cpp
class NullingService {
public:
    bool begin();
    bool requestNulling(const NullingRequest& request);
    void update();
    bool isRunning() const;
    bool isDone() const;
    bool hasError() const;
};
```

#### 6.1.10 Nulling Safety Rules
Source: BaseDesign.

```text
- nulling requires external 24VDC
- nulling blocked in battery mode
- nulling blocked when alarm active unless explicitly forced by safe operator policy
- nulling blocked during active dataset recording
- nulling should not run while gas leak is currently detected
- nulling profile should be versioned
```

#### 6.1.11 Success / Failure Criteria

Nulling per channel dianggap **berhasil** jika:

```text
- baseline ADC awal berhasil dibaca
- ADC mulai berubah melebihi threshold saat DAC dinaikkan
- DAC code ditemukan sebelum mencapai batas maksimum
- hasil confirmation valid pada titik below / result / above
- tidak ada timeout atau saturasi ADC
```

Nulling per channel dianggap **gagal** jika:

```text
- ADC tidak berubah sampai DAC mencapai 4095
- ADS1256 read timeout atau data invalid
- TCA9548A gagal select channel
- MCP4725 gagal menerima DAC code
- confirmation step gagal
```

#### 6.1.12 Contoh Log

```text
[NULLING] Start channel=0 sensor=MQ8
[NULLING] CH0 baseline_adc=0
[NULLING] CH0 exp dac=1 adc=0 delta=0
[NULLING] CH0 exp dac=2 adc=0 delta=0
[NULLING] CH0 exp dac=4 adc=0 delta=0
[NULLING] CH0 exp dac=8 adc=0 delta=0
[NULLING] CH0 exp dac=16 adc=0 delta=0
[NULLING] CH0 exp dac=32 adc=0 delta=0
[NULLING] CH0 exp dac=64 adc=142 delta=142
[NULLING] CH0 range low=32 high=64
[NULLING] CH0 binary result dac_code=53
[NULLING] CH0 confirmed=true
[NULLING] CH0 success dac_code=53 baseline=0 null_adc=118 delta=118
```

#### 6.1.13 Boot Auto Nulling
Boot policy target:

```text
BOOT
-> LOAD EEPROM CONFIG
-> VALIDATE CTRL WORD
-> INIT_HARDWARE
-> POWER_DETECTION
-> if POWER_MODE_EXTERNAL:
     if modelFilePath invalid or minimum config invalid:
        ENTER_SERIAL_SETUP_OR_CONFIG_WAIT
     else if NULLING_AUTO_RUN_ON_BOOT:
        RUN_NULLING(source=BOOT, reason=BOOT, saveProfile=true)
        if nulling failed:
           ENTER_SETUP_OR_ERROR_WAIT
     else:
        LOAD_NULLING_PROFILE
        if profile invalid:
           RUN_NULLING(source=BOOT, reason=BOOT, saveProfile=true)
           if nulling failed:
              ENTER_SETUP_OR_ERROR_WAIT
-> if configuration valid and nulling/profile valid:
     SELECT_DEFAULT_STAGE
```

Battery boot:

```text
BOOT
-> POWER_DETECTION = BATTERY
-> LOAD EEPROM CONFIG
-> LOAD_STORED_NULLING_PROFILE
-> if modelFilePath invalid or minimum config invalid:
     SKIP_INFERENCE_AND_SET_CONFIG_ERROR
-> else if profile valid:
     RUN_INFERENCE
     LORA_SEND
-> else:
     SKIP_INFERENCE_AND_SET_ERROR
-> TPL5110_DONE
```

Catatan: `Dataset` dan `Inference` hanya boleh menganggap pembacaan sensor valid jika `NullingProfile` sudah ada dan valid.

---

### 6.2 Dataset Generation Stage 

#### 6.2.1 Tujuan 
Source: BaseDesign.

Dataset Generation Stage digunakan untuk merekam data 8 sensor MQ dalam format yang konsisten dengan input model AI.

Dataset dipakai untuk:

```text
- training model AI
- validasi model AI
- testing model AI
- perbaikan model bila data lapangan berubah
```

Flow stage dataset:

| Langkah | Nama Flow | Keterangan |
|---|---|---|
| 1 | Validate Command | Terima `START_DATASET` dan validasi parameter sesi |
| 2 | Check Power | Pastikan node berada pada external power |
| 3 | Ensure Valid Nulling Profile | Jalankan nulling bila diminta atau jika `NullingProfile` valid belum tersedia |
| 4 | Prepare Acquisition | Load profile, fan intake, settle, dan siapkan pembacaan sensor |
| 5 | Build Record | Baca 8 sensor, terapkan AGC / filter, lalu bentuk record dataset |
| 6 | Publish Data | Publish record ke MQTT topic `dataset/data` |
| 7 | Update Status | Publish status sesi dan cek stop condition |
| 8 | Finish Session | Publish summary saat sesi selesai |

#### 6.2.2 Power Policy 

Dataset generation hanya diizinkan saat external power aktif. 
```text
External 24VDC mode : allowed
Battery mode        : not allowed
```

#### 6.2.3 Control Source 

Sumber kontrol dataset dibagi menjadi jalur utama dan jalur debug. 
```text
Primary control:
- MQTT command from server

Optional debug control:
- Serial command for development
```

Catatan:
- MQTT adalah control path utama
- serial tetap boleh dipakai sebagai jalur debug / development

#### 6.2.4 MQTT Topics 

Topik target design untuk command, ack, dataset stream, dan status. 
```cpp
#define MQTT_TOPIC_CMD_FORMAT             "gas-leak-detector/%s/cmd"
#define MQTT_TOPIC_CMD_ACK_FORMAT         "gas-leak-detector/%s/cmd/ack"
#define MQTT_TOPIC_DATASET_FORMAT         "gas-leak-detector/%s/dataset"
#define MQTT_TOPIC_DATASET_DATA_FORMAT    "gas-leak-detector/%s/dataset/data"
#define MQTT_TOPIC_DATASET_STATUS_FORMAT  "gas-leak-detector/%s/dataset/status"
#define MQTT_TOPIC_DATASET_SUMMARY_FORMAT "gas-leak-detector/%s/dataset/summary"
```

Catatan:
- topic di atas adalah format resmi yang dipakai desain ini
- `dataset/data` adalah topic publish utama untuk stream 8 nilai sensor per sample, sedangkan topic lama hanya referensi migrasi / kompatibilitas

#### 6.2.5 `START_DATASET` Command
Source: BaseDesign.

Shape command target:

```jsonc
{
  "cmd": "START_DATASET",                // command dataset start
  "label": "LPG",                        // label gas / kondisi dataset
  "target_samples": 1000,                // target jumlah sample yang ingin direkam
  "sample_interval_ms": 1000,            // interval antar-sample = 1 detik
  "max_duration_ms": 1200000,            // batas durasi sesi = 20 menit, cukup untuk target 1000 sample @ 1 detik
  "use_fan_intake": true,                // aktifkan fan intake sebelum sampling
  "fan_on_ms": 1000,                     // durasi fan ON per sampling / prepare cycle
  "post_fan_settle_ms": 0                // tambahan settle setelah fan OFF
}
```

Catatan updated draft: `START_DATASET` tidak menjalankan nulling otomatis. Dataset start wajib ditolak jika belum ada active `nulling_profile_id` yang valid. Nulling adalah stage/service terpisah karena setiap nulling sukses membuat profile baru dan mengubah validitas dataset/model.

#### 6.2.6 `STOP_DATASET` Command
Source: BaseDesign.

```json
{
  "cmd": "STOP_DATASET"
}
```

#### 6.2.7 Dataset Flow

```text
MQTT START_DATASET received
-> validate command
-> check power mode = EXTERNAL
-> reject if no valid active nulling profile
-> apply active nulling profile
-> publish command ACK accepted
-> publish dataset status STARTED
-> enter DATASET_RECORDING
```

Per sample:

```text
DATASET_RECORDING
-> FAN ON 1000 ms
-> FAN OFF
-> optional post-fan settle
-> read 8 sensor channels
-> ADS1256 AGC
-> convert to voltage
-> moving average after gain compensation
-> build dataset record
-> publish MQTT dataset record
-> wait next sample interval
```

Stop flow:

```text
MQTT STOP_DATASET received
-> stop recording
-> publish dataset summary
-> publish status STOPPED
-> publish command ACK accepted
-> return to idle
```

#### 6.2.8 Dataset Record
Source: BaseDesign.

Minimal informasi yang harus tercermin pada record dataset:

```text
device_id
node_id
mode = DATASET
seq
timestamp_ms
label
nulling_profile_id
sensor_voltage[8]
sensor_gain[8]
feature_order[8]
```

Topic publish untuk record ini:

```text
gas-leak-detector/{device_id}/dataset/data
```

`dataset/data` adalah topic stream sensor; `dataset/status` dan `dataset/summary` hanya untuk status dan ringkasan sesi.

#### 6.2.9 Dataset State Machine
Source: BaseDesign.

State machine dataset mengikuti flow pada `6.2.7`, dengan state inti:

```text
DATASET_IDLE                  // belum ada sesi dataset yang aktif
-> DATASET_VALIDATE_COMMAND   // validasi command dan parameter sesi
-> DATASET_POWER_CHECK        // pastikan mode power = EXTERNAL
-> DATASET_RECORDING          // ambil sample sensor dan bentuk record dataset
-> DATASET_MQTT_PUBLISH       // publish record / status ke topic MQTT
-> DATASET_CHECK_STOP_CONDITION // cek target sample, timeout, atau STOP_DATASET
```

#### 6.2.10 Field Reference Runtime Note 
Source: FieldReference.

Mode `TRAINING` lapangan memakai MQTT lokal; acquisition behavior tetap mengikuti jalur baca node lapangan.

---

### 6.3 Inference Stage 

#### 6.3.1 Tujuan 
Source: BaseDesign.

Inference stage digunakan untuk:

- membaca 8 sensor
- memuat dan mengaplikasikan nulling profile
- menjalankan fan intake sebelum sampling
- membentuk feature vector
- menjalankan model TFLite Micro
- menghasilkan label, confidence, dan alarm state
- meneruskan hasil inference ke LoRa layer

Flow stage inference:

| Langkah | Nama Flow | Keterangan |
|---|---|---|
| 1 | Detect Power Mode | Tentukan external mode atau battery mode |
| 2 | Load Runtime Context | Load config dan apply latest nulling profile |
| 3 | Prepare Sampling | Jalankan fan intake dan stabilisasi pembacaan bila diperlukan |
| 4 | Read Sensors | Baca 8 sensor melalui jalur ADS1256 |
| 5 | Build Features | Terapkan AGC / filter lalu susun feature vector |
| 6 | Run Model | Jalankan inference TFLite Micro |
| 7 | Decide Result | Tentukan label, confidence, dan alarm state |
| 8 | Report Result | Handoff hasil inference ke LoRa layer dan update status runtime |
| 9 | Finish Cycle | Jika battery mode, kirim `TPL5110 DONE`; jika external mode, lanjut ke siklus berikutnya |

#### 6.3.2 Power Policy

Inference dapat berjalan di:

```text
External 24VDC mode
Battery mode
```

External mode:

```text
- loop inference periodik
- Modbus aktif
- LoRa dapat kirim periodik atau saat alarm
```

Battery mode:

```text
- one-shot inference cycle
- LoRa transmit
- open receive window after transmit
- accept ACK or server command during receive window
- pulse DONE ke TPL5110
```

#### 6.3.3 Combined Inference Flow

Alur target design:

```text
BOOT / STAGE START
-> POWER DETECTION
-> CHECK INFERENCE ALLOWED
-> LOAD NULLING PROFILE
-> APPLY NULLING DAC CODES
-> INIT TFLITE MODEL
-> IF BATTERY MODE: SENSOR WARM-UP
-> FAN INTAKE 1000 ms
-> READ SENSOR ARRAY WITH ADS1256 AGC
-> MOVING AVERAGE
-> FEATURE EXTRACTION
-> MODEL INFERENCE
-> PARSE AI OUTPUT
-> ALARM DECISION
-> ALARM LAMP + BUZZER UPDATE
-> LORA TRANSMIT
-> OPEN POST-TRANSMIT RECEIVE WINDOW
-> PROCESS ACK / SERVER COMMAND IF RECEIVED
-> MODBUS REGISTER UPDATE, EXTERNAL ONLY
-> IF BATTERY MODE: TPL5110 DONE
```

Field-proven runtime note:

```text
cek network initialized
-> normalisasi 8 fitur
-> copy ke input tensor
-> invoke model
-> cari class dengan confidence terbesar
-> simpan predicted_class
-> simpan highest_confidence_score
-> hitung inference_time
-> update alarm state
-> siapkan LoRa payload
```

#### 6.3.4 Feature Vector 

Feature vector memakai 8 nilai sensor dalam urutan yang sudah langsung sama dengan urutan input model. 

```cpp
feature[i] = (sensorVoltage[i] - feature_mean[i]) / feature_std[i];
```

Aturan penting:

```text
Urutan fitur firmware harus sama persis dengan urutan fitur saat training.
Normalisasi inference harus sama dengan normalisasi dataset/training.
Dataset Generation Stage dan Inference Stage harus memakai pipeline sampling yang sama.
```

Catatan:
- urutan dan normalisasi fitur dikunci oleh base design
- runtime lapangan lama sudah konsisten pada tahap normalisasi sebelum invoke

#### 6.3.5 AI Runtime 

Runtime AI mengikuti `NeuralNetwork` dengan runtime `tfmicro` sebagai acuan implementasi, lalu operator dan bentuk integrasi lama tetap menjadi referensi perilaku.

Target design default:

```text
AI input feature count : 8
AI output mode         : multiclass
AI output class count  : 9
AI confidence threshold: 0.70
AI low confidence warn : 0.40
Initial tensor arena   : 8 KB
```

Field integration pattern: 

- `MicroErrorReporter`
- `MicroInterpreter`
- `MicroMutableOpResolver<10>`
- `tensor_arena` statis, boleh diperbesar bila model akhir membutuhkannya

Registered ops. 

- `FullyConnected`
- `Mul`
- `Add`
- `Logistic`
- `Reshape`
- `Quantize`
- `Dequantize`
- `Softmax`

Catatan:
- TFLite Micro adalah base runtime
- daftar operator mengikuti pola runtime lapangan yang sudah pernah dipakai

#### 6.3.6 Inference Result
Source: BaseDesign.

Minimal hasil inference yang harus direpresentasikan:

```text
predicted class
confidence
alarm / warning / anomaly status
```

#### 6.3.7 Alarm Rule 

Desain hasil gabungan memisahkan. 

- **alarm lokal**
- **aturan auto transmit LoRa**

Aturan historis yang terbukti di firmware lama:

```text
predicted_class != 0
AND
highest_confidence_score >= 0.80
```

Catatan updated draft:

- rule historis di atas tidak menjadi aturan final running LoRa firmware baru,
- rule final running LoRa memakai `gasClass != clearGas && confidence >= GLD_LEL_THRESHOLD_PERCENT`,
- default awal `GLD_LEL_THRESHOLD_PERCENT = 30`,
- `confidence = 30` sudah alarm jika threshold masih default 30,
- threshold tetap harus configurable.

Catatan:
- base design memisahkan local alarm dan transmit policy
- rule auto transmit lapangan tetap dipertahankan sebagai reference behavior

#### 6.3.8 Inference Output to LoRa

Hasil inference harus diteruskan ke jalur LoRa sebagai output stage, tetapi detail format payload tidak dikunci di section ini.

```text
Inference Stage
-> hasil akhir AI / alarm
-> handoff ke LoRa layer
-> LoRa layer membentuk payload akhir
```

Catatan:
- `Section 9` membahas arsitektur komunikasi LoRa
- `Section 16` menjadi referensi utama untuk payload compact, ACK, retry, dan scheduling final

#### 6.3.9 Inference State Machine
Source: BaseDesign.

```text
INFERENCE_IDLE
-> INFERENCE_POWER_CHECK
-> INFERENCE_LOAD_NULLING_PROFILE
-> INFERENCE_APPLY_NULLING_PROFILE
-> INFERENCE_INIT_MODEL
-> INFERENCE_OPTIONAL_SENSOR_WARMUP
-> INFERENCE_FAN_INTAKE
-> INFERENCE_POST_FAN_SETTLE
-> INFERENCE_SENSOR_READ
-> INFERENCE_AGC_APPLY
-> INFERENCE_MOVING_AVERAGE
-> INFERENCE_BUILD_FEATURES
-> INFERENCE_MODEL_RUN
-> INFERENCE_PARSE_RESULT
-> INFERENCE_DECISION
-> INFERENCE_ALARM_UPDATE
-> INFERENCE_LORA_SEND
-> INFERENCE_MODBUS_UPDATE
-> INFERENCE_BATTERY_DONE
```

#### 6.3.10 LoRa Downlink Behavior During Inference
Source: Runtime firmware.

Saat inference berjalan, jalur LoRa saat ini belum menjalankan command service dari downlink. Runtime aktual:

```text
- packet RX yang masuk dibaca dan di-log pada level packet type
- belum ada parser ACK final berbasis seq
- belum ada executor command seperti nulling, dataset, atau service command lain dari LoRa
- receive mode tetap dipakai sebagai jalur observasi dan extension point untuk pengembangan berikutnya
```

---

## 7. Third-Party Arduino Libraries 

| Component | Library Strategy | Notes |
|---|---|---|
| ADS1256 | ADS1256-main | Dipakai via `#include <ADS1256.h>` |
| TCA9548A | TCA9548-master | Dipakai via `#include <TCA9548.h>` |
| MCP4725 | MCP4725-master | Dipakai via `#include <MCP4725.h>` |
| LoRa | RadioLib | Dipakai via `#include <RadioLib.h>` |
| MQTT | PubSubClient | Dipakai via `#include <PubSubClient.h>` |
| JSON | ArduinoJson | Dipakai via `#include <ArduinoJson.h>` |
| LoRa payload | CayenneLPP | Dipakai via `#include <CayenneLPP.h>` |
| Moving average | movingAvgFloat-master | Dipakai via `#include <movingAvgFloat.h>` |
| AI runtime | `NeuralNetwork.h` + `tfmicro` | `NeuralNetwork.h` dipakai pada runtime AI node, dengan runtime pendukung di `lib/tfmicro` |

Rules:

```text
- Semua akses hardware sebaiknya melalui wrapper internal.
- Stage logic tidak langsung memegang detail low-level library.
- Jika library diganti, perubahan dibatasi di wrapper.
```

### 7.1 PlatformIO Draft
Source: BaseDesign.

Konfigurasi build target design:

```ini
[env:gas-leak-detector]
platform  = espressif32
board     = 4d_systems_esp32s3_gen4_r8n16
framework = arduino
monitor_speed = 115200
board_build.partitions  = default_16MB.csv
board_build.filesystem  = littlefs
lib_ldf_mode = deep+
build_unflags =
    -DARDUINO_USB_MODE=1
build_flags =
    -DCORE_DEBUG_LEVEL=3
    -DARDUINO_USB_MODE=0
    -DARDUINO_USB_CDC_ON_BOOT=1
```

Catatan:
- board `4d_systems_esp32s3_gen4_r8n16` adalah target aktual yang sesuai dengan `ESP32-S3-WROOM-1U-N16R8` (16 MB Flash, 8 MB PSRAM)
- partisi `default_16MB.csv` diperlukan untuk memanfaatkan flash 16 MB secara penuh
- `lib_ldf_mode = deep+` dipakai karena semua library disimpan lokal di `firmware/lib/`
- flag USB CDC diperlukan agar Serial Monitor via USB berfungsi di ESP32-S3

---

## 8. Sensor Acquisition Pipeline 

### 8.1 Acquisition Design Decision 
Source: BaseDesign.

```text
ADC device        : ADS1256
Resolution        : 24-bit
Input mode        : Single-ended, 8 channel
Reference voltage : 2.497V
INA333 gain       : 1x
Primary runtime   : Voltage-based processing
AGC approach      : High-sensitivity-first
```

### 8.2 Fan Intake Rule
Source: BaseDesign.

Sebelum sampling utama, firmware harus menjalankan **fan intake** untuk memaksa gas eksternal masuk ke enclosure.

```text
Fan pin       : GPIO42
Fan ON time   : 1000 ms
Post-fan settle : 0 ms by default
Applies to    : Dataset Generation Stage and Inference Stage
```

Aturan perilaku:

```text
Before every dataset sample:
-> FAN ON 1000 ms
-> FAN OFF
-> optional settle delay
-> read sensor array

Before every inference cycle:
-> FAN ON 1000 ms
-> FAN OFF
-> optional settle delay
-> read sensor array
```

Catatan:
- aturan fan intake mengikuti `BaseDesign`
- `FieldReference` tidak mendefinisikan perilaku ini secara eksplisit

### 8.3 Field-Proven Runtime Acquisition Flow `(field approved)`
Source: FieldReference.

Pada implementasi lapangan, acquisition path utama berjalan seperti ini:

```text
setiap 10 ms
-> pilih channel aktif
-> gainCalibrate(channel)
-> takeDataMQ(channel)
-> simpan ke buffer hasil
-> lanjut ke channel berikutnya
```

### 8.4 Count-to-Voltage Conversion 

Layer pemrosesan menggunakan nilai tegangan, bukan raw count murni. 

Draft formula:

```cpp
constexpr float ADS1256_VREF_VOLTS = 2.497f;
voltage = (rawCount / 8388607.0f) * (ADS1256_VREF_VOLTS / pgaGain);
```

Catatan. 

- formula final harus mengikuti konfigurasi ADS1256 aktual
- runtime lapangan memang mengubah raw menjadi voltage sebelum inferensi `(field approved)`

Catatan:
- base design memakai processing berbasis tegangan
- runtime lapangan lama juga sudah mengubah raw ADC menjadi voltage

### 8.5 AGC Strategy 

Strategi AGC mengikuti prinsip `high-sensitivity-first` dari `BaseDesign`.

```text
Default gain = maksimum
Jika mendekati saturasi -> turunkan gain
Jika sinyal kembali kecil -> naikkan gain lagi secara bertahap
```

Prinsip gain per stage:

```text
Standby
- ADS1256 PGA berada pada gain maksimum agar perubahan kecil cepat terdeteksi

Nulling
- ADS1256 PGA memakai gain maksimum agar titik awal perubahan ADC lebih mudah terlihat

Dataset Generation
- mulai dari gain maksimum
- jika sinyal membesar dan mendekati saturasi, turunkan gain

Inference
- mulai dari gain maksimum
- jika sinyal membesar dan mendekati saturasi, turunkan gain
- output tetap diproses sebagai tegangan yang sudah dikompensasi gain
```

Gain sequence:

```text
Gain down:
64x -> 32x -> 16x -> 8x -> 4x -> 2x -> 1x

Gain up:
1x -> 2x -> 4x -> 8x -> 16x -> 32x -> 64x
```

Draft parameter target design:

```text
ADS1256_NULLING_GAIN            = 64
ADS1256_DATASET_INITIAL_GAIN    = 64
ADS1256_INFERENCE_INITIAL_GAIN  = 64

ADS1256_AGC_SATURATION_RATIO    = 0.95
ADS1256_AGC_GAIN_DOWN_RATIO     = 0.85
ADS1256_AGC_GAIN_UP_RATIO       = 0.20

ADS1256_AGC_GAIN_DOWN_CONFIRM_COUNT = 1
ADS1256_AGC_GAIN_UP_CONFIRM_COUNT   = 5
ADS1256_AGC_MAX_ATTEMPTS            = 4
```

Catatan:
- moving average dan feature processing harus memakai `voltage_after_gain_compensation`, bukan raw count
- pada implementasi lapangan, gain adjustment dilakukan per channel melalui `gainCalibrate(channel)` sebelum pembacaan utama channel tersebut `(field approved)`

### 8.6 Feature Order Alignment 

Target desain ini tidak memakai remap pada jalur feature model. Urutan channel fisik, urutan baca firmware, dan urutan feature model harus sama.

| Physical Channel | Sensor |
|---:|---|
| 0 | MQ8 |
| 1 | MQ135 |
| 2 | MQ3 |
| 3 | MQ5 |
| 4 | MQ4 |
| 5 | MQ7 |
| 6 | MQ6 |
| 7 | MQ2 |

Aturan:
- `channel n` dibaca sebagai `feature n`
- firmware, dataset, dan model training harus memakai urutan yang sama
- remap feature tidak dipakai; lookup table hanya tetap dipakai untuk memilih DAC nulling yang benar

### 8.7 Moving Average 

Moving average tetap bagian dari target design dan dipakai untuk menstabilkan output sensor sebelum dipakai oleh stage berikutnya.

Prinsip target design:

```text
SENSOR_OUTPUT_INTERVAL_MS    = 1000
ADS1256_MOVING_AVERAGE_COUNT = 10
```

Artinya, sistem menargetkan output sensor **1 kali per detik** yang dibentuk dari **moving average 10 data**.

Aturan utama:

```text
moving average harus dihitung dari voltage_after_gain_compensation
```

Bukan dari:

```text
raw ADC count
```

Alasannya:
- gain ADS1256 dapat berubah karena AGC
- raw count dari gain yang berbeda tidak bisa langsung di-average secara aman
- voltage yang sudah dikompensasi gain memberi domain yang konsisten untuk filtering dan feature processing

Relasi ke output sensor:

```text
Field `movingAverageVoltage` menjadi bagian dari representasi output sensor final.
Lihat Section 8.8 untuk struktur output authoritative.
```

Catatan:
- pada target design, moving average adalah bagian normal dari jalur output sensor
- referensi lapangan lama masih dapat berjalan tanpa moving average aktif, tetapi arah desain final tetap memakai output yang sudah melalui moving average

### 8.8 Sensor Output Format
Source: BaseDesign.

Representasi hasil baca sensor sebaiknya tetap eksplisit dan typed:

```cpp
struct SensorVoltage {
    float voltage;
    float movingAverageVoltage;
    uint8_t gain;
    bool valid;
    bool saturated;
};

struct SensorArrayVoltageReading {
    SensorVoltage channels[8];
    uint32_t timestampMs;
    bool allValid;
};
```

### 8.9 User Button Design
Source: BaseDesign.

Board menyediakan user button pada `GPIO16` untuk fungsi service/debug lokal.

```cpp
#define PIN_USER_BUTTON 16
#define USER_BUTTON_ACTIVE_LOW true
```

Rekomendasi aksi saat tombol dilepas:

| Action | Durasi | Fungsi | Safety |
|---|---:|---|---|
| Short press | `< 1 detik` | Print status ringkas ke Serial | Aman |
| Long press | `>= 3 detik` | Toggle verbose Serial debug | Aman |
| Service press | `>= 6 detik` | Request manual nulling | External only, alarm off, dataset not recording |
| Very long press | `>= 10 detik` | Clear latched error / enter service mode | Factory reset disabled |

Feedback `Status-LED` selama tombol masih ditekan:

| Hold range | Blink `Status-LED` | Arti feedback |
|---|---:|---|
| `< 1 detik` | `1x` | Masuk range `Short press` |
| `1 <= x < 3 detik` | `2x` | Masuk range transisi sebelum `Long press` |
| `3 <= x < 6 detik` | `3x` | Masuk range `Long press` |
| `6 <= x < 10 detik` | `4x` | Masuk range `Service press` |
| `>= 10 detik` | `5x` | Masuk range `Very long press` |

Aturan feedback:

```text
- blink pattern dipicu sekali saat hold duration pertama kali memasuki range baru
- selama tombol tetap ditekan di range yang sama, pattern tidak diulang terus-menerus
- pattern berikutnya baru dipicu saat hold duration masuk ke range berikutnya
- feedback hanya penanda range; aksi final tetap dieksekusi saat tombol dilepas
- Status-LED dipakai sebagai preview lokal agar user tahu fungsi apa yang akan dipicu bila tombol dilepas saat itu
```

Battery mode policy:

```text
- short press boleh memberi status minimal bila Serial aktif
- long/nulling/service press ditolak di battery mode
- button tidak boleh memperpanjang wake cycle battery secara tidak perlu
```

---

## 9. LoRa Communication Design 

### 9.1 LoRa Decision 

Keputusan desain LoRa pada node. 
```text
Library    : RadioLib
Flow type  : direct node transmit
Node role  : prepare and send sensor result payload
```


### 9.2 Radio Object Draft 
Source: BaseDesign.

```cpp
radio = new Module(PIN_LORA_CS, PIN_LORA_DIO1, PIN_LORA_RST, PIN_LORA_BUSY);
```

### 9.3 LoRa Config 

Section ini menjelaskan arsitektur radio dan profil konfigurasi yang pernah dipakai sebagai acuan. Nilai payload, ACK, retry, dan scheduling final dikunci di `Section 16`. 

```text
Base radio profile:
- Frequency        : 920.0 MHz
- Bandwidth        : 125.0 kHz
- Spreading Factor : 7
- Coding Rate      : 5
- Sync Word        : 0x12
- TX power         : 17 dBm
- Preamble         : 8

Field reference:
- Spreading Factor : 9
- Coding Rate      : 7
```

Nilai final deployment harus dikunci di satu profil konfigurasi board.

### 9.4 Payload Direction 

Keputusan gabungan untuk payload LoRa:

```text
Target design      : compact binary payload
Field reference    : CayenneLPP payload on node, historical only
Identity on air    : deviceId
siteId / GPS       : not sent through LoRa
Location mapping   : server-side
```

Catatan: `CayenneLPP` hanya dipertahankan sebagai referensi migrasi lapangan. Format payload final node tetap `compact binary`, dan definisi finalnya ada di `Section 16`.

### 9.5 Send Trigger 
Source: FieldReference.

Node dapat mengirim karena:

- request manual serial `SEND`
- interval periodik saat auto transmit aktif
- event inference yang memenuhi rule alarm / confidence

---

## 10. Wi-Fi + MQTT Design 

### 10.1 Use Case 

Wi-Fi + MQTT dipakai hanya pada `external power mode`, tetapi lifecycle runtime-nya tidak dibatasi ketat ke `Dataset Stage` saja. Pada firmware saat ini, MQTT diinisialisasi setelah konfigurasi valid dan tetap dipelihara selama node berada pada runtime external mode agar command dataset dan service command tetap bisa diterima.

### 10.2 MQTT Topics from ESP32 Perspective
Source: BaseDesign + runtime firmware.

Pada firmware saat ini, behavior MQTT dari sudut pandang ESP32 adalah:

- subscribe command dataset / service saat `external power mode`
- publish `ack`, `dataset/data`, `dataset/status`, dan `dataset/summary`
- tetap memanggil `mqtt.loop()` selama runtime external mode, termasuk saat `Inference Stage`
- tidak ada aktivitas Wi-Fi / MQTT di battery mode

| Topic | Arah dari sudut pandang ESP32 | Fungsi |
|---|---|---|
| `gas-leak-detector/{device_id}/cmd` | Subscribe | Menerima command service umum saat external power; implementasi aktif saat ini hanya `START_NULLING` |
| `gas-leak-detector/{device_id}/dataset` | Subscribe | Menerima command dataset seperti `START_DATASET` dan `STOP_DATASET` beserta parameter sesi |
| `gas-leak-detector/{device_id}/cmd/ack` | Publish | Mengirim acknowledgement bahwa command diterima, ditolak, atau gagal dijalankan |
| `gas-leak-detector/{device_id}/dataset/data` | Publish | Mengirim record dataset per sample, termasuk 8 nilai sensor yang dibaca ESP32 selama `Dataset Stage` |
| `gas-leak-detector/{device_id}/dataset/status` | Publish | Mengirim status stage dataset seperti idle, running, stopping, completed, atau error |
| `gas-leak-detector/{device_id}/dataset/summary` | Publish | Mengirim ringkasan hasil sesi dataset seperti durasi, jumlah record, dan status akhir |

### 10.2.1 Expected Data for Subscribe Topics

Contoh data yang diharapkan ESP32 saat menerima topic subscribe:

`gas-leak-detector/{device_id}/cmd`

```json
{
  "cmd": "START_NULLING",
  "source": "mqtt",
  "force": false,
  "save_profile": true
}
```

`gas-leak-detector/{device_id}/dataset`

```json
{
  "cmd": "START_DATASET",
  "label": "LPG",
  "target_samples": 1000,
  "sample_interval_ms": 1000,
  "max_duration_ms": 1200000,
  "use_fan_intake": true,
  "fan_on_ms": 1000,
  "post_fan_settle_ms": 0
}
```

`gas-leak-detector/{device_id}/dataset`

```json
{
  "cmd": "STOP_DATASET"
}
```

### 10.2.2 Example Publish Payloads from ESP32

Contoh payload yang di-publish ESP32:

`gas-leak-detector/{device_id}/cmd/ack`

```json
{
  "cmd": "START_NULLING",
  "accepted": true,
  "reason": "external_power_ok",
  "timestamp_ms": 123456
}
```

`gas-leak-detector/{device_id}/dataset/data`

```json
{
  "device_id": "node-01",
  "node_id": 1,
  "mode": "DATASET",
  "seq": 15,
  "timestamp_ms": 123456,
  "label": "clean_air",
  "nulling_profile_id": 4,
  "sensor_voltage": [0.82, 0.91, 1.02, 0.77, 0.88, 0.95, 1.10, 0.69],
  "sensor_gain": [64, 64, 64, 64, 64, 64, 64, 64],
  "feature_order": ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
}
```

`gas-leak-detector/{device_id}/dataset/status`

```json
{
  "stage": "DATASET",
  "status": "running",
  "seq": 15,
  "label": "clean_air"
}
```

`gas-leak-detector/{device_id}/dataset/summary`

```json
{
  "stage": "DATASET",
  "result": "completed",
  "total_records": 120,
  "duration_ms": 120000
}
```


### 10.3 Field Reference Defaults 
Source: FieldReference.

Field reference lama pernah memakai SSID, broker, credential, dan topic lokal terpisah. Pada desain final, seluruh parameter ini dianggap deployment-specific dan tidak dikunci di dokumen utama.

### 10.4 Design Decision

- Wi-Fi dan MQTT hanya aktif pada `external power mode`
- Wi-Fi dan MQTT tidak aktif di `battery mode`
- saat node berada di `Inference Stage` external mode, koneksi MQTT tetap dipertahankan agar command dataset atau service tetap dapat diterima
- format topic `gas-leak-detector/{device_id}/...` adalah format base design yang menjadi acuan utama
- MQTT manager adalah jalur kontrol dan publish utama untuk `Dataset Stage`, serta tetap menjadi control plane service ringan selama runtime external mode
- implementasi service command MQTT aktif saat ini baru `START_NULLING` pada topic `cmd`; command lain masih bisa ditambahkan tanpa mengubah struktur topic
- topik dan parameter field reference lama boleh dipakai sebagai default awal, tetapi harus dianggap configurable dan bisa diubah-ubah sesuai deployment

---

## 11. Power Architecture Design 

### 11.1 Power Source Overview 
Source: BaseDesign.

```text
External 24VDC mode
Battery mode via TPL5110
Power source detection
```

Bagian ini hanya menjelaskan bagaimana firmware melihat sumber daya yang tersedia.

### 11.2 Power Path Detection

Klasifikasi jalur daya pada board baru menggunakan dua sinyal utama:

- `PG24` / `24V Power Good` pada `GPIO45`
- `BATMON` / `Battery Monitor` pada `GPIO4`

Aturan keputusan:

```text
Jika PG24 = normal / active
-> power path = External 24VDC

Jika PG24 = fault / inactive
AND BATMON = ada tegangan baterai
-> power path = Battery

Jika PG24 = fault / inactive
AND BATMON = tidak ada tegangan baterai
AND 5V rail tetap membuat board hidup
-> power path = External 5V
```

Aturan tambahan:
- `PG24 normal` berarti jalur `24V -> 5V` valid dan harus diprioritaskan
- `PG24 fault` dengan `BATMON` tidak valid tetapi board tetap aktif berarti node sedang disuplai dari `5V external`
- hanya jika `PG24 fault`, `BATMON` tidak valid, dan board tidak memiliki 5V rail aktif maka sumber daya dianggap invalid

### 11.3 Battery Monitor Program
Source: BaseDesign.

Battery monitor memakai analog input `GPIO4` dan voltage divider.

Formula dasar:

```text
Vadc = Vbattery * R_BOTTOM / (R_TOP + R_BOTTOM)
Vbattery = Vadc * (R_TOP + R_BOTTOM) / R_BOTTOM
```

Untuk board ini, policy firmware yang harus dipakai adalah:

```text
BATMON divider : 200k / 100k
Practical scaling for firmware : Vbattery = Vadc * 3
```

Konfigurasi target:

```cpp
#define ENABLE_BATTERY_VOLTAGE_MONITOR true
#define BATTERY_ADC_MAX_VOLTAGE 3.3f
#define BATTERY_ADC_MAX_COUNT   4095.0f
#define BATTERY_DIVIDER_R_TOP     200000.0f
#define BATTERY_DIVIDER_R_BOTTOM  100000.0f
#define BATTERY_MIN_VALID_VOLTAGE 3.00f
#define BATTERY_LOW_VOLTAGE      3.50f
#define BATTERY_CRITICAL_VOLTAGE 3.30f
#define BATTERY_FILTER_ALPHA     0.20f
#define BATTERY_SAMPLE_COUNT     16
```

Representasi status:

```cpp
struct BatteryStatus {
    float voltage;
    float adcVoltage;
    int rawAdc;
    bool present;
    bool low;
    bool critical;
    bool valid;
};
```

### 11.4 Stage Permission 
  
Izin operasi per stage mengikuti tabel berikut. 
| Stage | External 24V | External 5V | Battery |
|---|---|---|---|
| Nulling | Allowed | Allowed | Not allowed |
| Dataset | Allowed | Allowed | Not allowed |
| Inference | Allowed | Allowed | Allowed |
| Modbus | Allowed | Allowed | Not active |
| MQTT Dataset Control | Allowed | Allowed | Not used |
| LoRa Transmission | Allowed | Allowed | Allowed |
| Alarm Lamp/Buzzer | Allowed | Allowed | Power-aware |


### 11.5 Battery Behavior 

- monitor battery voltage dari GPIO4 
- jika battery critical, skip proses yang tidak penting 
- pada battery mode, fokus ke inference dan LoRa send singkat 
- kirim pulse `DONE` ke TPL5110 setelah siklus selesai 


---

## 12. RS485 / Modbus RTU Slave Design 

### 12.1 Modbus Decision 
Source: BaseDesign.

```text
Role        : Modbus RTU Slave
Interface   : RS485
Direction   : GPIO-controlled DE/RE
```

### 12.2 Config
Source: BaseDesign.

Konfigurasi target design:

```text
Slave ID      : configurable per deployment, recommended 1..247
Baudrate      : 9600
UART config   : 8N1
Direction pin : GPIO19
RX            : GPIO20
TX            : GPIO21
```

Catatan:
- `Slave ID = 0` tidak boleh dipakai sebagai alamat slave normal karena secara praktis diperlakukan sebagai broadcast
- nilai final `Slave ID` harus menjadi bagian dari konfigurasi board / deployment

### 12.3 Register Address Policy
Source: BaseDesign.

Kebijakan umum:

```text
- read-only registers untuk status sensor, AI, power, LoRa, dan health
- writable command registers untuk trigger operasi aman
- register map harus stabil agar alat eksternal tidak pecah saat firmware berubah
```

### 12.4 Read-Only Registers
Source: BaseDesign + runtime firmware.

Register berikut adalah peta alamat yang diekspos firmware. Namun pada runtime saat ini, register yang dipastikan di-update setiap siklus inference adalah `SYSTEM_STATE`, `ACTIVE_STAGE`, `POWER_MODE`, `AI_LABEL_ID`, `AI_CONFIDENCE_X1000`, `ALARM_ACTIVE`, `INFERENCE_VALID`, `WARNING_ACTIVE`, `BATTERY_MV`, `POWER_GOOD_24V`, register sensor `40..77`, `LORA_STATUS`, `MODBUS_STATUS`, dan `PACKET_SEQ_LOW/HIGH`. Register lain tetap dipertahankan di map agar antarmuka Modbus stabil, tetapi belum semuanya diisi penuh oleh logic aplikasi saat ini.

Draft `read-only register map`:

| Address | Register | Scaling / Value | Access | Description |
|---:|---|---|---|---|
| 0 | DEVICE_ID_LOW | uint16 | R | Device ID low word |
| 1 | DEVICE_ID_HIGH | uint16 | R | Device ID high word |
| 2 | FIRMWARE_VERSION | uint16 | R | Firmware version |
| 10 | SYSTEM_STATE | enum | R | Current firmware state |
| 11 | ACTIVE_STAGE | enum | R | Nulling / dataset / inference |
| 12 | POWER_MODE | enum | R | External / battery / error |
| 13 | HEALTH_FLAGS | bitmask | R | System health bitmask |
| 14 | LAST_ERROR_CODE | enum | R | Last error code |
| 20 | AI_LABEL_ID | enum | R | Predicted AI class |
| 21 | AI_CONFIDENCE_X1000 | 0-1000 | R | AI confidence |
| 22 | ALARM_ACTIVE | 0/1 | R | Alarm state |
| 23 | INFERENCE_VALID | 0/1 | R | Last inference valid |
| 24 | FINAL_STATUS | enum | R | Final decision status |
| 25 | WARNING_ACTIVE | 0/1 | R | Warning state |
| 26 | ANOMALY_DETECTED | 0/1 | R | Anomaly flag |
| 27 | ANOMALY_MAX_Z_X100 | z x 100 | R | Max z-score |
| 28 | ANOMALY_SENSOR_COUNT | count | R | Number of deviating sensors |
| 30 | BATTERY_MV | mV | R | Battery voltage |
| 31 | POWER_GOOD_24V | 0/1 | R | 24V buck power-good |
| 40 | MQ2_MV | mV | R | MQ2 voltage |
| 41 | MQ3_MV | mV | R | MQ3 voltage |
| 42 | MQ4_MV | mV | R | MQ4 voltage |
| 43 | MQ5_MV | mV | R | MQ5 voltage |
| 44 | MQ6_MV | mV | R | MQ6 voltage |
| 45 | MQ7_MV | mV | R | MQ7 voltage |
| 46 | MQ8_MV | mV | R | MQ8 voltage |
| 47 | MQ135_MV | mV | R | MQ135 voltage |
| 50 | MQ2_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 51 | MQ3_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 52 | MQ4_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 53 | MQ5_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 54 | MQ6_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 55 | MQ7_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 56 | MQ8_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 57 | MQ135_GAIN | 1/2/4/8/16/32/64 | R | ADS1256 gain |
| 60 | MQ2_VALID | 0/1 | R | Sensor channel valid |
| 61 | MQ3_VALID | 0/1 | R | Sensor channel valid |
| 62 | MQ4_VALID | 0/1 | R | Sensor channel valid |
| 63 | MQ5_VALID | 0/1 | R | Sensor channel valid |
| 64 | MQ6_VALID | 0/1 | R | Sensor channel valid |
| 65 | MQ7_VALID | 0/1 | R | Sensor channel valid |
| 66 | MQ8_VALID | 0/1 | R | Sensor channel valid |
| 67 | MQ135_VALID | 0/1 | R | Sensor channel valid |
| 70 | MQ2_SATURATED | 0/1 | R | Sensor channel saturation |
| 71 | MQ3_SATURATED | 0/1 | R | Sensor channel saturation |
| 72 | MQ4_SATURATED | 0/1 | R | Sensor channel saturation |
| 73 | MQ5_SATURATED | 0/1 | R | Sensor channel saturation |
| 74 | MQ6_SATURATED | 0/1 | R | Sensor channel saturation |
| 75 | MQ7_SATURATED | 0/1 | R | Sensor channel saturation |
| 76 | MQ8_SATURATED | 0/1 | R | Sensor channel saturation |
| 77 | MQ135_SATURATED | 0/1 | R | Sensor channel saturation |
| 80 | NULLING_STATUS | enum/bitmask | R | Nulling status summary |
| 81 | LORA_STATUS | enum | R | LoRa status |
| 82 | MODBUS_STATUS | enum | R | Modbus status |
| 90 | UPTIME_LOW | uint16 | R | Uptime low word |
| 91 | UPTIME_HIGH | uint16 | R | Uptime high word |
| 92 | PACKET_SEQ_LOW | uint16 | R | LoRa packet seq low word |
| 93 | PACKET_SEQ_HIGH | uint16 | R | LoRa packet seq high word |

### 12.5 Writable Command Registers
Source: BaseDesign + runtime firmware.

Draft `writable command register map`:

| Address | Register | Access | Description |
|---:|---|---|---|
| 100 | COMMAND_CODE | R/W | Command code |
| 101 | COMMAND_ARG0 | R/W | Command argument 0 |
| 102 | COMMAND_ARG1 | R/W | Command argument 1 |
| 103 | COMMAND_APPLY | R/W | Write `1` to execute command |
| 104 | COMMAND_STATUS | R | Command result/status |
| 105 | COMMAND_LAST_ERROR | R | Last command error |

Command codes yang didefinisikan pada firmware:

| Code | Command | Allowed Power Mode | Description |
|---:|---|---|---|
| 0 | NONE | Any | No command |
| 1 | START_NULLING | External only | Diimplementasikan; memindahkan state ke `NULLING` |
| 2 | START_DATASET | External only | Sudah didefinisikan pada enum, tetapi belum dieksekusi oleh callback Modbus runtime |
| 3 | START_INFERENCE | External only | Sudah didefinisikan pada enum, tetapi belum dieksekusi oleh callback Modbus runtime |
| 4 | RESET_ALARM | External only | Diimplementasikan; mematikan output alarm lokal |
| 5 | SAVE_CONFIG | External only | Sudah didefinisikan pada enum, tetapi belum dieksekusi oleh callback Modbus runtime |
| 6 | REBOOT | External only | Diimplementasikan; memanggil `esp_restart()` |
| 7 | CLEAR_ERROR | External only | Sudah didefinisikan pada enum, tetapi belum dieksekusi oleh callback Modbus runtime |

Catatan runtime:

```text
Command callback Modbus saat ini hanya menangani:
- START_NULLING
- RESET_ALARM
- REBOOT

Command lain masih berstatus reserved / planned pada level aplikasi.
```

### 12.6 Power Policy 

```text
External mode : enabled
Battery mode  : disabled
```


---

## 13. Persistent Configuration 

### 13.1 Node Config Structure 

Firmware dasar sama untuk banyak board; pembeda utamanya adalah `board ID`, parameter board, dan file model machine learning yang dimuat.

Struktur target minimum untuk deployment banyak board:

```cpp
struct BoardDeploymentConfig {
    uint8_t  ctrlword;               // harus == CTRL_WORD_VALUE (0xA3)
    uint8_t  boardId;
    char     boardLabel[16];
    char     modelProfileId[32];
    char     modelFilePath[64];      // path di LittleFS, misal "/model.tflite"
    uint16_t defaultWiperArr[8];
    uint8_t  modbusSlaveId;
    float    loraFreq;               // MHz
    char     wifiSsid[32];
    char     wifiPassword[64];
    char     mqttBroker[64];
    uint16_t mqttPort;
    bool     nullingAutoRunOnBoot;
};
```

Default konseptual untuk node yang belum pernah dikonfigurasi:

```text
boardId       = 1
modelFilePath = belum valid / harus dikonfigurasi user via serial
defaultWiperArr[8] = 0,0,0,0,0,0,0,0
```

Untuk kompatibilitas lapangan, struktur berikut dicatat hanya sebagai field reference:

```cpp
struct idConfig {
    uint8_t ctrlword;
    uint8_t clusterId;
    uint8_t networkId;
    uint8_t targetId;
    uint8_t mode;
    uint8_t periode;
    uint8_t toGatewayId;
    uint8_t toNodeId;
    float loraFreq;
    uint16_t wiperArr[8];
};
```

`idConfig` tetap dipertahankan hanya sebagai field reference kompatibilitas.

### 13.2 EEPROM Rule 

- validasi config menggunakan `ctrlword`
- `CTRL_WORD_VALUE = 0xA3`
- `boardId`, `modelFilePath`, dan `wiperArr` dibaca dari EEPROM saat boot
- jika config invalid, node masuk ke mode tunggu config serial
- implementasi boleh memakai `boardId = 1` sebagai default placeholder awal, tetapi `modelFilePath` tetap harus dikonfigurasi user sebelum deployment final


### 13.3 Boot-Time Config Resolution

Urutan keputusan konfigurasi yang diharapkan:

```text
BOOT
-> LOAD EEPROM CONFIG
-> VALIDATE CTRL WORD
-> if boardId belum ada: gunakan default placeholder boardId = 1
-> if external power and modelFilePath kosong / invalid: masuk SERIAL SETUP untuk konfigurasi user
-> if wiperArr belum ada: isi default 0 per channel
-> jika external power tersedia dan active nulling profile belum valid: masuk CONFIG/NULLING REQUIRED, tunggu request Nulling Service
-> Nulling Service hanya berjalan saat diminta operator/command stage nulling
-> jika battery mode dan konfigurasi minimum / model belum valid: skip inference, set config error, lalu DONE
-> lanjut ke Dataset / Inference hanya jika konfigurasi minimum sudah valid
```

Aturan minimum:
- `boardId` harus terkonfigurasi
- `modelFilePath` harus valid sebelum model dipakai
- `wiperArr` hasil nulling disimpan di EEPROM
- `wiperArr = 0` per channel berarti pembacaan sensor belum tervalidasi

### 13.4 Important Field Note 
Source: FieldReference.

Pada referensi lapangan, `wiperArr` kadang di-load dari EEPROM lalu ditimpa default hardcoded. Pada desain final, policy utama adalah: `boardId` dan `modelFilePath` mengikuti EEPROM/serial user, `wiperArr` awal boleh `0`, dan hasil nulling valid harus disimpan ke EEPROM. Override hardcoded hanya dianggap historis.

### 13.5 Base Implementation Shape
Source: BaseDesign.

```text
- konfigurasi minimum mencakup board identity, model selection, nulling flags, AI metadata, LoRa, Wi-Fi/MQTT, power, dan Modbus
- modul inti dipisah menjadi controller, services/stages, drivers, sensing, processing, AI, comms, power, dan storage
- source tree minimum mengikuti pemisahan include/, src/app/, src/stages/, src/drivers/, src/sensing/, src/processing/, src/ai/, src/comms/, src/power/, src/storage/
- dataset and inference must use the same sampling condition
- battery inference is one-shot and ends with TPL5110 DONE
- LoRa is direct node transmit
- nulling, dataset, inference, power, and comms should be separated by module boundaries
```

---

## 14. Serial Commands 

Serial command gabungan yang perlu dipertahankan:

```text
RUNNING
TRAINING
SETUP
SEND
show
reset
restart
DEBUG_ON
DEBUG_OFF
```

Extended command base design yang boleh dipertahankan bila memang dipakai:

```text
stage nulling
stage dataset
stage inference
status
power status
help
```

Command runtime lapangan yang paling penting adalah `RUNNING`, `TRAINING`, `SETUP`, `SEND`, dan command debug terkait.

---

## 15. State Machine 

### 15.1 High-Level Flow 
Source: BaseDesign.

```text
BOOT
  ->
LOAD CONFIG
  ->
POWER MODE CHECK
  ->
CHECK CONFIG / NULLING PREREQUISITE
  +- if minimum config invalid and external power -> SERIAL SETUP / CONFIG WAIT
  +- if minimum config invalid and battery mode -> SKIP / CONFIG ERROR / DONE
  +- if prerequisites valid -> SELECT RUNTIME STAGE
  +- DATASET
  +- INFERENCE
```

### 15.2 Runtime Modes 
Source: FieldReference.

Node runtime mode yang relevan untuk firmware lapangan:

```text
RUNNING
TRAINING
SETUP
```

### 15.3 Inference-Oriented Loop 

```text
sensor read
-> calibration/gain update
-> feature normalize
-> model invoke
-> alarm update
-> handoff hasil inference ke LoRa layer
-> LoRa layer handles compact payload + direct transmit
```

Catatan: `Section 15.3` hanya menjelaskan flow logis inference sampai handoff ke LoRa layer. Detail payload, ACK, retry, dan scheduling final bersifat authoritative di `Section 16`.


---

## 16. LoRa Running Payload, Scheduling, and ACK Policy

### 16.1 Authoritative Contract

Untuk firmware baru, detail running payload LoRa dikunci oleh `docs/design/gld-ch/payload-contract.draft.md`. Bagian ini menggantikan format historis `NORMAL`, `ALARM`, `HEALTH`, dan `CayenneLPP`.

GLD mengirim `AppFrame` `SENSOR_DATA` ke CH. Isi `AppFrame.payload` adalah payload GLD encrypted 29 byte. CH tidak decrypt, tidak parse, dan tidak mengubah payload GLD.

```text
Plaintext GLD running payload : 4 byte
Encrypted GLD payload         : 29 byte
Outer frame                   : AppFrame SENSOR_DATA
CH role                       : validate frame, cache opaque payload, ACK alarm jika diminta
```

### 16.2 Plaintext Running Payload

Plaintext sebelum enkripsi selalu 4 byte:

| Offset | Field | Size | Type | Keterangan |
|---:|---|---:|---|---|
| 0 | `gasClass` | 1 | `uint8` | Kelas gas final |
| 1 | `confidence` | 1 | `uint8` | Confidence `0..100` |
| 2..3 | `batteryMv` | 2 | `uint16BE` | Tegangan baterai mV, `0xFFFF` jika tidak tersedia |

`gasClass` phase awal:

| Value | Meaning |
|---:|---|
| 0 | `clearGas` |
| 1 | `LPG` |
| 2 | `propana` |
| 3 | `butana` |
| 4 | `metana` |
| 5 | reserve |
| 6 | anomaly / unknown |
| 7..255 | reserved / invalid |

### 16.3 Encrypted Payload

Payload encrypted di `AppFrame.payload`:

| Offset | Field | Size |
|---:|---|---:|
| 0 | `keyId` | 1 |
| 1..12 | `nonce` | 12 |
| 13..16 | `ciphertext` | 4 |
| 17..28 | `tag` | 12 |

```text
Total encrypted payload = 1 + 12 + 4 + 12 = 29 byte
AEAD                  = AES-128-GCM
AAD                   = nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8
```

Production key tidak boleh hardcoded di source, tidak boleh masuk git, dan tidak boleh muncul di log.

### 16.4 AppFrame `typeFlags`

Semua running frame memakai `msgType = SENSOR_DATA (0x10)`.

| Kasus | `typeFlags` |
|---|---:|
| Normal battery | `0x10` |
| Normal external | `0x90` |
| Alarm battery | `0x50` |
| Alarm external | `0xD0` |

`0x50`, `0x90`, dan `0xD0` adalah `typeFlags`, bukan `msgType`.

### 16.5 Alarm and Normal Rule

Alarm ditentukan di GLD sebelum frame dikirim:

```c
alarm = (gasClass != GLD_GAS_CLEAR) &&
        (confidence >= GLD_LEL_THRESHOLD_PERCENT);
```

Default awal:

```c
static const uint8_t GLD_LEL_THRESHOLD_PERCENT = 30;
```

Aturan:

- `clearGas` selalu normal.
- Non-clear gas dengan `confidence < threshold` tetap dikirim sebagai class gas tersebut, tetapi normal.
- Non-clear gas dengan `confidence >= threshold` menjadi alarm.
- `confidence == 30` sudah alarm jika threshold default 30.
- Device fault, AI-not-ready, no-decision, atau model/profile mismatch tidak boleh dibuat menjadi alarm gas produksi.

### 16.6 Retry and ACK Policy

Normal frame:

- tidak meminta ACK,
- update latest cache di CH,
- dikirim ke server nanti lewat server pull.

Alarm frame:

- mengaktifkan `FLAG_ALARM_ACK`,
- CH wajib mengirim ACK compact dulu jika alarm diterima dan queue tersedia,
- alarm diteruskan CH ke parent/gateway via `alarmQueue`,
- retry alarm untuk event yang sama wajib mengirim ulang frame/payload snapshot yang sama.

Untuk retry alarm event yang sama, firmware tidak boleh regenerate:

- `seq`,
- `nonce`,
- `ciphertext`,
- `tag`,
- encrypted payload,
- CRC/frame snapshot.

ACK compact dari CH:

```text
typeFlags = 0x50
srcId     = CH ID
dstId     = GLD nodeId
seq       = sama dengan alarm GLD
payloadLen = 0
```

### 16.7 Scheduling Policy

External mode:

- inference dapat berjalan periodik sesuai config,
- normal telemetry mengikuti interval normal,
- alarm dikirim segera tanpa menunggu interval normal.

Battery mode:

- TPL5110 hanya dipakai di battery mode,
- satu siklus wake menjalankan inference dan TX,
- setelah TX buka RX window singkat untuk ACK/downlink phase sesuai scope,
- setelah selesai pulse `DONE` ke TPL5110.

### 16.8 Explicitly Rejected From Running LoRa

Field/format berikut tidak masuk running LoRa payload firmware baru:

- `LoRaNormalPayload` lama,
- `LoRaAlarmPayload` lama,
- `LoRaHealthPayload` lama,
- `packetType` lama sebagai wire format final,
- `sensorMv[8]`,
- raw ADC / raw sensor voltage,
- nulling snapshot,
- dataset record,
- health/status internal,
- z-score / anomaly detail,
- `powerMode` field di payload GLD,
- `finalStatus` field di payload GLD.

Data sensor rinci hanya masuk dataset/MQTT stage. Health/status internal tetap boleh ada di log, Modbus, atau format health terpisah di phase lanjut, tetapi bukan bagian running payload 4 byte / encrypted 29 byte.

### 16.9 Implementation Alignment Note

Section 9 membahas arsitektur LoRa; section 16 updated ini mengunci payload running GLD. Jika ada bagian historis lain yang menyebut payload lama, keputusan section ini dan kontrak GLD-CH menang.

---

## 17. Error Handling and Safety Rules 

### 17.1 General 
Source: BaseDesign.

```text
- Jika power mode invalid, stage utama tidak boleh dijalankan.
- Jika nulling profile tidak tersedia atau belum valid, dataset dan inference tidak boleh menganggap pembacaan sensor sebagai data valid sampai Nulling Service berhasil dijalankan pada external power.
- Jika ADC atau DAC gagal, health flag harus di-set.
- Jika AI invoke gagal, hasil inference invalid dan alarm tidak boleh bergantung pada output invalid.
- Alarm lokal tetap berjalan walaupun LoRa gagal.
```

### 17.2 Dataset Safety 

```text
- Dataset hanya boleh dijalankan pada external power.
- MQTT disconnect harus memicu reconnect attempt.
- Jika reconnect gagal melebihi limit, dataset stage berhenti dengan error.
```


### 17.3 Inference Safety 

```text
- Battery mode menjalankan inference singkat.
- Battery mode tidak menjalankan nulling.
- Battery mode harus mengirim DONE ke TPL5110 setelah selesai atau error.
```


### 17.4 Bus Safety 
Source: BaseDesign.

```text
- TCA9548A harus select satu channel pada satu waktu.
- Semua MCP4725 diakses lewat mux karena alamat sama.
- ADS1256 dan LoRa tidak boleh aktif bersamaan pada shared SPI bus.
```

---

## 18. Open Items

```text
1. Final LoRa frequency / exact field deployment profile bila berbeda dari base draft
2. Moving average sudah diputuskan aktif untuk jalur feature/dataset; yang tersisa hanya tuning window jika hasil bring-up perlu disesuaikan
3. Final battery warmup duration dan calibration constants hasil bring-up
4. Final freeze / external publication confirmation untuk Modbus register map
5. Final AI model metadata: tensor shape, labels, arena size, quantization choice
6. Migration rule payload sudah dikunci: CayenneLPP dan payload lama hanya historis, running LoRa memakai kontrak 4 byte plaintext / 29 byte encrypted
```

---

## 19. Implementation Priorities 

Urutan implementasi yang disarankan:

```text
Phase 1 - Board bring-up
- pin mapping
- I2C
- SPI
- ADS1256
- LoRa

Phase 2 - Sensor node core
- acquisition loop
- gain calibration
- nulling / setup calibration
- EEPROM config

Phase 3 - AI and result handling
- scaler params
- TFLite Micro
- alarm logic
- compact LoRa payload + ACK

Phase 4 - Support systems
- training mode MQTT
- power manager
- RS485 / Modbus

Phase 5 - Field alignment
- verify feature order alignment
- verify board-specific wiper defaults
- verify confidence threshold and auto transmit rule
```

---

## 20. Background References 

Dokumen ini merangkum desain firmware akhir berdasarkan arah desain dasar, mapping board aktual, dan runtime node yang telah tervalidasi di lapangan.

### 20.1 Component Datasheet References

| IC / Module | Datasheet Title | Link |
|---|---|---|
| ESP32-S3 | `ESP32-S3-WROOM-1 / ESP32-S3-WROOM-1U Datasheet` | `https://www.lcsc.com/datasheet/C3013946.pdf` |
| ADS1256 | `ADS1256 Very Low Noise, 24-Bit Analog-to-Digital Converter` | `https://www.lcsc.com/datasheet/C28186.pdf` |
| INA333 | `INA333 Zero-Drift, Low-Power, Instrumentation Amplifier` | `https://www.lcsc.com/datasheet/C19450.pdf` |
| MCP4725 | `MCP4725 12-Bit Digital-to-Analog Converter with EEPROM Memory` | `https://www.lcsc.com/datasheet/C144198.pdf` |
| TCA9548A | `TCA9548A Low-Voltage 8-Channel I2C Switch with Reset` | `https://www.lcsc.com/datasheet/C130026.pdf` |
| E22-900M | `E22-900MM22S User Manual / Datasheet` | `https://www.lcsc.com/datasheet/C5333985.pdf` |
| THVD1410DR | `THVD1410 3.3-V to 5-V RS-485 Transceiver` | `https://www.lcsc.com/datasheet/C2671345.pdf` |
| TPL5110 | `TPL5110 Nano Power System Timer with MOSFET Driver` | `https://www.lcsc.com/datasheet/C1539984.pdf` |
| ULN2003 | `ULN2003 7-Channel Darlington Transistor Array` | `https://www.lcsc.com/datasheet/C91443.pdf` |
---


