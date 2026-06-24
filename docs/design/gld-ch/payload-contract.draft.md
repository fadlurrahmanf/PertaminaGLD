# GLD-CH-Server Payload Contract Draft

**Status:** draft kontrak hasil diskusi  
**Tanggal:** 2026-06-15  
**Scope:** running uplink GLD -> CH -> Gateway/Server/Node-RED  
**Tidak mengubah:** `docs/design/gld/design.md` dan `docs/design/ch/design.md`

Dokumen ini menjadi kontrak integrasi antara firmware GLD, firmware CH, gateway, dan Node-RED/server untuk payload running. Desain import GLD dan CH tetap dianggap source/reference terpisah; dokumen ini menjahit keputusan integrasi terbaru agar implementasi firmware tidak berbeda tafsir.

Semua integer multibyte di wire format memakai big-endian.

---

## 1. Ringkasan Keputusan

- GLD running plaintext payload adalah tepat 4 byte: `gasClass`, `confidence`, `batteryMv`.
- Payload GLD dienkripsi end-to-end dari GLD sampai Node-RED/server.
- CH tidak decrypt, tidak parse, dan tidak mengubah payload GLD.
- Enkripsi phase 1 memakai `AES-128-GCM` dengan payload encrypted tetap 29 byte.
- CH menyimpan latest cache opaque per GLD dan meneruskan data sebagai `GLDRecord`.
- Normal server pull memakai `CLUSTER_DATA_RESPONSE (0x31)` dan dapat membawa beberapa `GLDRecord`.
- Alarm push memakai `SENSOR_DATA (0x10) | FLAG_ALARM_ACK (0x40)` dan membawa tepat satu `GLDRecord`.
- Recovery clear dipush sebagai satu `GLDRecord` tanpa `FLAG_ALARM_ACK`.
- Threshold alarm operator disebut `LEL threshold`, default awal `30`, dan diterapkan ke `confidence` model `0..100`.
- Test/manual GLD memakai reserved GLD ID range yang terlihat di `nodeId`.
- Firmware belum dimulai dari dokumen ini; ini hanya kontrak draft untuk dikonfirmasi sebelum implementasi.

---

## 2. GLD Running Plaintext Payload

Plaintext sebelum enkripsi selalu 4 byte:

| Offset | Field | Size | Encoding | Keterangan |
|---:|---|---:|---|---|
| 0 | `gasClass` | 1 | `uint8` | Kelas gas hasil inference |
| 1 | `confidence` | 1 | `uint8` | Skor confidence `0..100` |
| 2..3 | `batteryMv` | 2 | `uint16 BE` | Tegangan baterai GLD dalam mV |

### 2.1 `gasClass`

| Value | Nama | Status |
|---:|---|---|
| `0` | `clearGas` | Valid, tidak alarm |
| `1` | `LPG` | Valid |
| `2` | `propana` | Valid |
| `3` | `butana` | Valid |
| `4` | `metana` | Valid |
| `5` | `reserve` | Reserved, tidak diproduksi firmware normal |
| `6` | `anomaly` / `unknown` | Valid untuk gas unknown/anomaly |
| `7..255` | reserved / invalid | Tidak valid untuk phase 1 |

Catatan:

- Low-confidence gas tetap dikirim sebagai class gas yang terdeteksi dengan confidence rendah.
- Low-confidence gas tidak otomatis diubah menjadi `anomaly`.
- Device fault, AI-not-ready, dan no-decision tidak boleh di-encode sebagai alarm gas.
- `gasClass = 5` tidak boleh diproduksi oleh firmware normal phase 1. Jika server menerima nilai ini, server harus menandainya sebagai reserved/invalid untuk analisis, bukan alarm produksi otomatis.

### 2.2 `confidence`

`confidence` adalah integer `0..100`.

Nilai di luar `0..100` invalid dan harus ditolak atau ditandai invalid oleh server setelah decrypt.

### 2.3 `batteryMv`

`batteryMv` adalah `uint16 BE`.

| Value | Makna |
|---:|---|
| `0..65534` | Tegangan baterai dalam mV |
| `0xFFFF` | Invalid / unavailable / tidak terbaca |

Untuk GLD external power, nilai baterai tetap boleh dikirim jika tersedia. Jika tidak tersedia, gunakan `0xFFFF`.

---

## 3. Alarm Rule GLD

Alarm ditentukan oleh GLD sebelum payload dikirim:

```c
alarm = (gasClass != 0) && (confidence >= GLD_LEL_THRESHOLD_PERCENT);
```

Aturan:

- Default awal `GLD_LEL_THRESHOLD_PERCENT = 30`.
- `confidence = 30` sudah termasuk alarm jika threshold masih default 30.
- Istilah operatornya adalah `LEL threshold`, tetapi nilai yang dibandingkan pada phase ini adalah confidence model `0..100`, bukan konsentrasi gas fisik yang didecrypt dari payload.
- Threshold harus ditempatkan sebagai konstanta/config global yang mudah diubah.
- Normal dikirim jika `gasClass == clearGas`, atau jika `gasClass != clearGas` tetapi `confidence < GLD_LEL_THRESHOLD_PERCENT`.
- Hanya kejadian alarm yang boleh mengaktifkan `FLAG_ALARM_ACK` di `AppFrame.typeFlags`.
- Device fault, AI-not-ready, dan no-decision tidak masuk `alarmQueue`.
- Local alarm GLD boleh tetap aktif sesuai kebijakan GLD, tetapi kontrak LoRa alarm mengikuti rule di atas.

---

## 4. Encrypted GLD Payload

Payload GLD yang masuk ke `AppFrame.payload` adalah payload encrypted 29 byte:

| Offset | Field | Size | Keterangan |
|---:|---|---:|---|
| 0 | `keyId` | 1 | ID key untuk decrypt di server |
| 1..12 | `nonce` | 12 | Nonce AES-GCM 96-bit |
| 13..16 | `ciphertext` | 4 | Ciphertext dari plaintext 4 byte |
| 17..28 | `tag` | 12 | AES-GCM authentication tag 96-bit |

```text
encryptedPayloadLen = 1 + 12 + 4 + 12 = 29 byte
```

Ketentuan:

- Cipher: `AES-128-GCM`.
- AES key size: 16 byte.
- GCM tag length: 12 byte.
- Nonce length: 12 byte.
- Plaintext length: 4 byte.
- Ciphertext tidak memakai padding.
- `keyId` tidak terenkripsi, tetapi ikut dilindungi melalui AAD.
- CH wajib memperlakukan 29 byte ini sebagai opaque bytes.

### 4.1 Nonce Policy

Phase 1 memakai random nonce 12 byte dari hardware RNG ESP32.

Larangan penting:

- Untuk key yang sama, nonce tidak boleh berulang.
- Retry alarm untuk event yang sama harus mengirim ulang encrypted payload/frame yang sama, bukan membuat nonce/ciphertext baru.

Alasan: AES-GCM rusak jika kombinasi key dan nonce dipakai ulang.

### 4.2 AAD

AAD adalah data yang tidak dienkripsi, tetapi diverifikasi oleh AES-GCM.

Format AAD byte-presisi:

| Offset | Field | Size | Source |
|---:|---|---:|---|
| 0..1 | `nodeId` | 2 | `GLDRecord.nodeId`, `uint16 BE` |
| 2 | `gldSeq` | 1 | `GLDRecord.seq` |
| 3 | `recordFlags` | 1 | `GLDRecord.flags` |
| 4 | `keyId` | 1 | `encryptedPayload[0]` |

```text
AAD = nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8
AAD length = 5 byte
```

Aturan:

- `gldSeq` adalah sequence asal GLD, bukan sequence MESH, bukan request server.
- `recordFlags` harus stabil dari CH ke server karena ikut AAD.
- Server harus reconstruct AAD dari `GLDRecord` dan `keyId`.
- CH tidak perlu tahu isi AAD sebagai crypto concept, tetapi CH wajib meneruskan field `nodeId`, `seq`, `flags`, dan payload tanpa modifikasi.

---

## 5. Key Provisioning

Phase 1 memakai satu global AES key untuk semua GLD dengan `keyId = 1`.

Contoh `.env` lokal/provisioning:

```env
GLD_KEY_ID=1
GLD_AES128_KEY_HEX=00112233445566778899AABBCCDDEEFF
GLD_AES_GCM_TAG_LEN=12
```

Template non-secret disediakan di:

```text
config/gld-crypto.env.example
```

Aturan:

- `.env` tidak boleh masuk git.
- `.env.example` boleh masuk git tanpa secret.
- Key produksi tidak boleh ditulis di dokumen, log, chat, atau source code yang masuk git.
- `GLD_AES128_KEY_HEX` harus 32 hex chars atau 16 byte.
- `keyId` disiapkan untuk rotasi key berikutnya.

Risiko global key:

- Jika satu key bocor, semua GLD phase 1 terdampak.
- Untuk phase berikutnya, kontrak dapat dinaikkan ke per-device key tanpa mengubah wire layout karena `keyId` sudah ada.

---

## 6. AppFrame Usage

`AppFrame` adalah outer transport untuk STAR dan MESH. Format detail tetap mengikuti desain CH.

Field yang relevan untuk kontrak ini:

| Field | Size | Keterangan |
|---|---:|---|
| `typeFlags` | 1 | `msgType` bit `0..5`, `FLAG_ALARM_ACK` bit 6, `FLAG_GLD_EXT_POWER` bit 7 |
| `srcId` | 2 | Pengirim frame |
| `dstId` | 2 | Tujuan frame |
| `seq` | 1 | Sequence pengirim frame |
| `payloadLen` | 1 | Panjang payload |
| `payload` | N | Payload compact |
| `crc16` | 2 | CRC16 AppFrame |

### 6.1 `typeFlags`

| Kasus | `typeFlags` | Makna |
|---|---:|---|
| GLD normal battery | `0x10` | `SENSOR_DATA` normal |
| GLD normal external | `0x90` | `SENSOR_DATA` normal + external power |
| GLD alarm battery | `0x50` | `SENSOR_DATA` alarm + ACK request |
| GLD alarm external | `0xD0` | `SENSOR_DATA` alarm + external power + ACK request |
| Normal batch to server | `0x31` | `CLUSTER_DATA_RESPONSE` |

Catatan:

- `0x50`, `0x90`, dan `0xD0` adalah `typeFlags`, bukan `msgType`.
- `msgType = typeFlags & 0x3F`.
- Semua varian GLD `0x10/0x50/0x90/0xD0` memiliki `msgType = SENSOR_DATA (0x10)`.
- `FLAG_GLD_EXT_POWER` hanya bermakna pada `SENSOR_DATA`.

---

## 7. GLDRecord Wire Format

`GLDRecord` adalah unit data GLD yang dipakai CH saat mengirim normal batch, alarm push, dan recovery clear.

```c
struct GLDRecord {
  uint16_t nodeId;      // GLD ID, big-endian on wire
  uint8_t  seq;         // original GLD seq
  uint8_t  flags;       // CH/server-visible metadata
  uint8_t  payloadLen;  // encrypted payload length
  uint8_t  payload[N];  // encrypted opaque GLD payload
};
```

Wire layout:

| Offset | Field | Size | Encoding |
|---:|---|---:|---|
| 0..1 | `nodeId` | 2 | `uint16 BE` |
| 2 | `seq` | 1 | `uint8` |
| 3 | `flags` | 1 | `uint8` |
| 4 | `payloadLen` | 1 | `uint8` |
| 5.. | `payload` | N | opaque bytes |

For phase 1:

```text
payloadLen = 29
recordSize = 5 + 29 = 34 byte
```

### 7.1 `record.flags`

| Bit | Mask | Name | Source | Keterangan |
|---:|---:|---|---|---|
| 0 | `0x01` | `NC_FLAG_ALARM` | `AppFrame.typeFlags & 0x40` | `1` jika alarm |
| 1 | `0x02` | reserved | - | harus `0` |
| 2 | `0x04` | reserved | - | harus `0` |
| 3 | `0x08` | reserved | - | harus `0` |
| 4 | `0x10` | `NC_FLAG_EXT_POWER` | `AppFrame.typeFlags & 0x80` | `1` jika GLD external power |
| 5..7 | `0xE0` | reserved | - | harus `0` |

Aturan:

- CH membentuk `record.flags` dari metadata `AppFrame.typeFlags`.
- CH tidak boleh menambahkan flag internal yang berubah-ubah ke `record.flags`.
- Server memakai `record.flags` untuk reconstruct AAD.
- Bits reserved harus `0` pada phase 1.

---

## 8. CH NodeCache

CH menyimpan latest cache per GLD dan payload tetap opaque.

```c
#define GLD_PAYLOAD_MAX 64

struct NodeCache {
  uint16_t nodeId;
  uint8_t  used;
  uint8_t  currentSeq;
  uint8_t  sentSeq;
  uint8_t  flags;
  uint32_t lastSeenMs;
  uint32_t lastSentMs;
  uint8_t  payloadLen;
  uint8_t  payload[GLD_PAYLOAD_MAX];
};
```

Aturan cache:

- `nodeId` berasal dari `AppFrame.srcId` GLD.
- `currentSeq` berasal dari `AppFrame.seq` GLD.
- `sentSeq` adalah seq terakhir yang sukses dikirim onward.
- `currentSeq != sentSeq` berarti latest record belum terkirim onward.
- `payloadLen` harus `<= GLD_PAYLOAD_MAX`.
- Untuk running encrypted phase 1, `payloadLen` normalnya harus `29`.
- CH drop atau tandai invalid frame jika `payloadLen > GLD_PAYLOAD_MAX`.
- CH tidak menyimpan hasil decrypt.
- CH tidak menurunkan `gasClass`, `confidence`, `batteryMv`, health, wake, raw sensor, dataset, nulling, atau AI status dari payload encrypted.

Seq `uint8` wrap-around:

- `seq` rollover `0..255`.
- Phase 1 boleh memakai dedup sederhana: terima frame jika `seq != currentSeq` atau jika cache belum used.
- Aturan newer/stale yang lebih ketat bisa ditambahkan saat firmware CH sudah mempunyai kebutuhan anti-replay lokal.

---

## 9. Normal Pull To Server/Gateway

Normal non-alarm ke server/gateway memakai:

```text
msgType = CLUSTER_DATA_RESPONSE (0x31)
```

Payload:

| Offset | Field | Size | Encoding |
|---:|---|---:|---|
| 0..1 | `requestId` | 2 | `uint16 BE` |
| 2 | `status` | 1 | `uint8` |
| 3..4 | `chBatteryMv` | 2 | `uint16 BE` |
| 5 | `recordCount` | 1 | `uint8` |
| 6.. | `records` | variable | repeated `GLDRecord` |

Aturan:

- `CLUSTER_DATA_RESPONSE` adalah response dari CH target terhadap server/gateway pull.
- Hanya record normal/non-alarm yang masuk normal response.
- Frame ini tidak memakai `FLAG_ALARM_ACK`.
- `FLAG_GLD_EXT_POWER` tidak dipasang di outer `CLUSTER_DATA_RESPONSE` karena satu response bisa berisi beberapa GLD dengan status power berbeda.
- Status power per GLD berada di `GLDRecord.flags`.
- `recordCount` adalah jumlah `GLDRecord` yang dimasukkan.

### 9.1 Capacity

MESH payload max:

```text
MESH_MAX_PAYLOAD = 80 byte
CLUSTER_DATA_RESPONSE header = 6 byte
GLDRecord phase 1 = 34 byte
capacity = floor((80 - 6) / 34) = 2 record
```

Dengan payload encrypted 29 byte, normal response muat maksimal 2 GLD per frame.

---

## 10. Alarm Push To Server/Gateway

Alarm ke server/gateway memakai:

```text
msgType = SENSOR_DATA (0x10)
FLAG_ALARM_ACK = 1
typeFlags = 0x50 atau 0xD0
payload = exactly one GLDRecord
```

Aturan:

- Alarm push bukan `CLUSTER_DATA_RESPONSE`.
- Alarm push tidak membawa `requestId`, `status`, `chBatteryMv`, atau `recordCount`.
- Alarm push membawa tepat satu `GLDRecord`.
- Outer MESH `AppFrame.srcId` adalah CH ID pengirim MESH.
- Identitas GLD asli berada di `GLDRecord.nodeId`.
- Outer MESH `AppFrame.seq` untuk hop ACK/retry.
- `GLDRecord.seq` untuk identitas event/data GLD.
- Jika `alarmQueue` penuh, CH tidak boleh ACK GLD; GLD harus retry.
- ACK ke GLD berarti CH menerima alarm ke queue/processing, bukan bukti server sudah menerima alarm.

Retry alarm:

- Retry event yang sama memakai `GLDRecord.nodeId` dan `GLDRecord.seq` yang sama.
- Encrypted payload untuk event yang sama harus sama.
- Server dedup harus mencegah retry menjadi event alarm baru.

---

## 11. Recovery Clear Push

Jika GLD yang sebelumnya alarm mengirim valid clear/non-alarm, CH harus clear `NC_FLAG_ALARM` dan push recovery clear segera.

Format:

```text
msgType = SENSOR_DATA (0x10)
FLAG_ALARM_ACK = 0
payload = exactly one GLDRecord
GLDRecord.flags bit0 alarm = 0
```

Aturan:

- Recovery clear tidak memakai `FLAG_ALARM_ACK`.
- Recovery clear adalah record baru dengan `alarm = 0`, bukan penghapusan cache diam-diam.
- Reliability phase 1 boleh best-effort dan tetap akan terkoreksi oleh normal pull berikutnya.

---

## 12. Server Decode And Dedup

Server/gateway parser harus branch berdasarkan outer `msgType`:

- `CLUSTER_DATA_RESPONSE (0x31)`: parse response header lalu repeated `GLDRecord`.
- `SENSOR_DATA (0x10) + FLAG_ALARM_ACK`: parse exactly one alarm `GLDRecord`.
- `SENSOR_DATA (0x10)` tanpa `FLAG_ALARM_ACK` untuk recovery clear: parse exactly one `GLDRecord`.

Server decrypt:

1. Ambil `GLDRecord.payload`.
2. Validasi `payloadLen == 29`.
3. Ambil `keyId = payload[0]`.
4. Cari AES key berdasarkan `keyId`.
5. Reconstruct AAD:
   ```text
   nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8
   ```
6. AES-128-GCM decrypt ciphertext 4 byte dengan nonce 12 byte dan tag 12 byte.
7. Parse plaintext 4 byte menjadi `gasClass`, `confidence`, `batteryMv`.
8. Validasi enum/range.

Dedup alarm/retry:

```text
dedupKey = clusterId + nodeId + GLDRecord.seq + eventKind
```

Optional:

```text
dedupKey += payloadHash
```

`AppFrame.seq` dari hop CH/MESH tidak boleh menjadi identitas utama event GLD.

---

## 13. Test And Manual Isolation

Karena payload encrypted, marker test/manual harus terlihat di metadata luar.

Reserved GLD ID:

| Range | Fungsi |
|---:|---|
| `0x0001..0xEFFF` | Production GLD |
| `0xF000..0xFEFF` | Test/manual GLD |
| `0xFF00..0xFFFF` | System/future reserved |

Aturan:

- Test/manual GLD memakai `nodeId` dalam range `0xF000..0xFEFF`.
- Server harus bisa filter event test agar tidak dihitung sebagai alarm produksi.
- Test/manual marker tidak boleh hanya disimpan di encrypted payload.
- Dokumentasi operator harus menjelaskan cara membedakan test/manual dari production.

---

## 14. Future Downlink Placeholder

Downlink belum menjadi scope implementasi utama kontrak ini, tetapi arah flow sudah disiapkan:

```text
SERVER_NODE_COMMAND -> CH pending downlink -> NODE_DOWNLINK -> GLD
```

Command class rencana:

- request data,
- konfigurasi parameter GLD,
- switch mode/state GLD: `running`, `dataset`, `nulling`.

Aturan awal:

- Battery mode: CH mengirim `NODE_DOWNLINK` saat RX window setelah GLD mengirim `SENSOR_DATA`.
- External power mode: CH boleh mengirim `NODE_DOWNLINK` langsung berdasarkan `NC_FLAG_EXT_POWER`.
- Jika ada alarm, ACK alarm compact harus diprioritaskan sebelum pending downlink.

Detail payload downlink akan dikunci di kontrak terpisah sebelum implementasi.

---

## 15. Constants Naming

Nama konstanta phase 1 harus konsisten di GLD, CH, gateway, dan server.

### 15.1 GLD / Shared Constants

```c
static const uint8_t GLD_GAS_CLEAR    = 0;
static const uint8_t GLD_GAS_LPG      = 1;
static const uint8_t GLD_GAS_PROPANE  = 2;
static const uint8_t GLD_GAS_BUTANE   = 3;
static const uint8_t GLD_GAS_METHANE  = 4;
static const uint8_t GLD_GAS_RESERVED = 5;
static const uint8_t GLD_GAS_ANOMALY  = 6;

static const uint8_t GLD_LEL_THRESHOLD_PERCENT = 30;
static const uint8_t GLD_RUNNING_PLAINTEXT_LEN = 4;
static const uint8_t GLD_ENCRYPTED_PAYLOAD_LEN = 29;
static const uint8_t GLD_AES_GCM_NONCE_LEN = 12;
static const uint8_t GLD_AES_GCM_TAG_LEN = 12;
static const uint8_t GLD_AES_KEY_LEN = 16;

static const uint16_t GLD_BATTERY_MV_INVALID = 0xFFFF;
```

### 15.2 CH / Record Constants

```c
static const uint8_t GLD_RECORD_HEADER_LEN = 5;
static const uint8_t GLD_PAYLOAD_MAX = 64;

static const uint8_t NC_FLAG_ALARM = 0x01;
static const uint8_t NC_FLAG_EXT_POWER = 0x10;
```

### 15.3 Test ID Constants

```c
static const uint16_t GLD_PRODUCTION_ID_MIN = 0x0001;
static const uint16_t GLD_PRODUCTION_ID_MAX = 0xEFFF;
static const uint16_t GLD_TEST_ID_MIN = 0xF000;
static const uint16_t GLD_TEST_ID_MAX = 0xFEFF;
static const uint16_t GLD_SYSTEM_ID_MIN = 0xFF00;
static const uint16_t GLD_SYSTEM_ID_MAX = 0xFFFF;
```

---

## 16. AES-GCM Test Vector

Test vector ini memakai dummy key yang aman masuk git. Jangan memakai nilai ini untuk produksi.

Parameter:

| Field | Value |
|---|---|
| `keyId` | `0x01` |
| AES-128 key | `000102030405060708090A0B0C0D0E0F` |
| `nodeId` | `0xF001` |
| `gldSeq` | `0x2A` |
| `recordFlags` | `0x11` (`NC_FLAG_ALARM | NC_FLAG_EXT_POWER`) |
| nonce | `101112131415161718191A1B` |
| plaintext | `01500E74` |
| plaintext meaning | `gasClass=1 LPG`, `confidence=80`, `batteryMv=3700` |
| AAD | `F0012A1101` |
| ciphertext | `C57E0DDB` |
| tag 12 byte | `F88ABEC591E9F5BFAD982A6C` |
| encrypted payload 29 byte | `01101112131415161718191A1BC57E0DDBF88ABEC591E9F5BFAD982A6C` |

Expected encrypted payload layout:

```text
01                                      keyId
10 11 12 13 14 15 16 17 18 19 1A 1B   nonce
C5 7E 0D DB                             ciphertext
F8 8A BE C5 91 E9 F5 BF AD 98 2A 6C   tag
```

Catatan:

- Test vector dihitung dengan Node.js `crypto` memakai `aes-128-gcm` dan `authTagLength = 12`.
- Node-RED phase 1 memakai Function Node langsung dengan Node.js `crypto`; helper module baru dibuat nanti jika flow sudah stabil.

---

## 17. Phase 1 Firmware Scope

Firmware phase 1 yang disarankan setelah kontrak disetujui:

### GLD

- Bentuk plaintext 4 byte dari hasil inference.
- Tentukan alarm berdasarkan rule `gasClass != 0 && confidence >= GLD_LEL_THRESHOLD_PERCENT`.
- Bentuk `recordFlags`/metadata AppFrame yang cocok dengan status alarm dan power.
- Encrypt payload memakai AES-128-GCM 29 byte.
- Kirim `SENSOR_DATA` normal/alarm ke CH.
- Untuk retry alarm event yang sama, kirim ulang frame/payload yang sama.

### CH

- Validasi `AppFrame`.
- ACK alarm jika queue/processing menerima alarm.
- Update `NodeCache` opaque.
- Forward alarm sebagai one-record alarm push.
- Push recovery clear sebagai one-record clear.
- Jawab server pull memakai `CLUSTER_DATA_RESPONSE` maksimal 2 GLDRecord per frame untuk payloadLen 29.

### Server / Node-RED

- Parse `CLUSTER_DATA_RESPONSE` dan `SENSOR_DATA` one-record.
- Reconstruct AAD.
- Decrypt AES-128-GCM dengan tag 12 byte.
- Validasi plaintext.
- Dedup alarm/retry.
- Filter test/manual ID range.

---

## 18. Implementation Notes Before Firmware

Item berikut bukan blocker wire protocol, tetapi perlu diputuskan saat source tree GLD/CH dibuat:

1. Lokasi file test vector, misalnya JSON terpisah atau embedded fixture di unit test.
2. Penyesuaian nama konstanta dengan style firmware setelah module/shared protocol dibuat.

Tidak ada open item pada byte layout uplink phase 1.
