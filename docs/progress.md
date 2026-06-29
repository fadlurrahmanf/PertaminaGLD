# Pertamina GLD Progress

Last updated: 2026-06-19 Asia/Jakarta

## Current Milestone

```text
100% 12/12 — placeholder model integrated, inference pipeline ready
```

## Status Ringkas

- GLD COM10: upload `gld_dataset_esp32s3` v0.6.4 sukses; dataset generation live verified with MQTT ack/data, CSV rows, and MySQL rows. Nulling profile NVS terakhir profileId=2.
- CH COM3: runtime aktif sekarang env pendek `ch1`.
- Gateway COM38: runtime aktif sekarang env pendek `gw`.
- Node-RED: flow Pertamina deployed, Aedes bench aktif di port `1884`.
- Full normal path: GLD -> CH -> Gateway -> Node-RED -> `gld/server/decoded` sukses.
- Alarm push live path: GLD alarm frame -> CH alarm push -> Gateway -> Node-RED -> `gld/server/alarm` sukses.
- Host protocol tests: `28/28 tests passed`.
- Functional monitor update uploaded:
  - GLD COM10 now sends every 10 seconds and prints header/status only.
  - CH COM3 now prints cache summary/entry without encrypted payload hex dump.
- Functional monitor verified:
  - GLD serial: `GLD_TX_HEADER ... frameSize=39 payloadLen=29`, `GLD_LORA_TX_RESULT=PASS`.
  - CH serial: `CH_STAR_RX state=0 len=39`, `CH_CACHE_SUMMARY reason=star-rx used=1`, `CH_CACHE_ENTRY node=0xF001`.
- CH runtime fixed to non-blocking STAR+MESH receive:
  - CH firmware is now `v0.5.2`.
  - Gateway server pull reached CH over MESH.
  - CH returned one cached GLD record.
  - Node-RED/MQTT produced `gld/server/decoded` with `decryptOk=true`.
- GLD alarm self-test target added:
  - GLD firmware is now `v0.5.9`.
  - `gld_lora_alarm_selftest_esp32s3` sends LPG confidence `30` with alarm flag.
  - GLD self-test destination CH ID corrected to `0x0064`.
  - After alarm proof, COM10 was returned to normal `gld_lora_tx_selftest_esp32s3`.
- SERVER_PULL_REQUEST contract alignment:
  - CH firmware is now `v0.5.3`.
  - Gateway firmware is now `v0.1.3`.
  - Node-RED pull inject now uses `{"requestId":1,"hopList":["0x0064"]}`.
  - Gateway builds the MESH pull payload as `requestId:uint16BE + hopList:uint16BE[]`.
  - Pull is CH-level latest-cache request; it no longer carries GLD `node`.
  - CH validates `dstId == localChId`, `hopList[0] == localChId`, and rejects multi-hop until relay logic is implemented.
- GLD dataset generation:
  - GLD firmware is now `v0.6.4`.
  - v0.6.2 booted but `START_DATASET` failed with `DATASET_CMD_PARSE_ERROR NoMemory`.
  - v0.6.3 increased JSON/MQTT buffers.
  - v0.6.4 added MQTT diagnostics/stale-session mitigation and was uploaded to COM10.
  - Live MQTT `START_DATASET` produced `cmd/ack result=ok`, `dataset/status state=running`, and `dataset/data` records.
  - Dataset record schema matches design: `device_id`, `node_id`, `mode`, `seq`, `timestamp_ms`, `label`, `nulling_profile_id`, `sensor_voltage[8]`, `sensor_gain[8]`, and `feature_order`.
  - `feature_order=["MQ8","MQ135","MQ3","MQ5","MQ4","MQ7","MQ6","MQ2"]`.
  - Recorder wrote 69 rows to MySQL and 69 rows to `C:\Users\asus\gld-dataset.csv`.
- Step 11c Node-RED dataset tab:
  - `server/nodered/deploy-dataset-flow.py` now replaces existing `GLD Dataset Server` tab by label, not only by fixed id.
  - Node-RED dataset tab was redeployed with design-compliant schema.
  - Old schema `ch0..ch7`, `ts_ms`, `profile_id`, and `ok0..ok7` was removed from active dataset tab functions.
  - MySQL config now uses Node-RED `credentials` so `node-red-node-mysql` can connect.
  - CSV formatter receives raw MQTT dataset record in parallel, before MySQL parser converts payload to SQL bind array.
  - Bounded capture verified:
    - `target_samples=2` produced serial `DATASET_AUTOSTOP target_reached total=2`.
    - MySQL `gld_dataset` wrote 2 rows for label `step11_final_2`.
    - CSV wrote 2 matching rows to `C:\Users\asus\gld-dataset.csv`.
  - Summary verified:
    - topic `gas-leak-detector/F001/dataset/summary`
    - payload label `summary_final_1`, `total_samples=1`, `nulling_profile_id=2`.
  - Final clean sink check after summary test:
    - MySQL `gld_dataset` count `3`
    - CSV count `3`

## Bukti End-to-End Terakhir

Diverifikasi ulang setelah upload CH v0.5.3 + Gateway v0.1.3 dengan pull command `{"requestId":1,"hopList":["0x0064"]}`:

- Gateway:
  - `GW_MESH_READY=1`
  - `GW_MQTT_CONNECT host=CHANGE_ME_MQTT_HOST port=1884 ok=1`
  - `GW_MESH_TX reason=server-pull state=0`
  - `GW_MESH_RX state=0 len=50`
  - `GW_MQTT_PUBLISH topic=gld/gateway/uplink ok=1 frameLen=50 parseStatus=0`
- CH:
  - `CH_RUNTIME_READY star=1 mesh=1`
  - `CH_MESH_RX state=0 len=14`
  - `CH_PULL_PROCESS status=Ok onwardQueued=1 pullStatus=0 txStatus=0`
  - `CH_MESH_TX state=0 len=50`
- Node-RED decoded (`gld/server/decoded`):
  - `requestId=1`
  - `status=0`
  - `recordCount=1`
  - `nodeIdHex=0xF001`
  - `srcIdHex=0x0064`
  - `dstIdHex=0x006F`
  - `seq=107`
  - `decryptOk=true`
  - `gasClass=0 clearGas`
  - `confidence=100`
  - `batteryMv=65535`
  - `dedupKey=0x0064:61441:107:normal`

## Bukti Alarm Push Terakhir

- MQTT subscribe:
  - `C:\Program Files\mosquitto\mosquitto_sub.exe -h 127.0.0.1 -p 1884 -t gld/server/alarm -C 1 -W 45 -v`
- Node-RED alarm:
  - topic `gld/server/alarm`
  - `outer.msgType=16`
  - `outer.typeFlags=208`
  - `outer.alarmFlag=true`
  - `outer.srcIdHex=0x0064`
  - `outer.dstIdHex=0x006F`
  - `nodeIdHex=0xF001`
  - `flags=17`
  - `alarm=true`
  - `externalPower=true`
  - `decryptOk=true`
  - `gasClass=1 LPG`
  - `confidence=30`
  - `batteryMv=65535`

## Sisa Besar

| Step | Status | Fokus |
|---:|---|---|
| 1 | Done | Shared protocol |
| 2 | Done | GLD board bring-up |
| 3 | Done | GLD nulling selftest |
| 4 | Done | GLD STAR TX |
| 5 | Done | CH STAR RX |
| 6 | Done | CH runtime/cache/pull |
| 7 | Done | Gateway MQTT/MESH |
| 8 | Done | Full normal path bench |
| 9 | Done | Alarm push live test |
| 10 | Done | Production GLD running/inference |
| 11a | Done | Nulling service + NVS + MQTT publish |
| 11b | Done | Dataset generation GLD (WiFi+MQTT, START/STOP cmd, stream records) |
| 11c | Done | Node-RED dataset tab, MySQL, CSV, bounded capture, and summary verified |
| 12 | Done | GLD inference pipeline integrated — placeholder model live, `firmware/gld/model/` ready for drop-in replacement |

**Catatan Step 12:** Model training di-out-scope dari repo ini. Placeholder model dari ApplyGasleak dipakai sementara. Untuk replace model: overwrite `firmware/gld/model/model_data.cpp`, `scaler_params.cpp`, `scaler_params.h` dari PC/server training, lalu rebuild `gld_inference_esp32s3`.

## Next Steps (Post-12)

| # | Fokus |
|---|---|
| A | Remote GLD dataset — GLD kirim dataset via LoRa/MQTT ke server tanpa kabel USB |
| B | Model replacement — copy trained `firmware/gld/model/` dari server training ke repo ini, rebuild, upload |

## Catatan

- Port `1884` dipakai untuk Aedes bench karena port `1883` di laptop sedang dikunci service Mosquitto lama.
- Jalur normal/pull sudah clear end-to-end.
- Jalur alarm push live delivery sudah clear end-to-end untuk bench.
- MESH ACK/retry production belum dianggap selesai: Gateway mengirim compact ACK, tetapi CH runtime belum memproses ACK compact dari Gateway dan masih menandai alarm sent setelah TX radio lokal sukses.
