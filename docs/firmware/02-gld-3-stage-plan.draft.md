# GLD 3 Stage Firmware Plan Draft

**Status:** draft planning, belum mulai coding firmware  
**Tanggal:** 2026-06-15  
**Scope:** GLD stage architecture: running/inference, dataset/training capture, nulling/setup calibration  
**Sumber teknis:** `D:\GasleakDetectorDesign\firmware`, `C:\Users\asus\Downloads\ApplyGasleak-main\ApplyGasleak-main\src\Gasleak\Board1`, `docs/design/gld/design.updated.draft.md`, dan `docs/design/gld-ch/payload-contract.draft.md`

Dokumen ini mengunci arsitektur 3 stage GLD sebelum firmware dibuat. Tujuannya agar firmware baru tidak hanya mengejar payload LoRa, tetapi tetap membawa runtime GLD lengkap dengan batas stage yang jelas.

---

## 1. Ringkasan Keputusan

- Firmware GLD baru memiliki 3 stage utama:
  1. `running` / `inference`,
  2. `dataset` / `training capture`,
  3. `nulling` / `setup calibration`.
- Source runtime stage mengikuti firmware lama, tetapi running LoRa mengikuti kontrak baru.
- `ApplyGasleak Board1` menjadi referensi cara mengambil hasil model:
  - 8 voltage sensor dinormalisasi dengan scaler params,
  - input dikirim ke TensorFlow Lite,
  - model di-invoke,
  - output argmax menjadi `predicted_class`,
  - max score menjadi confidence.
- Running production wajib punya active nulling profile valid dan model metadata yang cocok dengan profile tersebut.
- Dataset production wajib membawa metadata active nulling profile ID.
- Nulling ulang membuat profile baru; dataset/model lama untuk profile sebelumnya tidak valid untuk running production.
- Dataset dan nulling hanya boleh berjalan di external power.

---

## 2. Running / Inference Stage

### 2.1 Input Model

Flow inference mengikuti pola invoke model dari `ApplyGasleak Board1`, tetapi urutan channel/feature mengikuti `docs/design/gld/design.updated.draft.md`:

1. Ambil 8 voltage sensor dalam urutan target desain:
   ```text
   MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
   ```
2. Gunakan `movingAverageVoltage` / `voltage_after_gain_compensation` sebagai nilai sensor final untuk feature processing.
3. Hitung scaled feature:
   ```c
   feature[i] = (sensor_voltage[i] - featureMean[i]) / featureStd[i];
   ```
4. Copy 8 float ke TensorFlow Lite input buffer.
5. Jalankan `interpreter->Invoke()`.
6. Ambil output class dengan nilai probabilitas tertinggi.
7. Simpan:
   - `rawModelClassIndex`,
   - `confidenceFloat`,
   - `confidencePercent uint8 0..100`,
   - `inferenceTimeMs`,
   - `inferenceValid`.

Referensi kode lama:

- `ApplyGasleak-main\src\Gasleak\Board1\Gasleak.cpp`: referensi historis untuk scaling 8 voltage, copy ke input model, dan invoke model; bukan sumber kebenaran urutan feature final.
- `ApplyGasleak-main\src\Gasleak\Board1\NeuralNetwork.cpp`: `predict(float &confidence_score)` menjalankan TFLite invoke dan argmax.
- `ApplyGasleak-main\src\Gasleak\Board1\scaler_params.cc`: `feature_means[8]` dan `feature_stds[8]`.
- `docs/design/gld/design.updated.draft.md`: sumber kebenaran urutan channel/feature final untuk implementasi.

### 2.2 Model Metadata

`ApplyGasleak Board1` belum punya metadata model untuk `nullingProfileId`, `modelProfileId`, atau mapping class gas. Firmware baru menambahkan sidecar JSON per model.

Sidecar JSON minimal:

```json
{
  "modelProfileId": "board1-profile-5-v1",
  "boundNullingProfileId": 5,
  "classCount": 5,
  "classMap": {
    "0": "clearGas",
    "1": "LPG",
    "2": "propana",
    "3": "butana",
    "4": "metana"
  },
  "scalerProfileId": "board1-profile-5-scaler-v1",
  "featureOrder": ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"],
  "lelThresholdPercent": 30
}
```

Aturan:

- Model binary dan sidecar JSON adalah pasangan.
- Model tanpa sidecar valid tidak boleh dipakai untuk production running.
- Mapping `predicted_class` ke `gasClass` kontrak berasal dari model metadata, bukan hardcoded global firmware.
- `featureOrder` wajib sama dengan urutan channel/feature di `docs/design/gld/design.updated.draft.md`.
- Jika class dari model tidak ada di `classMap`, firmware harus memperlakukan hasil sebagai invalid/anomaly sesuai policy phase implementasi, dan tidak boleh membuat alarm produksi tanpa mapping valid.
- Contoh `classMap` di atas adalah target model final sesuai kontrak GLD. Audit terhadap `Board1.xlsx` hanya menemukan label `Udara`, `Metana`, dan `LPG`, sehingga `Board1` tidak boleh dianggap sudah memiliki metadata class final.

### 2.3 Model/Profile Binding

Running production hanya boleh jalan jika:

```text
activeNullingProfileId == modelMetadata.boundNullingProfileId
```

Jika mismatch:

- production running diblok,
- LoRa production normal/alarm tidak dikirim,
- status internal/log menunjukkan model-profile mismatch,
- operator perlu memasang model yang dibangun dari dataset dengan nulling profile aktif.

### 2.4 Alarm Rule

Threshold operator disebut `LEL threshold`, default awal:

```c
GLD_LEL_THRESHOLD_PERCENT = 30
```

Pada phase ini threshold tersebut diterapkan pada confidence model `0..100`.

Rule:

```c
normal = (gasClass == clearGas) ||
         (gasClass != clearGas && confidencePercent < GLD_LEL_THRESHOLD_PERCENT);

alarm = (gasClass != clearGas &&
         confidencePercent >= GLD_LEL_THRESHOLD_PERCENT);
```

Boundary:

- confidence `29` dengan gas non-clear = normal,
- confidence `30` dengan gas non-clear = alarm,
- clearGas selalu normal walaupun confidence tinggi.

### 2.5 Running LoRa

Running LoRa tetap mengikuti kontrak GLD-CH:

- plaintext 4 byte: `gasClass`, `confidence`, `batteryMv`,
- encrypted payload 29 byte AES-GCM,
- raw sensor, dataset, health, nulling snapshot, model metadata, dan internal status tidak masuk payload running.

---

## 3. Dataset / Training Capture Stage

Dataset hanya mengumpulkan data. Training/model build dilakukan di PC, Node-RED, atau device lain di luar firmware GLD.

### 3.1 Start Condition

Dataset production hanya boleh mulai jika:

- power mode external,
- active nulling profile valid,
- MQTT config valid,
- dataset command valid.

Firmware baru tidak menjalankan nulling otomatis sebelum dataset start. Opsi lama seperti `run_nulling_before_start` tidak dipakai sebagai behavior production karena nulling adalah calibration event, bukan rutinitas sebelum dataset.

### 3.2 MQTT Flow

Dataset MQTT mengikuti flow firmware lama:

- command start/stop,
- publish command ACK,
- publish dataset status,
- publish dataset record,
- publish dataset summary.

Topic pattern mengikuti firmware lama:

- `gas-leak-detector/<device>/dataset`,
- `gas-leak-detector/<device>/dataset/data`,
- `gas-leak-detector/<device>/dataset/status`,
- `gas-leak-detector/<device>/dataset/summary`.

### 3.3 Dataset Record

Setiap record dataset wajib membawa metadata cukup agar training tetap sinkron walau record berdiri sendiri.

Field minimum:

```json
{
  "device_id": "node-01",
  "node_id": 1,
  "mode": "DATASET",
  "seq": 42,
  "timestamp_ms": 123456,
  "label": "LPG",
  "nulling_profile_id": 5,
  "model_profile_id": "optional-current-or-target",
  "firmware_version": "draft",
  "sensor_voltage": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
  "sensor_gain": [64, 64, 64, 64, 64, 64, 64, 64],
  "feature_order": ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
}
```

Aturan:

- `sensor_voltage[8]` memakai `movingAverageVoltage` / `voltage_after_gain_compensation`, bukan raw ADC count.
- `sensor_gain[8]` memakai gain ADS1256 per sensor saat sample diambil.
- `feature_order[8]` adalah canonical mapping sensor untuk setiap index `sensor_voltage` dan harus sama dengan urutan channel/feature di `docs/design/gld/design.updated.draft.md`.
- `nulling_profile_id` wajib di setiap record; field ini adalah ID monotonic profile aktif dan tidak dipisah lagi menjadi versi terpisah.
- `power_mode` tidak dikirim per record karena dataset hanya boleh berjalan di external power.
- Dataset yang dibuat dengan profile 5 hanya valid untuk model yang menyatakan `boundNullingProfileId = 5`.

---

## 4. Nulling / Setup Calibration Stage

Nulling mengikuti service + algoritma firmware lama, tetapi profile ID baru memakai monotonic counter.

### 4.1 Start Condition

Nulling production hanya boleh mulai jika:

- power mode external,
- sensor/ADS/DAC siap,
- tidak sedang dataset recording,
- tidak sedang running cycle yang harus selesai,
- operator/command masuk dari Serial, MQTT, atau Modbus sesuai gate firmware.

### 4.2 Full 8 Channel Flow

Alur full nulling:

1. Load `nullingThresholdVoltage` dari config, fallback ke default.
2. Reset DAC semua channel ke nilai awal.
3. Jika diminta, jalankan fan sebelum nulling.
4. Set ADS1256 ke gain nulling.
5. Buat profile baru.
6. Loop channel `0..7`.
7. Untuk tiap channel:
   - set DAC channel ke 0,
   - baseline prescan dari DAC 0 sampai `NULLING_BASELINE_PRESCAN_MAX`,
   - hitung baseline average, baseline min/max, dan noise range,
   - exponential search untuk menemukan rentang DAC yang melewati threshold,
   - binary search dalam rentang,
   - confirm candidate dengan confirm window,
   - tulis DAC final jika success,
   - simpan `NullingResult`.
8. Jika satu channel gagal, `allSuccess=false`, abort sisa channel, dan active profile tidak diganti.
9. Jika semua channel sukses dan save enabled, simpan profile sebagai active profile.
10. Reset ADS gain normal.

### 4.3 Success Rule

Nulling sukses jika:

- semua 8 channel success,
- profile tersimpan sebagai active profile,
- monotonic `nullingProfileId` naik.

Jika nulling gagal:

- active profile lama tetap dipakai,
- model/dataset binding lama tetap berlaku,
- error dicatat untuk operator.

### 4.4 Profile Versioning

Firmware baru tidak memakai `(uint16_t)millis()` sebagai profile ID.

Rule baru:

```text
nextNullingProfileId = lastNullingProfileId + 1
```

Konsekuensi:

- setelah profile berubah dari 5 ke 6, model dengan `boundNullingProfileId=5` tidak valid lagi untuk running production,
- dataset baru harus membawa profile 6,
- PC/Node-RED training menghasilkan model baru yang bind ke profile 6.

---

## 5. Acceptance Criteria

Running:

- class 0 selalu normal.
- gas non-clear confidence 29 normal jika threshold 30.
- gas non-clear confidence 30 alarm jika threshold 30.
- mismatch active nulling profile vs model metadata memblok production TX.
- running payload tetap 4 byte plaintext dan 29 byte encrypted.

Dataset:

- dataset start tanpa active nulling profile valid ditolak.
- dataset hanya berjalan di external power.
- setiap MQTT dataset record membawa 8 `sensor_voltage` berbasis moving average / voltage after gain compensation, `feature_order`, dan `nulling_profile_id`.
- dataset tidak menjalankan nulling otomatis sebelum start.

Nulling:

- semua channel sukses membuat active profile baru dengan monotonic ID.
- satu channel gagal membuat nulling gagal dan tidak mengganti active production profile.
- nulling ulang membuat dataset/model lama untuk profile sebelumnya tidak valid untuk running production.

Regression:

- raw sensor, dataset, nulling snapshot, model metadata, dan health tidak masuk running LoRa payload.
- firmware coding belum dimulai dari dokumen ini.
