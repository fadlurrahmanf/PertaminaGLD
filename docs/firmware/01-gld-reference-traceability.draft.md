# GLD Reference Traceability Draft

**Status:** draft traceability sebelum firmware coding  
**Tanggal:** 2026-06-15  
**Firmware baru:** `D:\PertaminaGLD`  
**Referensi lama:** `D:\GasleakDetectorDesign\firmware`  
**Sumber kontrak utama:** `docs/design/gld-ch/payload-contract.draft.md`

Dokumen ini mencatat hubungan antara kontrak GLD-CH-server yang baru, firmware GLD lama yang sudah terbukti jalan di board, dan keputusan apa yang masuk ke firmware baru. Firmware lama dipakai **reference-only**, bukan di-merge mentah.

Aturan prioritas:

1. Kontrak GLD-CH-server adalah sumber kebenaran untuk wire protocol.
2. Firmware lama adalah sumber referensi untuk board, driver, pin, power, dan flow runtime yang sudah terbukti.
3. Jika kontrak dan firmware lama konflik, kontrak menang kecuali user menyetujui perubahan kontrak.
4. Tidak ada copy/merge otomatis dari firmware lama tanpa masuk matrix ini.
5. Firmware coding belum dimulai dari dokumen ini.

---

## 1. Ringkasan Keputusan

- Firmware baru tetap **contract-first**.
- `D:\GasleakDetectorDesign\firmware` menjadi referensi teknis untuk GLD saja.
- Target firmware GLD baru adalah firmware lengkap, tetapi eksekusinya tetap gated dengan urutan:
  1. running / inference,
  2. dataset / training capture,
  3. nulling / setup calibration.
- Behavior stage mengambil referensi dari firmware lama + kontrak baru. Jika wire protocol konflik, kontrak baru menang.
- Yang boleh diadaptasi dari firmware lama:
  - PlatformIO/Arduino ESP32-S3 setup,
  - board pins,
  - RadioLib/SX1262 setup,
  - `PowerManager` dan TPL5110 flow,
  - inference stage flow,
  - config store pattern,
  - sensor/nulling/dataset/Modbus/MQTT sesuai batas stage firmware baru.
- Yang tidak boleh diikuti dari firmware lama untuk running LoRa phase 1:
  - `LoRaPacketType NORMAL/ALARM/ACK/HEALTH`,
  - `LoRaNormalPayload` 13 byte,
  - `LoRaAlarmPayload` 33 byte,
  - `sensorMv[8]` di alarm running LoRa,
  - raw sensor / health / internal flags di running payload,
  - `packetType` lama sebagai format final.

---

## 2. Traceability Matrix

| No | Berdasarkan Kontrak | Berdasarkan Firmware Lama | Masuk Ke Firmware Baru | Keputusan / Catatan |
|---:|---|---|---|---|
| 1 | Firmware baru harus mengikuti kontrak `payload-contract.draft.md` untuk wire protocol GLD-CH-server. | Firmware lama punya wire protocol sendiri di `LoRaManager`: packet type `NORMAL`, `ALARM`, `ACK`, `HEALTH`. | Kontrak baru masuk penuh; packet type lama ditolak untuk phase 1. | Keputusan final: kontrak menang. Firmware lama hanya reference runtime, bukan protocol. |
| 2 | Phase 1 dimulai dari shared protocol: AppFrame, constants, plaintext 4 byte, AES-GCM payload 29 byte, AAD, test vector. | Firmware lama belum punya shared protocol layer lintas GLD/CH; LoRa payload langsung packed struct lokal GLD. | Buat shared protocol baru di repo ini. | Keputusan final: kontrak menang. Shared protocol wajib dibuat sebelum GLD/CH coding agar tidak beda tafsir. |
| 3 | Build system phase 1 direkomendasikan PlatformIO. | `platformio.ini` lama memakai `platform = espressif32`, `framework = arduino`, board `4d_systems_esp32s3_gen4_r8n16`, LittleFS, local `lib/`. | Adaptasi. | PlatformIO/Arduino/board target lama boleh jadi baseline karena sudah jalan di board. |
| 4 | Firmware baru boleh memakai local dependencies agar reproducible. | `platformio.ini` lama menyatakan semua library dari `firmware/lib/`, `lib_deps` kosong. | Adaptasi. | Untuk phase awal, local lib boleh dipakai agar tidak perlu download registry. Nanti bisa dirapikan. |
| 5 | Pin mapping harus cocok dengan hardware GLD. | `board_pins.h` lama mendefinisikan SPI, ADS1256, LoRa, I2C, output alarm, TPL5110, battery ADC, RS485, button. | Adaptasi penuh setelah diverifikasi. | Pin lama adalah referensi kuat karena sudah applied ke board. |
| 6 | LoRa GLD memakai SX1262/E22 dan AppFrame `SENSOR_DATA`. | Firmware lama memakai RadioLib `SX1262`, pin `PIN_LORA_CS=15`, `RST=39`, `BUSY=7`, `DIO1=40`, `RXEN=5`, `TXEN=6`. | Adaptasi hardware/radio init, ganti protocol payload. | Radio init dan RF switch dipertahankan, tetapi payload lama diganti AppFrame. |
| 7 | STAR GLD payload ke CH adalah encrypted opaque payload 29 byte di AppFrame. | Firmware lama `sendNormal()` mengirim `LoRaNormalPayload` 13 byte dan `sendAlarm()` mengirim `LoRaAlarmPayload` 33 byte. | Kontrak baru masuk; payload lama ditolak. | Keputusan final: kontrak menang. Running LoRa baru tidak boleh memakai struct lama. |
| 8 | Plaintext running payload hanya 4 byte: `gasClass`, `confidence`, `batteryMv` big-endian. | Firmware lama normal payload berisi `packetType`, `deviceId`, `seq`, `powerMode`, `aiClass`, `confidence`, `finalStatus`, `flags`, `batteryMv`. | Adaptasi sebagian. | Keputusan final: kontrak menang untuk payload. Ambil sumber `aiClass`, `confidence`, `batteryMv`; field lain pindah ke AppFrame/metadata atau ditolak. |
| 9 | Alarm payload tidak membawa raw sensor. | Firmware lama alarm membawa `sensorMv[8]`, `nullingProfileId`, `anomalyMaxZx10`, `activeSensorCount`. | Ditolak untuk running LoRa phase 1. | Keputusan final: kontrak menang. Raw sensor/nulling snapshot bukan bagian running uplink; dataset/nulling memakai stage sendiri. |
| 10 | `gasClass`: `0 clearGas`, `1 LPG`, `2 propana`, `3 butana`, `4 metana`, `5 reserve`, `6 anomaly`, lainnya invalid. | Firmware lama `AI_OUTPUT_CLASS_COUNT = 9`, `AI_NORMAL_CLASS = 0`; mapping kelas detail belum sesuai kontrak. | Kontrak masuk; firmware lama hanya referensi normal class 0. | Keputusan final: kontrak menang. Firmware baru harus punya adapter mapping model output ke enum kontrak. |
| 11 | Alarm rule: `gasClass != clearGas && confidence >= GLD_LEL_THRESHOLD_PERCENT`. | Firmware lama memakai `predictedClass != AI_NORMAL_CLASS && confidence >= AI_ALARM_CONFIDENCE_THRESHOLD`, threshold `0.80`. | Adaptasi. | Rule lama selaras secara konsep; ubah confidence menjadi `uint8 0..100`, default `GLD_LEL_THRESHOLD_PERCENT = 30`. |
| 12 | `confidence = GLD_LEL_THRESHOLD_PERCENT` sudah alarm. | Firmware lama memakai float `confidence >= 0.80f`. | Adaptasi. | Keputusan final: bebas float atau integer internal, tetapi makna alarm final selalu `confidence >= threshold`; default awal threshold 30. |
| 12a | Canonical confidence untuk payload/alarm harus compact dan konsisten. | Firmware lama bisa menghasilkan confidence float dari model. | Tambah normalisasi confidence. | Canonical wire value adalah `uint8 0..100` karena 1 byte. Float model hanya input sementara jika ada, tidak ikut dikirim. |
| 13 | Low-confidence gas tetap dikirim sebagai class gas dengan confidence rendah, bukan anomaly. | Firmware lama punya `warningActive` untuk confidence di antara low warning dan alarm. | Adaptasi hati-hati. | Keputusan final: kontrak menang. Warning tidak masuk running payload; server melihat low confidence dari field `confidence`. |
| 14 | Device fault, AI-not-ready, no-decision tidak boleh menjadi alarm gas. | Firmware lama jika model invoke gagal set `alarmActive=false`, `warningActive=false`, dan flag `ai_error`. | Adaptasi sebagian. | Keputusan final: kontrak menang untuk payload/alarm. Jangan kirim alarm dan jangan masukkan `ai_error` ke encrypted running payload. Logging internal boleh. |
| 15 | `batteryMv` adalah `uint16 BE`, `0xFFFF` untuk invalid/unavailable. | Firmware lama memakai `PowerManager::getBatteryStatus().voltage * 1000.0f`; `BatteryStatus` punya `valid`. | Adaptasi. | Jika `valid=false`, kirim `0xFFFF`; jika valid, encode big-endian. |
| 16 | TPL5110 hanya dipakai battery mode. | Firmware lama punya `PowerManager::pulseTpl5110Done()` dan memanggilnya setelah RX window battery mode. | Adaptasi. | Pertahankan behavior battery mode; external mode tidak memakai TPL5110 DONE. |
| 17 | External power ditandai dengan `FLAG_GLD_EXT_POWER` bit 7 pada `SENSOR_DATA`. | Firmware lama punya `PowerManager::isExternal()` dan `PowerMode` external 24V/5V. | Adaptasi. | `isExternal()` menjadi sumber bit `0x80`. |
| 18 | `nodeId` adalah GLD ID dan terlihat di AppFrame/GLDRecord. | Firmware lama `BoardDeploymentConfig.boardId` dipakai sebagai `_deviceId` di `InferenceStage`. | Adaptasi. | `boardId` menjadi `nodeId`. Untuk test/manual gunakan range `0xF000..0xFEFF`. |
| 19 | Destination CH ID harus tersedia untuk AppFrame `dstId`. | Firmware lama tidak terlihat punya CH ID eksplisit untuk LoRa target; LoRa lama direct packet tanpa AppFrame dst. | Tambah baru. | Keputusan final: kontrak menang. Firmware baru perlu config/provisioning `chId` atau default test CH ID. |
| 20 | GLD seq untuk kontrak adalah `uint8` rollover `0..255`. | Firmware lama `LoRaManager::_seq` adalah `uint16_t`. | Adaptasi. | Keputusan final: kontrak menang di wire. Firmware baru boleh simpan counter internal lebih besar, tapi AppFrame `seq` harus `uint8`. |
| 21 | AppFrame memakai `typeFlags`: normal battery `0x10`, normal external `0x90`, alarm battery `0x50`, alarm external `0xD0`. | Firmware lama memakai `LoRaPacketType` enum `0x01..0x04`. | Kontrak masuk; enum lama ditolak. | Keputusan final: kontrak menang. `packetType` lama tidak dipakai sebagai wire format phase 1. |
| 22 | Payload encrypted phase 1: `keyId(1)+nonce(12)+ciphertext(4)+tag(12)=29`. | Firmware lama tidak punya AES-GCM payload pada `LoRaManager`. | Tambah baru. | Keputusan final: kontrak menang. Gunakan mbedTLS/ESP32 API; detail crypto mengikuti kontrak. |
| 23 | AAD: `nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8`. | Firmware lama belum punya AAD atau `recordFlags`. | Tambah baru. | Keputusan final: kontrak menang. `recordFlags` harus dibentuk sama dengan CH: alarm bit 0, ext power bit 4. |
| 24 | Retry alarm harus resend frame/payload yang sama untuk event yang sama. | Firmware lama `sendAlarm()` loop retry memanggil `startTransmit()` dengan struct yang sama dalam satu call; belum ada ACK matching penuh. | Adaptasi konsep, perketat. | Keputusan final: kontrak menang. Cache AppFrame alarm snapshot; retry tidak boleh regenerate nonce/ciphertext/seq. |
| 25 | ACK compact dari CH adalah AppFrame `typeFlags=0x50`, `payloadLen=0`, `seq` sama. | Firmware lama menerima packet di RX window dan hanya log `pktType`, belum matching ACK kontrak. | Tambah baru. | Keputusan final: kontrak menang. RX window lama bisa dipakai, parser ACK harus baru. |
| 26 | Normal data best-effort, alarm meminta ACK. | Firmware lama punya `LORA_ENABLE_ACK=true`, `LORA_MAX_RETRY=3`, `LORA_ACK_TIMEOUT_MS=2000`. | Adaptasi. | Nilai timeout 2000 ms dan retry 3 cocok sebagai default phase 1. |
| 27 | Running payload tidak membawa health/internal status. | Firmware lama punya `sendHealth()` dan `LoRaHealthPayload`. | Ditahan dari running LoRa. | Aman: health/internal status tidak masuk running encrypted payload. Jika dibutuhkan, health harus punya jalur/format sendiri di luar running payload. |
| 28 | Dataset/raw sensor tidak masuk running LoRa. | Firmware lama punya `DatasetStage` dan MQTT dataset publishing. | Masuk firmware baru sebagai dataset/training stage, bukan running LoRa. | Aman: dataset tetap bagian firmware baru, tetapi raw sensor hanya lewat stage dataset/MQTT dan tidak masuk GLD-CH running uplink. |
| 29 | Nulling snapshot tidak masuk running LoRa. | Firmware lama punya `NullingService`, profile, DAC result, dan alarm payload membawa nulling profile ID. | Masuk firmware baru sebagai nulling/setup calibration stage, bukan running LoRa. | Aman: nulling snapshot tidak masuk running payload, tetapi alur `NullingService` firmware lama diikuti penuh untuk service + algoritma. |
| 29a | Running dan dataset production harus memakai baseline kalibrasi yang valid. | Firmware lama memakai nulling profile di inference/dataset, tetapi belum dikunci sebagai kontrak validitas model. | Tambah validasi profile. | Running dan dataset production wajib punya nulling profile valid; dataset membawa `nullingProfileId`; model running wajib cocok dengan active nulling profile. |
| 29b | Nulling ulang mengubah validitas dataset/model untuk device tersebut. | Firmware lama punya profile ID/result dan penyimpanan profile. | Tambah policy versioning. | Setiap nulling sukses menaikkan `nullingProfileId` monotonic. Dataset/model lama untuk profile sebelumnya tidak valid lagi untuk running production device itu. |
| 30 | Modbus bukan bagian GLD-CH uplink phase 1. | Firmware lama punya `ModbusSlaveManager` dan register AI/LoRa/status. | Masuk firmware baru bersama running sebagai local control/observability, bukan uplink GLD-CH. | Aman: Modbus dipertahankan, tetapi tidak mengubah format payload LoRa dan bukan jalur GLD-CH running contract. |
| 30a | Firmware baru butuh full config/control lokal tanpa mencampuri payload LoRa. | Firmware lama punya Modbus register dan command callback. | Tambah full config/control via Modbus. | Modbus boleh mengatur konfigurasi penuh firmware, termasuk secret, dengan guard. Wire protocol GLD-CH tetap kontrak baru. |
| 30b | Config write harus aman dan tidak bocor secret. | Firmware lama punya config store dan Modbus write register, tetapi belum cukup untuk secret/config critical. | Tambah guard write. | Modbus config write memakai unlock window, staged commit, validasi semua field, dan secret readback write-only. |
| 31 | MQTT bukan bagian GLD-CH uplink phase 1 kecuali dataset mode. | Firmware lama punya `MqttManager`, topics dataset/cmd/status. | Masuk firmware baru untuk dataset/training stage. | Aman: MQTT tetap dipakai untuk dataset/training mengikuti firmware lama, tanpa hardcoded credential produksi dan tidak dipakai untuk running LoRa contract. |
| 31a | Dataset harus bisa disinkronkan dengan training di PC/Node-RED. | Firmware lama punya MQTT dataset record/status/summary. | Adaptasi old MQTT flow + metadata. | Dataset output mengikuti alur MQTT lama, tetapi wajib membawa metadata profile seperti `nullingProfileId`, board/node ID, label, seq/timestamp, feature order, dan sensor readings. |
| 32 | Config/provisioning harus memuat key config non-secret template dan production secret tidak masuk git. | Firmware lama `BoardDeploymentConfig` menyimpan board/model/lora/wifi/mqtt/nulling, belum crypto key. | Adaptasi + tambah baru. | Keputusan final: kontrak menang untuk crypto provisioning. Tambah field/loader crypto; jangan hardcode production key di source/git/log. |
| 33 | Test/manual marker harus terlihat di `nodeId` range `0xF000..0xFEFF`. | Firmware lama test/manual marker tidak terlihat di LoRa protocol; `boardId` bebas. | Tambah aturan baru. | Keputusan final: kontrak menang. Bench GLD harus memakai `boardId/nodeId` test range agar server/CH bisa filter. |
| 34 | CRC16 AppFrame wajib untuk frame compact. | Firmware lama RadioLib packet tidak terlihat punya AppFrame CRC layer sendiri. | Tambah baru. | Keputusan final: kontrak menang. Radio CRC tidak menggantikan CRC AppFrame/contract parser. |
| 35 | Production logs tidak boleh print AES key. | Firmware lama banyak serial logs untuk debug, tidak ada crypto key. | Adaptasi. | Tambah aturan logging: boleh print payload length/typeFlags, jangan print production key. |
| 36 | Firmware baru harus bisa dites dengan AES-GCM test vector. | Firmware lama belum punya unit test crypto contract. | Tambah baru. | Wajib host/unit test sebelum radio bench. |
| 37 | GLD tidak membentuk `GLDRecord`; CH yang membentuk record saat onward. | Firmware lama mengirim packet langsung dengan deviceId dan payload fields. | Kontrak masuk. | Keputusan final: kontrak menang. GLD hanya mengirim AppFrame payload 29 byte ke CH. |
| 38 | `config/gld-crypto.env.example` adalah template non-secret repo ini. | Firmware lama tidak punya `.env` crypto template. | Tambah baru. | Source provisioning final boleh ditentukan saat coding, tapi secret tidak masuk git. |
| 39 | Firmware phase 1 tidak mengimplementasikan downlink command execution penuh. | Firmware lama RX window sudah membaca packet tapi belum service command LoRa. | Ditahan dari running uplink awal. | Keputusan final: kontrak menang. RX parser ACK dibutuhkan; command downlink penuh masuk phase berikutnya dan tidak mengubah running payload. |
| 40 | Firmware baru harus punya traceability sebelum copy/adapt modul lama. | Firmware lama adalah repo terpisah yang sudah jalan. | Masuk sebagai policy. | Setiap adaptasi modul lama harus bisa ditunjuk di tabel ini atau revisi tabel lebih dulu. |

---

## 3. Keputusan Modul

| Area | Keputusan |
|---|---|
| PlatformIO / board target | Adaptasi dari firmware lama. |
| Local `lib/` | Boleh diadaptasi supaya build reproducible, tetapi jangan copy `.pio`. |
| `board_pins.h` | Adaptasi sebagai baseline pin GLD. |
| `PowerManager` | Adaptasi sebagai referensi power mode dan TPL5110. |
| `ConfigStore` | Adaptasi pattern, tambah kebutuhan `chId` dan crypto provisioning. |
| `InferenceStage` | Adaptasi flow, refactor `sendLoraResult()` ke kontrak baru. |
| `LoRaManager` | Rewrite interface/protocol; hanya radio init/startTransmit/RX window lama yang dijadikan referensi. |
| `LoRaNormalPayload` lama | Ditolak. |
| `LoRaAlarmPayload` lama | Ditolak. |
| `LoRaHealthPayload` lama | Ditahan dari running payload. Jika health dibutuhkan, buat jalur/format sendiri di luar encrypted running payload. |
| MQTT / Dataset | Masuk firmware baru untuk dataset/training stage. Ikuti alur MQTT lama, tambah metadata `nullingProfileId`, dan jangan hardcode credential produksi. |
| Nulling | Masuk firmware baru sebagai setup calibration stage. Ikuti service + algoritma firmware lama, tetapi nulling snapshot tidak masuk running LoRa. |
| Modbus | Masuk bersama running sebagai full config/control lokal. Gunakan unlock window, staged commit, validasi semua field, dan secret readback write-only. |
| Stage execution | Target firmware lengkap, tetapi implementasi gated: running -> dataset -> nulling. Dataset dan nulling hanya external power. |
| Model/profile binding | Running production hanya boleh memakai model yang cocok dengan active `nullingProfileId`. |

---

## 4. Acceptance Criteria Traceability

Traceability dianggap cukup untuk mulai coding jika:

- semua poin kontrak penting punya keputusan eksplisit,
- semua konflik firmware lama vs kontrak diberi keputusan `kontrak menang`, `adaptasi`, `ditolak`, atau `ditahan`,
- tidak ada field payload lama yang masuk running LoRa phase 1,
- dataset/nulling tetap jelas sebagai bagian firmware baru tetapi bukan running LoRa payload,
- model running production jelas harus cocok dengan active nulling profile,
- Modbus full config/control jelas punya guard dan secret readback write-only,
- rencana firmware phase 1 menunjuk dokumen ini sebagai reference matrix,
- user menyetujui firmware coding secara eksplisit.

---

## 5. Risiko Dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Import firmware lama mentah | Kontrak baru kalah oleh payload lama | Gunakan firmware lama reference-only dan wajib lewat matrix. |
| Payload lama tidak sengaja dipakai | CH/server tidak bisa decrypt/parse sesuai kontrak | Rewrite LoRa wire protocol, jangan reuse `LoRaNormalPayload`/`LoRaAlarmPayload`. |
| Raw sensor masuk running LoRa | Airtime besar dan melanggar kontrak | Raw sensor hanya dataset/MQTT stage, bukan running LoRa. |
| Mapping class AI 9 output vs kontrak 7 value tidak jelas | Gas class salah di server | Buat adapter gas class eksplisit saat coding. |
| Seq lama `uint16` dipakai langsung | AAD/server dedup mismatch | AppFrame `seq` harus `uint8`; internal counter boleh lebih besar. |
| Crypto key hardcoded di source | Secret bocor | Gunakan provisioning/env source; dummy key hanya untuk test. |
| CH ID tidak tersedia | AppFrame `dstId` tidak valid | Tambah config/provisioning `chId` phase 1. |
| Dataset dibuat tanpa profile metadata | Training PC/Node-RED tidak bisa tahu baseline nulling yang dipakai | Dataset wajib membawa `nullingProfileId`. |
| Model lama dipakai setelah nulling ulang | Running production memakai model yang tidak cocok baseline device | Setiap nulling sukses menaikkan profile ID dan model lama untuk profile sebelumnya invalid. |
| Modbus full config salah tulis | Device berubah konfigurasi/secret tanpa sadar | Gunakan unlock window, staged commit, validasi semua field, dan readback secret write-only. |

---

## 6. Next Planning Update

`docs/firmware/03-phase-1-plan.draft.md` harus menyatakan:

- firmware GLD baru adalah contract-first,
- firmware lama adalah reference-only,
- dokumen ini adalah gate sebelum adaptasi modul lama,
- target firmware GLD lengkap tetap gated dengan urutan running -> dataset -> nulling,
- dataset/nulling/MQTT/Modbus masuk firmware baru sesuai stage masing-masing, bukan sebagai running LoRa payload,
- coding firmware belum dimulai sampai user approve.
