# Gateway Design

**Status:** draft + bench implementation reference  
**Tanggal:** 2026-06-18  
**Scope:** firmware Gateway sebagai root identity/direct MESH bridge dan WiFi MQTT bridge ke server  
**Sumber utama:** `firmware/gateway/src/GatewayMqttMeshMain.cpp`, `server/nodered/README.md`, `docs/design/gld-ch/payload-contract.draft.md`  

---

## 1. Ringkasan

Gateway adalah root identity/direct MESH bridge dan bridge ke server. Gateway menerima frame dari CH melalui LoRa MESH, lalu mem-publish ke server melalui MQTT. Gateway juga menerima command dari server melalui MQTT dan meneruskannya ke CH target melalui MESH.

Gateway tidak melakukan decrypt payload GLD. Decrypt dilakukan di server/Node-RED.

Status saat ini:

- Gateway firmware `v0.1.2` sudah di-upload dan live-tested pada COM38.
- Gateway berhasil connect WiFi dan MQTT.
- Gateway berhasil meneruskan server pull ke CH.
- Gateway berhasil publish `gld/gateway/uplink`.

---

## 2. Tanggung Jawab

Gateway bertanggung jawab untuk:

- init Radio B / MESH,
- connect WiFi bench,
- connect MQTT broker,
- subscribe topic command server,
- build MESH frame untuk CH target,
- receive MESH frame dari CH,
- publish MESH frame ke MQTT dalam format JSON,
- publish gateway status periodik,
- memberi compact ACK untuk alarm MESH jika dibutuhkan.

Gateway tidak bertanggung jawab untuk:

- decrypt AES-GCM payload GLD,
- parse plaintext gas,
- menentukan alarm dari `gasClass/confidence`,
- menyimpan database,
- menjalankan dashboard,
- melakukan training/model build.

---

## 3. Runtime Architecture

```text
MQTT command in
  -> command parser
  -> AppFrame builder
  -> MESH TX

MESH RX
  -> AppFrame parse best-effort
  -> JSON publish to MQTT
  -> optional compact ACK

Status timer
  -> MQTT status publish
```

Loop utama:

1. Pastikan WiFi connected.
2. Pastikan MQTT connected.
3. Jalankan `mqtt.loop()`.
4. Publish status periodik.
5. Receive MESH frame.

---

## 4. Hardware / Link

Gateway memakai Radio B / MESH.

Parameter bench:

| Parameter | Nilai |
|---|---:|
| Frequency | `921.0 MHz` |
| Bandwidth | `125 kHz` |
| Spreading Factor | `SF9` |
| Coding Rate | `4/5` |
| Sync Word | `0x34` |
| TX Power | `17 dBm` |
| Preamble | `8` |
| SPI | `2 MHz`, mode 0 |

Catatan:

- Firmware saat ini mencoba TCXO `1.6V`, lalu fallback XTAL/TCXO `0V` jika init gagal.
- Final production pin/config harus masuk provisioning/config, bukan hardcoded.
- LAN/Ethernet adalah opsi phase lanjut; bench saat ini memakai WiFi.

Pin map firmware bench:

| Sinyal | Pin |
|---|---:|
| SPI SCK | `12` |
| SPI MOSI | `11` |
| SPI MISO | `13` |
| Radio B CS | `14` |
| Radio B BUSY | `38` |
| Radio B RXEN | `39` |
| Radio B TXEN | `40` |
| Radio B RST | `41` |
| Radio B DIO1 | `42` |
| LED | `19` |

Build/upload bench:

```powershell
pio run -d firmware -e gateway_mqtt_mesh_esp32s3 -t upload --upload-port COM38
```

Board target:

```text
4d_systems_esp32s3_gen4_r8n16
```

---

## 5. IDs

Bench IDs:

| Entity | ID |
|---|---:|
| Gateway | `0x006F` |
| Default CH | `0x0064` |

Aturan:

- Gateway ID adalah root identity untuk MESH.
- CH target dapat dipilih lewat payload command MQTT.
- ID production harus dikelola sebagai config/provisioning.

---

## 6. MQTT Topics

Gateway subscribe:

| Topic | Fungsi |
|---|---|
| `gld/gateway/cmd/#` | command namespace umum |
| `gld/gateway/cmd/pull` | request data CH |
| `gld/gateway/cmd/node` | command server ke GLD via CH |

Gateway publish:

| Topic | Fungsi |
|---|---|
| `gld/gateway/uplink` | frame MESH dari CH ke server |
| `gld/gateway/status` | status Gateway periodik |

Server/Node-RED publish turunan:

| Topic | Fungsi |
|---|---|
| `gld/gateway/events` | envelope hasil parse |
| `gld/server/decoded` | event normal hasil decrypt |
| `gld/server/alarm` | event alarm |
| `gld/gateway/error` | error decode/parse |

---

## 7. MQTT Command: Pull

Input topic:

```text
gld/gateway/cmd/pull
```

JSON payload:

```json
{
  "requestId": 1,
  "hopList": ["0x0064"]
}
```

Catatan:

- Firmware Gateway memakai `hopList[]` untuk menentukan jalur CH target.
- `requestId` boleh dikirim server untuk korelasi; jika tidak dikirim, Gateway membuat request ID lokal.
- Field `cluster` masih diterima sebagai fallback kompatibilitas lama dan diterjemahkan menjadi `hopList[0]`.
- Field `node` tidak dipakai untuk pull karena pull phase saat ini adalah CH-level pull dari cache, bukan request langsung ke GLD.
- Callback bench subscribe wildcard `gld/gateway/cmd/#` dan menerima topic yang mengandung `/pull` atau `/node`; production sebaiknya exact-match topic supaya command salah topic tidak dieksekusi.

Gateway membangun:

```text
msgType = SERVER_PULL_REQUEST (0x30)
srcId = Gateway ID
dstId = hopList[0]
payload = requestId:uint16BE + hopList:uint16BE[]
```

Catatan:

- Payload 4 byte adalah bentuk single-hop bench: `requestId + hopList[0]`.
- Multi-hop memakai `requestId + hopList[]` dengan lebih dari satu CH ID.

---

## 8. MQTT Command: Node Command

Input topic:

```text
gld/gateway/cmd/node
```

JSON payload rencana/bench:

```json
{
  "cluster": "0x0064",
  "node": "0xF001",
  "id": 1,
  "ttl": 600,
  "hex": "..."
}
```

Gateway membangun:

```text
msgType = SERVER_NODE_COMMAND (0x32)
payload = nodeId:uint16BE + commandId:uint16BE + ttlSec:uint16BE + commandLen:uint8 + commandBytes
```

Status:

- Command builder sudah ada di Gateway firmware.
- Execution penuh sampai GLD adalah phase downlink berikutnya.
- Validasi command production harus fail-closed: reject JSON invalid, `cluster` hilang/invalid, `id` invalid, `ttl` invalid, hex ganjil/invalid/overflow, dan publish NACK/error.

---

## 9. MQTT Uplink JSON

Gateway publish ke:

```text
gld/gateway/uplink
```

JSON:

```json
{
  "source": "gateway",
  "gatewayId": 111,
  "frameHex": "AA31...",
  "frameLen": 50,
  "rssi": -66,
  "snr": 9.25,
  "parseStatus": 0,
  "typeFlags": 49,
  "msgType": 49,
  "srcId": 100,
  "dstId": 111,
  "seq": 1,
  "payloadLen": 40
}
```

Aturan:

- `frameHex` adalah source of truth untuk server decode.
- Field parse metadata membantu monitor/debug.
- Jika `parseStatus != 0`, server tetap bisa log error dengan `frameHex`.

---

## 10. Status Publish

Gateway publish periodik:

```text
gld/gateway/status
```

JSON:

```json
{
  "kind": "gateway-status",
  "gatewayId": 111,
  "state": "alive",
  "wifi": true,
  "mqtt": true,
  "meshReady": true,
  "ip": "10.255.102.36"
}
```

Interval bench saat ini:

```text
10000 ms
```

---

## 11. Error Handling Dan Data Loss

Gateway:

- Jika MQTT down, Gateway mencoba reconnect.
- Jika MQTT disconnected saat uplink datang, firmware bench belum punya offline buffer/retry; frame uplink bisa hilang.
- Jika MESH TX gagal, Gateway log `GW_MESH_TX ... state != 0`.
- Jika frame MESH parse gagal, Gateway tetap dapat publish `frameHex` dengan `parseStatus` non-zero untuk debug.
- ACK alarm guard production harus memastikan `dstId == Gateway ID`, payload valid, dan source CH masuk allowlist sebelum ACK.

Server/Node-RED:

- Jika `frameHex` invalid, publish error/debug route.
- Jika decrypt gagal, event tidak boleh masuk alarm production tanpa gate decrypt dan key valid.

---

## 12. Security

Phase bench:

- WiFi/MQTT masih hardcoded di firmware untuk percepatan test.
- Node-RED Aedes broker berjalan di laptop bench port `1884`.

Production requirement:

- WiFi SSID/password tidak boleh hardcoded.
- MQTT host/port/user/password harus dari provisioning/config.
- Credential tidak boleh masuk git/log.
- Credential production harus dipindah ke NVS/provisioning/env sebelum field deployment.
- MQTT sebaiknya memakai TLS atau setidaknya network terisolasi.
- Gateway tidak menyimpan AES key GLD karena decrypt dilakukan di server.

---

## 13. Functional Monitor

Serial boot expected:

```text
GW_MESH_READY=1
GW_WIFI_CONNECT ssid=...
GW_MQTT_CONNECT host=... port=1884 ok=1
GW_MQTT_SUB topic=gld/gateway/cmd/# ok=1
```

Pull expected:

```text
GW_MQTT_CMD topic=gld/gateway/cmd/pull
GW_MESH_TX reason=server-pull state=0 len=14
GW_MESH_RX state=0 len=50
GW_MQTT_PUBLISH topic=gld/gateway/uplink ok=1 frameLen=50 parseStatus=0
```

---

## 14. Acceptance Criteria

Gateway dianggap ready phase bench jika:

- Radio MESH init sukses.
- WiFi connected.
- MQTT connected.
- Subscribe command topics sukses.
- Pull command dari MQTT menghasilkan MESH TX.
- MESH response dari CH dipublish ke `gld/gateway/uplink`.
- Status publish periodik muncul.
- Node-RED dapat decode frame yang dipublish.

Current bench sudah memenuhi normal pull acceptance.

---

## 15. Open Items

- Config/provisioning untuk WiFi/MQTT/IDs.
- Offline buffer jika MQTT/server down.
- Non-blocking MESH RX jika traffic naik.
- Gateway OTA/update strategy.
- Production logging level.
- TLS/MQTT security.
- Gateway watchdog dan reconnect hardening.
- ACK alarm guard dengan `dstId`, payload valid, dan source CH allowlist.
