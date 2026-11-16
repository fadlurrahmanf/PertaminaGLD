# Pertamina GLD Node-RED Flow

## Mode lama: broker lokal terpisah

Untuk bench lokal yang tidak bergantung pada IP broker lama, jalankan:

```text
tools\start-local-nodered-mqtt.bat
```

Launcher ini membuat credential lokal pertama kali, menyalakan broker MQTT pada
`127.0.0.1:1884`, menyalakan Node-RED pada `127.0.0.1:1880`, menerapkan flow,
dan hanya selesai jika broker merekam CONNECT dari client
`node-red-pertamina-gld`.

Titik inisialisasi broker adalah `tools\local_mqtt_broker.py`. Broker dapat
dijalankan sendiri dengan `tools\run-local-mqtt-broker.bat`; launcher full-stack
memanggil runner yang sama secara otomatis. Node-RED hanya client MQTT, bukan
pemilik/penjalannya. Credential dan status lokal dibuat di
`apps\runtime\local-mqtt\` dan sengaja tidak masuk Git.

Saat deploy, launcher tidak menulis ulang file flow di repository; hanya flow
Node-RED pada profil pengguna aktif yang diperbarui.

Broker ini hanya untuk bench lokal loopback dan MQTT 3.1.1 QoS 0, bukan TLS atau
deployment produksi.

Flow ini adalah server-side bridge untuk tahap bench GLD -> CH -> Gateway -> Node-RED.
Jalur utama kasus sebenarnya adalah MQTT/LAN dari Gateway ke server, bukan AP.

## Import untuk Gateway fisik

Import `pertamina-gld-server.flow.json` dan deploy di Node-RED. File ini
disinkronkan dengan generator; `handover/state/nodered/flows.json` adalah
snapshot runtime yang terpisah, bukan file import server yang dipelihara.
Flow berisi node broker Aedes dan client MQTT Node-RED. Install
`node-red-contrib-aedes` 1.2.0 melalui Manage Palette terlebih dahulu; import
tidak memasang modul dan tidak menyalin kredensial/secret.

1. Import flow, lalu buka node **Aedes MQTT broker**. Atur username dan
   password broker sebelum Deploy; field yang kosong membuat Aedes menerima
   koneksi anonim. Port default adalah 1883 dan harus bebas dari broker lain.
   Aedes 1.2.0 mendengarkan semua interface; batasi firewall dan gunakan
   jaringan bench yang sesuai. Flow bawaan non-TLS, bukan konfigurasi produksi.
2. Di Expert Gateway, pilih bentuk board dan transport MQTT yang sesuai saat
   upload. Setelahnya gunakan Gateway Setup untuk menyimpan dan memverifikasi
   Wi-Fi serta host/IP PC Node-RED, port 1883, username dan password Aedes.
   **Use This PC IP** hanya benar jika Expert dan Node-RED ada di PC yang sama;
   tombol ini tidak mengisi kredensial. Untuk paket TLS,
   konfigurasi CA dan NTP yang sesuai dengan sertifikat broker juga diperlukan.
3. Di node konfigurasi `Pertamina GLD MQTT`, gunakan `127.0.0.1:1883` dan
   username/password yang sama dengan Aedes, lalu Deploy. Pastikan firewall
   mengizinkan koneksi Gateway ke alamat LAN PC pada port tersebut. Operator
   Hub dapat menjalankan broker terpisah pada 1884 untuk workflow lamanya;
   broker itu bukan Aedes dan tidak dipakai flow ini.
4. Pastikan `settings.js` mengizinkan `functionExternalModules` dan Function
   nodes dapat memakai modul Node.js `crypto`, `fs`, dan `path`. Contoh
   tersedia di `handover/state/nodered/settings.js`. Siapkan environment
   Node-RED untuk `GLD_AES128_KEY_HEX`, `GLD_KEY_ID` dan
   `PGL_COMMAND_AUTH_TOKEN`; key dan ID harus sesuai dengan GLD. Restart proses
   setelah mengubah environment. Jangan memasukkan secret ke flow JSON.
   Untuk menyimpan rute CH setelah Node-RED restart, aktifkan juga named context
   store `pglTopologyFile` dengan `module: "localfilesystem"` di `settings.js`;
   contoh lengkap ada di `handover/state/nodered/settings.js`. Setelah mengubah
   settings, restart Node-RED dan tunggu rute tersimpan. Tanpa store tersebut,
   rute bisa sementara hilang hingga CH mengirim HELLO kembali.
   Jika Node-RED dimulai tanpa environment GLD, siapkan file lokal yang diabaikan
   Git `server/nodered/.env` dengan `GLD_KEY_ID` dan `GLD_AES128_KEY_HEX` yang
   sesuai dengan GLD, lalu jalankan dari root repository:

   ```powershell
   node server/nodered/configure-local-gld-env.js
   ```

   Skrip mencadangkan `settings.js` dan menambahkan pembaca untuk dua nilai itu;
   nilai kunci tidak disalin ke flow atau repository. Restart Node-RED setelah
   pengaturan. Jalankan sekali pada setiap PC yang memakai user Node-RED yang
   berbeda. Untuk lokasi khusus, gunakan `--user-dir` dan `--env-file`.
5. Tab flow memiliki path relatif `.node-red/...` untuk replay state, log dan
   bootstrap topology. Path ini relatif terhadap working directory proses
   Node-RED; pada server, ubah flow environment tersebut ke lokasi privat yang
   tetap dan dapat ditulis. Replay state harus bertahan saat restart.
6. Pastikan kedua client MQTT connected, lalu periksa `gld/gateway/status`.
   Dengan CH dan GLD aktif, periksa `gld/gateway/uplink`,
   `gld/server/decoded`, dan `gld/server/integrity`; uji command serta ACK
   terpisah jika fungsi downlink diperlukan.

Topik flow menggunakan root tetap `gld/gateway`. Penggantian root pada build
Gateway memerlukan penyesuaian topik node MQTT di flow.

## Isi

- `functions/pertamina-gld-decode.js`
  - Function Node decoder.
  - Bisa membaca output Gateway `/api/status`.
  - Bisa decode `GLDRecord` kontrak baru.
  - Bisa decrypt AES-128-GCM payload 29 byte.
- `apply-pertamina-gld-flow.js`
  - Membuat tab `Pertamina GLD Server` di Node-RED lokal.
  - Backup flow existing sebelum deploy.
  - Apply lewat Node-RED Admin API.
- `apply-pertamina-gld-flow.ps1`
  - Wrapper PowerShell ke generator JS utama supaya hanya ada satu definisi flow.
- `.env.example`
  - Contoh variabel lokal. Jangan commit `.env` berisi secret produksi.

## Secret AES dan status deployment

`GLD_AES128_KEY_HEX`, `GLD_KEY_ID`, dan `PGL_COMMAND_AUTH_TOKEN` adalah
secret runtime. Generator tidak pernah menyalin nilainya ke
`pertamina-gld-server.flow.json`; Node-RED yang berjalan harus menerima ketiga
variabel tersebut dari service environment atau secret store-nya sendiri.

Operator Hub hanya membaca `server/nodered/.env` sebagai sumber provisioning
untuk GLD. Status **source siap** berarti bridge dapat mengirim key ke GLD,
bukan bukti flow Node-RED yang sedang berjalan sudah di-deploy atau direstart
dengan key tersebut. Setelah mengubah secret, update environment proses
Node-RED lalu deploy/restart Node-RED melalui prosedur server yang berwenang.

## Jalur Input

Flow menyediakan:

- MQTT uplink dari Gateway:
  - `gld/gateway/uplink`
  - `gld/gateway/raw`
  - `pertamina/gld/uplink`
- HTTP polling Gateway:
  - opsional/debug saja jika firmware Gateway nanti memang expose endpoint status.
  - default flow generator tidak mengaktifkan polling HTTP.
- MQTT command bridge:
  - inject/publish `gld/gateway/cmd/pull`
  - high-level GLD command input `gld/server/cmd/node`
  - signed Gateway command output `gld/gateway/cmd/node`
- Test vectors run through the checked-in automated harness, not a production
  flow inject node.

## Jalur Output MQTT

- `gld/gateway/status`
- `gld/gateway/events`
- `gld/server/decoded`
- `gld/server/alarm`
- `gld/server/integrity` untuk record yang gagal autentikasi/validasi
- `gld/server/replay` hanya untuk encrypted record yang benar-benar identik
  atau pemakaian ulang nonce AES-GCM; sequence GLD yang turun, sama, wrap, atau
  reset setelah reboot tetap diterima bila nonce dan ciphertext-nya baru
- `gld/server/test` untuk input HTTP manual/test yang terautentikasi tetapi
  tidak boleh masuk alarm produksi
- `gld/gateway/error`
- command inject:
  - `gld/gateway/cmd/pull`
  - `gld/server/cmd/node`
  - `gld/gateway/cmd/node`

Pull command mengikuti kontrak CH `SERVER_PULL_REQUEST`: payload berisi
`hopList[]`, bukan GLD `nodeId`. Contoh direct CH bench:

```json
{"requestId":1,"hopList":["0x0064"]}
```

Command GLD/downlink high-level masuk ke `gld/server/cmd/node` dengan `mode`,
`cluster`, `node`, `id`, dan `authorization`. Nilai authorization harus sama
dengan secret `PGL_COMMAND_AUTH_TOKEN` (minimal 32 karakter). Flow menolak ID
hilang/tidak valid, menghapus token sebelum output, menandatangani payload
memakai `GLD_AES128_KEY_HEX`, lalu publish hasil authenticated ke
`gld/gateway/cmd/node`.

## Dataset Flow Controls

`apply-pertamina-gld-dataset-flow.ps1` membuat tab `GLD Dataset Server` untuk recorder dan kontrol operator. Flow dataset memiliki inject:

- `START_DATASET clear_air_test` publish ke `gas-leak-detector/F001/dataset`.
- `STOP_DATASET` publish ke `gas-leak-detector/F001/dataset`.

Flow dataset juga listen ke `gas-leak-detector/+/cmd/ack`, `gas-leak-detector/+/dataset/status`, `gas-leak-detector/+/dataset/summary`, `gas-leak-detector/+/dataset/data`, dan `gas-leak-detector/+/nulling/result`.

Record disimpan hanya bila topic/device cocok, mode `DATASET`, delapan voltage
finite, gain valid, seluruh `sensor_status` bernilai `0`, dan `feature_order`
sama dengan urutan model canonical. MySQL menjadi gate idempotensi sebelum CSV,
sehingga duplicate tidak dihitung atau ditulis dua kali. Saat deploy, script
membuat header CSV hanya untuk file baru dan menolak schema file lama.

## Apply Lokal

Contoh dari repo root:

```powershell
node .\server\nodered\apply-pertamina-gld-flow.js `
  --external-mqtt --node-red-url "http://127.0.0.1:1880" `
  --gateway-status-url "http://0.0.0.0/disabled-until-gateway-ip-known" `
  --gateway-base-url "http://0.0.0.0" `
  --mqtt-host "127.0.0.1" `
  --mqtt-port 1884 `
  --replay-state-path "C:\ProgramData\PertaminaGLD\replay-state.json"
```

Wrapper PowerShell lama tetap bisa dipakai dan meneruskan argumen ke generator JS:

```powershell
.\server\nodered\apply-pertamina-gld-flow.ps1 `
  -NodeRedUrl "http://127.0.0.1:1880" `
  -GatewayStatusUrl "http://0.0.0.0/disabled-until-gateway-ip-known" `
  -GatewayBaseUrl "http://0.0.0.0" `
  -MqttHost "127.0.0.1" `
  -MqttPort 1884
```

Jika broker MQTT butuh auth, pass username/password saat apply lokal. Untuk host
non-loopback generator mewajibkan credentials dan TLS (`--mqtt-tls`), kecuali
operator secara eksplisit memilih `--allow-insecure-mqtt` untuk jaringan bench
yang benar-benar terisolasi. `--external-mqtt` menggunakan broker eksternal;
tanpa opsi itu generator membuat node Aedes dan deployment via script
mensyaratkan `MQTT_USER` dan `MQTT_PASS`.

## Catatan Keamanan

Flow wajib menerima `GLD_AES128_KEY_HEX`, `PGL_COMMAND_AUTH_TOKEN`, dan token
Admin API Node-RED dari environment/secret store. Jika key kosong, decrypt GLD
dan builder downlink authenticated ditolak eksplisit. Replay state disimpan
atomik ke `PGL_REPLAY_STATE_PATH` agar restart Node-RED tetap mengingat encrypted
record yang sudah pernah diterima. Sequence 8-bit hanya dipakai sebagai status
observasi karena restart/wrap tidak boleh membuat data autentik ditolak. Deploy
memakai API v2/revision checking dan tidak menimpa
credential node lain; credential baru hanya dikirim inline ke node miliknya.

Gunakan `node server/nodered/apply-pertamina-gld-flow.js --check` dan
`powershell -ExecutionPolicy Bypass -File server/nodered/apply-pertamina-gld-dataset-flow.ps1 -Check`
untuk mendeteksi drift antara generator dan flow JSON yang disimpan.

## Compatibility Notes

Sebagian reference Gateway lama tidak sama dengan kontrak final. Jalur final yang dipakai sistem sebenarnya adalah Gateway publish MQTT/LAN ke server, bukan CH/Gateway sebagai AP. Flow ini tetap punya parser untuk bentuk `gateway-event`, tetapi decrypt hanya berjalan bila `payload_hex` berisi:

- encrypted payload 29 byte dengan metadata `node_id`, `seq`, `flags`, atau
- `GLDRecord` lengkap 34 byte, atau
- `AppFrame` lengkap dari kontrak baru.
