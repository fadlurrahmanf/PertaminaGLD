# Handoff Perbaikan RSSI Parent CH pada Dashboard GLD

Dokumen ini merangkum investigasi dan perbaikan yang dimulai pada Rabu, 9 September 2026 pukul 11:35 WIB. Dokumen dibuat agar pekerjaan dapat dilanjutkan dari komputer atau sesi AI lain tanpa membutuhkan riwayat percakapan sebelumnya.

## 1. Tujuan

Dashboard harus membedakan dua pengukuran radio yang berbeda:

1. **RSSI Parent → CH**, yaitu sinyal parent yang diterima dan diukur oleh child CH.
2. **Gateway RX dari hop**, yaitu sinyal paket hop terakhir yang diterima dan diukur oleh Gateway.

Contoh topology yang dibahas:

```text
GW 0x0001 → CH10 0x0010 → CH11 0x0011 → CH12 0x0012
```

Metrik parent yang benar untuk topology tersebut adalah:

```text
CH10: GW    → CH10, diukur oleh CH10
CH11: CH10  → CH11, diukur oleh CH11
CH12: CH11  → CH12, diukur oleh CH12
```

RSSI bersifat directional. Metrik `CH10 → CH11` tidak otomatis sama dengan `CH11 → CH10`. Implementasi ini melaporkan arah parent ke child. Pengukuran dua arah memerlukan field reverse-link tersendiri.

## 2. Akar Masalah

Firmware CH sebenarnya sudah melakukan langkah berikut saat discovery parent:

1. Mengirim `CH_CONFIG_REQUEST`.
2. Menerima `CH_CONFIG_RESPONSE` dari kandidat parent.
3. Membaca RSSI dan SNR paket kandidat pada radio CH.
4. Menyimpan metrik kandidat dalam `ParentCandidate.rssiDbm` dan `ParentCandidate.snrDb`.
5. Memilih kandidat terbaik menggunakan skor RSSI, SNR, dan depth.
6. Menyalin metrik parent terpilih ke `lastParentRssiDbm` dan `lastParentSnrDb`.

Nilai tersebut sebelumnya hanya tersedia pada serial `CH_STATUS_JSON`. Payload `CH_HELLO` lama tidak mengirim metrik parent ke Gateway.

Akibatnya, dashboard memakai `rssi` dan `snr` milik Gateway. Nilai ini adalah pengukuran paket terakhir yang masuk ke Gateway, bukan pengukuran parent oleh CH. Pada jaringan multi-hop, paket origin yang sama dapat diterima langsung atau melalui relay sehingga nilainya dapat berubah dari sekitar `-80 dBm` menjadi `-110 dBm` atau lebih kecil.

Angka tersebut bukan data palsu; konteks dan labelnya yang salah.

## 3. Kontrak Metrik

### 3.1 Parent-link

```text
parentRxRssiDbm = RSSI parent → child, diukur radio child CH
parentRxSnrDb   = SNR parent → child, diukur radio child CH
```

Metrik terikat pada `parentId` yang terdapat dalam payload `CH_HELLO`. Sampel dapat berasal dari:

- `CH_CONFIG_RESPONSE`, ketika CH melakukan discovery/route verification; atau
- `CH_HELLO_ACK`, ketika child menerima ACK dari parent aktif.

### 3.2 Gateway ingress

```text
gatewayIngressRssiDbm = RSSI hop terakhir → Gateway, diukur Gateway
gatewayIngressSnrDb   = SNR hop terakhir → Gateway, diukur Gateway
ingressHopId          = ID hop yang frame-nya benar-benar diterima Gateway
originChId            = CH asal yang terdapat di payload CH_HELLO
```

Pada frame relay, `originChId` dan `ingressHopId` dapat berbeda.

## 4. Ekstensi Protokol CH_HELLO

Prefix payload lama dipertahankan agar kompatibel dengan firmware lama. Payload baru berukuran 18 byte.

| Byte | Field | Format | Keterangan |
|---:|---|---|---|
| 0–1 | `originChId` | uint16 BE | ID CH asal |
| 2–3 | `parentId` | uint16 BE | Parent aktif |
| 4–5 | `batteryMv` | uint16 BE | Tegangan baterai |
| 6–7 | `uptimeSec16` | uint16 BE | Uptime 16-bit |
| 8 | `meshDepth` | uint8 | Depth topology |
| 9–10 | `parentAltId` | uint16 BE | Alternate parent |
| 11 | `helloFlags` | bit field | Bit 0 ACK request; bit 1 parent-link extension tersedia |
| 12 | `parentLinkFlags` | bit field | Validitas dan sumber sampel |
| 13–14 | `parentRxRssiDbm` | int16 BE | Parent → CH RSSI |
| 15 | `parentRxSnrDb` | int8 | Parent → CH SNR |
| 16–17 | `parentLinkAgeSec` | uint16 BE | Umur sampel dalam detik |

Flag yang digunakan:

```text
CH_HELLO_FLAG_ACK_REQUEST_V1                 = 0x01
CH_HELLO_FLAG_PARENT_LINK_V1                 = 0x02
CH_PARENT_LINK_FLAG_VALID                    = 0x01
CH_PARENT_LINK_FLAG_SOURCE_CONFIG_RESPONSE   = 0x02
CH_PARENT_LINK_FLAG_SOURCE_HELLO_ACK         = 0x04
```

Sentinel metrik tidak valid:

```text
RSSI = -32768
SNR  = -128
age  = 0xFFFF
```

Umur sampel valid disaturasi maksimum ke `0xFFFE` agar tidak bertabrakan dengan sentinel.

## 5. Perubahan Implementasi

### Firmware bersama

File: `firmware/shared/include/ProtocolConstants.h`

- Menambahkan flag ekstensi parent-link.
- Menetapkan payload CH_HELLO baru 18 byte.
- Menetapkan flag validitas dan sumber sampel.
- Memastikan ukuran payload masih di bawah `MESH_MAX_PAYLOAD`.

### Firmware CH

File: `firmware/ch/src/ChStarMeshRuntimeMain.cpp`

- Menyimpan sumber sampel parent terakhir.
- Menginvalidasi sampel ketika parent berubah.
- Menandai sampel dari `CH_CONFIG_RESPONSE` atau `CH_HELLO_ACK`.
- Mengirim RSSI, SNR, umur, validitas, dan sumber melalui CH_HELLO.
- Tetap mempertahankan semantik ACK lama pada bit 0.

### Firmware Gateway

File: `firmware/gateway/src/GatewayMqttMeshMain.cpp`

- Membaca ekstensi hanya jika flag tersedia dan panjang payload minimal 18 byte.
- Payload lama 8/11/12 byte tetap diproses sebagai topology dasar.
- Menerbitkan parent-link dan Gateway-ingress sebagai field terpisah.
- Menerbitkan `originChId` dan `ingressHopId` secara eksplisit.
- Metrik malformed tidak menggugurkan topology dasar.

### Decoder dan state Node-RED

File: `server/nodered/functions/pertamina-gld-decode.js`

- Mendekode signed RSSI 16-bit dan signed SNR 8-bit.
- Mendukung frameHex maupun object topology dari Gateway.
- Menggunakan `srcId` sebagai fallback `ingressHopId`.
- Menyimpan waktu pengukuran berdasarkan `receivedAt - parentLinkAgeSec`.
- Firmware lama menghasilkan status unsupported/unavailable, bukan `0 dBm`.

### Dashboard Node-RED

File: `server/nodered/apply-pertamina-gld-flow.js`

- Edge parent hanya menggunakan `parentRxRssiDbm` dan `parentRxSnrDb`.
- RSSI Gateway tidak lagi diberi label “RSSI to Parent”.
- Kartu CH menampilkan dua baris yang terpisah:

```text
RSSI Parent → CH (0x0010 → 0x0011): -81 dBm, SNR 9 dB, umur 3 dtk
Gateway RX dari 0x0010: -88 dBm, SNR 7 dB
```

- Firmware lama ditampilkan sebagai:

```text
RSSI Parent → CH: firmware CH belum mengirim metrik
```

Flow hasil generator berada di `server/nodered/pertamina-gld-server.flow.json`.

## 6. Status Implementasi per 9 September 2026

Selesai:

- Source firmware CH dan Gateway diperbarui.
- Decoder, state, API topology, dan dashboard diperbarui.
- Flow Node-RED digenerasi ulang dan dideploy pada server `192.168.8.19`.
- Broker tetap menggunakan `192.168.8.19:1884`.
- Topology live tetap menampilkan GW `0x0001`, CH10 `0x0010`, CH11 `0x0011`, dan CH12 `0x0012`.
- Route dan fungsi Request GLD tetap berjalan.
- Tiga pengujian Node-RED lulus.
- Build `chRealTest`, `gwRealTest`, `chRealField`, dan `gwRealField` berhasil.
- Paket firmware Operator Hub telah diperbarui.

Belum selesai:

- Firmware baru belum di-flash ke perangkat fisik.
- Nilai aktual CH10→CH11 dan CH11→CH12 belum dapat muncul sampai firmware CH dan Gateway di-rollout.
- Suite Python `pytest` belum dijalankan pada komputer tersebut karena modul `pytest` dan `cryptography` tidak terpasang. Build firmware dan pengujian Node.js berhasil.

## 7. Lokasi Paket Firmware

Paket yang sudah dibangun:

```text
apps/operator-hub/firmware-packages/chRealTest/latest/
apps/operator-hub/firmware-packages/gwRealTest/latest/
apps/operator-hub/firmware-packages/chRealField/latest/
apps/operator-hub/firmware-packages/gwRealField/latest/
```

Gunakan varian yang sama dengan konfigurasi perangkat aktif. Jangan mengganti varian RealTest/RealField tanpa memeriksa interval HELLO, threshold, dan konfigurasi jaringan yang sedang digunakan.

## 8. Langkah Melanjutkan di Perangkat Lain

### 8.1 Persiapan repository

```powershell
$PglRepoRoot = 'C:\path\to\PertaminaGLD_Github' # sesuaikan pada komputer tujuan
Set-Location $PglRepoRoot
git status --short
```

Repository dapat berisi perubahan lain yang belum di-commit. Jangan melakukan `git reset --hard` atau menimpa file yang tidak terkait.

Baca aturan repository:

```powershell
Get-Content -Raw AGENTS.md
Get-Content -Raw ActivityAI\rules\AGENTS.md
Get-Content -Raw ActivityAI\rules\AI_WORKFLOW_RULES.md
Get-Content ActivityAI\codexactivity.md -Tail 20
```

### 8.2 Build firmware

Jika PlatformIO tersedia di PATH:

```powershell
Set-Location (Join-Path $PglRepoRoot 'firmware')
platformio run -e chRealTest -e gwRealTest
platformio run -e chRealField -e gwRealField
```

Jika `platformio` tidak ada di PATH, temukan executable instalasi lokal terlebih dahulu. Pada komputer sumber, lokasinya adalah:

```powershell
& 'C:\Users\Win11\.platformio\penv\Scripts\platformio.exe' run -e chRealTest -e gwRealTest
& 'C:\Users\Win11\.platformio\penv\Scripts\platformio.exe' run -e chRealField -e gwRealField
```

### 8.3 Pengujian server

```powershell
Set-Location $PglRepoRoot
node --check server\nodered\functions\pertamina-gld-decode.js
node --check server\nodered\apply-pertamina-gld-flow.js
node server\nodered\apply-pertamina-gld-flow.js --generate-only

Get-ChildItem server\nodered\tests -Filter '*.test.js' | ForEach-Object {
    node $_.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Hasil yang diharapkan mencakup:

```text
PASS routed GLD response request correlation
PASS multi-Gateway topology roots and role boundaries
PASS Node-RED authenticated replay policy
```

Jika dependency Python tersedia:

```powershell
python -m pytest firmware\tests\test_shared_protocol.py -q
```

### 8.4 Deploy dashboard server

Launcher mengambil kredensial MQTT runtime lokal tanpa menuliskannya ke dokumen atau command history:

```powershell
Set-Location $PglRepoRoot
& .\tools\start-pertamina-gld-system.ps1 -ForceDeployFlow -NoBrowser
```

Verifikasi endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:1880/pertamina-gld/topology
Start-Process http://127.0.0.1:1880/pertamina-gld/topology/view
```

### 8.5 Rollout perangkat

Urutan aman yang disarankan:

1. Backup konfigurasi perangkat dan catat pemetaan port COM.
2. Pastikan server/decoder baru sudah aktif.
3. Flash Gateway baru agar ekstensi CH_HELLO diteruskan ke MQTT.
4. Flash satu CH sebagai canary.
5. Verifikasi topology, parent, Request GLD, RSSI, SNR, dan umur sampel.
6. Jika canary berhasil, rollout CH lainnya satu per satu.
7. Jangan melakukan upload pada beberapa board secara paralel.

Port COM harus dideteksi ulang pada komputer tujuan. Jangan berasumsi port lama masih benar.

## 9. Checklist Verifikasi Lapangan

Untuk topology `GW → CH10 → CH11 → CH12`, pastikan:

- [ ] CH10, CH11, dan CH12 berstatus installed.
- [ ] Request GLD untuk setiap CH masih mendapatkan respons, bukan timeout.
- [ ] CH11 menampilkan parent `0x0010`.
- [ ] CH11 menampilkan `RSSI Parent → CH (0x0010 → 0x0011)`.
- [ ] CH12 menampilkan parent `0x0011`.
- [ ] CH12 menampilkan `RSSI Parent → CH (0x0011 → 0x0012)`.
- [ ] `Gateway RX dari ...` muncul pada baris terpisah.
- [ ] Nilai pada edge parent sama dengan `parentRxRssiDbm`, bukan `gatewayIngressRssiDbm`.
- [ ] `parentLinkAgeSec` bertambah wajar dan kembali kecil setelah sampel parent baru.
- [ ] Pergantian parent menginvalidasi metrik lama sampai sampel parent baru diterima.
- [ ] Firmware lama tetap muncul sebagai unavailable tanpa merusak route.

Contoh pemeriksaan API:

```powershell
$topology = Invoke-RestMethod http://127.0.0.1:1880/pertamina-gld/topology
$topology.nodes |
    Where-Object type -eq 'ch' |
    Select-Object id,parent,parentRssi,parentSnr,parentLinkAgeSec,gatewayRssi,gatewaySnr,gatewayIngressHopIdHex,linkQualityLabel,gatewayQualityLabel |
    Format-List
```

## 10. Kriteria Penerimaan

Perbaikan dianggap selesai di perangkat fisik jika:

1. CH11 melaporkan RSSI CH10→CH11 dari radio CH11.
2. CH12 melaporkan RSSI CH11→CH12 dari radio CH12.
3. Gateway RX tetap tersedia sebagai metrik terpisah dengan ingress hop yang benar.
4. Nilai direct-overhear tidak pernah lagi menggantikan nilai edge parent.
5. Request GLD, routing, discovery, dan kompatibilitas firmware lama tidak mengalami regresi.
6. Sistem tetap pulih setelah restart server, Gateway, dan CH sesuai launcher serta konfigurasi jaringan yang berlaku.

## 11. Batasan dan Catatan Keamanan

- Dokumen ini tidak menyimpan username, password, token, AES key, maupun kredensial broker.
- Jangan membuka broker MQTT atau editor Node-RED langsung ke internet.
- Quick Tunnel Cloudflare bersifat sementara dan hostname `trycloudflare.com` diberikan secara acak.
- Untuk alamat publik tetap, gunakan domain sendiri dan Cloudflare Named Tunnel dengan autentikasi yang sesuai.
- Flash perangkat adalah perubahan hardware; pastikan board, environment, dan port COM telah diverifikasi sebelum upload.

## 12. File Referensi Utama

```text
firmware/shared/include/ProtocolConstants.h
firmware/ch/src/ChStarMeshRuntimeMain.cpp
firmware/gateway/src/GatewayMqttMeshMain.cpp
firmware/tests/test_shared_protocol.py
server/nodered/functions/pertamina-gld-decode.js
server/nodered/apply-pertamina-gld-flow.js
server/nodered/pertamina-gld-server.flow.json
server/nodered/tests/multi-gateway-topology.test.js
tools/start-pertamina-gld-system.ps1
ActivityAI/codexactivity.md
```

---

Status dokumen: handoff implementasi; server sudah diperbarui, rollout firmware perangkat masih diperlukan.
