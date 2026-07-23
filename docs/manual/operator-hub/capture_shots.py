"""Capture annotated screenshots of the Pertamina GLD Operator Hub consoles.

Runs the three consoles in their built-in no-hardware / simulator state, feeds
each one representative telemetry so the panels are not empty, then draws
numbered callout boxes on the elements the documentation refers to.
"""
from __future__ import annotations

import json
import pathlib
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

DSF = 1.5  # device scale factor: crisp text without enormous files

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "screenshots"
OUT.mkdir(exist_ok=True)
ANNOTATE_JS = (HERE / "annotate.js").read_text(encoding="utf-8")

HUB = "http://127.0.0.1:5173/"
GLD = "http://127.0.0.1:5174/"
CH = "http://127.0.0.1:5273/"
GW = "http://127.0.0.1:5373/"

# --------------------------------------------------------------------------
# Per-app priming: put realistic data on screen without any hardware attached.
# --------------------------------------------------------------------------

GLD_PRIME = """
async () => {
  const m = await import('/js/mock.js');
  if (!window.__mockOn) { m.toggleMock(); window.__mockOn = true; }
}
"""

CH_LINES = [
    "CH boot: ClusterHead STAR/MESH runtime",
    "Firmware version: 1.4.2",
    "Protocol version: 3",
    "CH_IDS ch=0010 rootGateway=0001",
    "CH_STAR_BEGIN_STATE=0",
    "CH_MESH_BEGIN_STATE=0",
    "CH_RUNTIME_READY star=1 mesh=1",
    "CH_ACK_PROFILE helloIntervalMs=60000 helloJitterMs=8000 healthTimeoutMs=180000",
    "CH_INFO_JSON " + json.dumps({
        "chId": "0010", "rootGatewayId": "0001",
        "firmwareVersion": "1.4.2", "protocolVersion": "3", "caps": "0x0F",
        "starLora": {"freqMHz": 920.0, "bwKHz": 125, "sf": 7, "cr": 5, "syncWord": 18, "txPowerDbm": 17},
        "meshLora": {"freqMHz": 921.0, "bwKHz": 125, "sf": 9, "cr": 5, "syncWord": 52, "txPowerDbm": 17},
        "helloProfile": {"intervalMs": 60000, "jitterMs": 8000, "healthTimeoutMs": 180000},
    }),
    "CH_STATE state=JOINED reason=parent-selected",
    "CH_PARENT_CANDIDATE id=0001 parent=0000 depth=0 rssi=-74 snr=9 battMv=4110 caps=0x0F",
    "CH_PARENT_CANDIDATE id=0011 parent=0001 depth=1 rssi=-98 snr=2 battMv=3820 caps=0x03",
    "CH_PARENT_CANDIDATE id=0012 parent=0001 depth=1 rssi=-105 snr=-3 battMv=3640 caps=0x01",
    "CH_PARENT_SELECT parent=0001 parentRssi=-74 parentSnr=9 parentDepth=0",
    "CH_BATT_MV=4020 stableCount=6 threshold=3150",
    "CH_BATT_MV=4005 stableCount=6 threshold=3150",
    "CH_BATT_MV=3996 stableCount=6 threshold=3150",
    "CH_BATT_MV=3984 stableCount=6 threshold=3150",
    "CH_BATT_MV=3975 stableCount=6 threshold=3150",
    "CH_BATT_MV=3968 stableCount=6 threshold=3150",
    "CH_BATT_MV=3961 stableCount=6 threshold=3150",
    "CH_BATT_MV=3957 stableCount=6 threshold=3150",
    "CH_STATUS_JSON " + json.dumps({
        "state": "JOINED", "batteryMv": 3957, "uptimeSec": 8465,
        "parentId": "0001", "parentRssi": -74, "parentSnr": 9,
        "meshDepth": 1, "nodeCount": 3,
    }),
    "CH_HELLO_TX parentId=0001 battMv=3957 uptimeSec=8465 depth=1 caps=0x0F ackWait=1",
    "CH_HELLO_ACK_RECV",
    "CH_STAR_RX rssi=-83 snr=8",
    "CH_CACHE_ENTRY node=1001 seq=4120 alarm=0 extPwr=1 unsent=0 ageMs=0",
    "CH_STAR_RX rssi=-101 snr=1",
    "CH_CACHE_ENTRY node=1002 seq=3887 alarm=0 extPwr=0 unsent=2 ageMs=0",
    "CH_CACHE_ENTRY node=1003 seq=951 alarm=1 extPwr=0 unsent=1 ageMs=48000",
    "CH_CACHE_SUMMARY used=3 unsentNormal=2 unsentAlarm=1",
    "CH_MESH_PARSE src=0001 dst=0010 typeFlags=48 len=12",
    "CH_PULL_PROCESS requestId=0007 status=Ok dataStatus=DataOk records=3 responseSize=96 onwardQueued=1",
]

CH_PRIME = """
async (lines) => {
  const p = await import('/js/ch-protocol.js');
  for (const line of lines) p.handleLine(line);
}
"""

GW_STATUS = {
    "state": "ONLINE", "gatewayId": "0001", "firmwareVersion": "1.3.0",
    "protocolVersion": 3, "uptimeMs": 5346000, "ip": "192.168.1.42",
    "wifi": True, "mqtt": True, "meshReady": True,
    "mqttQueueDepth": 0, "mqttQueueCapacity": 64, "mqttQueueDropped": 0,
    "mqttQueuePublished": 1842,
    "wifiSsid": "PERTAMINA-FIELD", "wifiRssi": -58, "wifiChannel": 6,
    "wifiMac": "A0:B7:65:1C:2D:9E",
    "mqttHost": "192.168.1.17", "mqttPort": 1884, "mqttState": "connected",
    "mqttAuthConfigured": True, "mqttSubscriptionsReady": True,
    "topicRoot": "gld/gateway",
    "meshFreqMhz": 921.0, "meshBandwidthKhz": 125, "meshSpreadingFactor": 9,
    "meshCodingRate": 5, "meshSyncWord": 52, "meshTxPowerDbm": 17, "meshPreamble": 8,
}

GW_UPLINKS = [
    {"msgType": 0x33, "srcId": "0010", "dstId": "0001", "seq": 812, "payloadLen": 14,
     "rssi": -74, "snr": 9, "parseStatus": "ok",
     "topology": {"reportType": "CH_HELLO", "chId": "0010", "parentId": "0001",
                  "batteryMv": 3957, "routeFlags": 0x0F}},
    {"msgType": 0x31, "srcId": "0010", "dstId": "0001", "seq": 811, "payloadLen": 96,
     "rssi": -76, "snr": 8, "parseStatus": "ok"},
    {"msgType": 0x10, "srcId": "1001", "dstId": "0001", "seq": 4120, "payloadLen": 32,
     "rssi": -83, "snr": 7, "parseStatus": "ok"},
    {"msgType": 0x33, "srcId": "0011", "dstId": "0010", "seq": 209, "payloadLen": 14,
     "rssi": -98, "snr": 2, "parseStatus": "ok",
     "topology": {"reportType": "CH_HELLO", "chId": "0011", "parentId": "0010",
                  "batteryMv": 3820, "routeFlags": 0x03}},
    {"msgType": 0x34, "srcId": "0012", "dstId": "FFFF", "seq": 7, "payloadLen": 8,
     "rssi": -105, "snr": -3, "parseStatus": "ok",
     "topology": {"reportType": "CH_CONFIG_REQUEST", "chId": "0012", "parentId": "0000",
                  "batteryMv": 3640, "routeFlags": 0x01}},
]

GW_PRIME = """
async ({status, uplinks}) => {
  const p = await import('/js/gw-protocol.js');
  p.handleStatus(status);
  for (const u of uplinks.slice().reverse()) p.handleUplink(u, JSON.stringify(u));
  p.logCommand('pull', 'gld/gateway/cmd/pull', JSON.stringify({hopList:['0010'],requestId:'0007'}));
  p.logCommand('node', 'gld/gateway/cmd/node', JSON.stringify({cluster:'0010',nodeId:'1001',ttl:3,hex:'00'}));
}
"""

GW_BOOTLOG = [
    "GW boot: Pertamina GLD Gateway",
    "Firmware version: 1.3.0",
    "GW_WIFI_CONNECTING ssid=PERTAMINA-FIELD",
    "GW_WIFI_OK ip=192.168.1.42 rssi=-58 ch=6",
    "GW_MQTT_CONNECTING host=192.168.1.17 port=1884",
    "GW_MQTT_OK subscriptions=2 topicRoot=gld/gateway",
    "GW_MESH_BEGIN_STATE=0",
    "GW_MESH_LORA freq=921.0 bw=125 sf=9 cr=5 sync=0x34 tx=17",
    "GW_STATUS published state=ONLINE queue=0/64",
    "GW_MESH_RX src=0010 dst=0001 type=0x33 rssi=-74 snr=9",
    "GW_MQTT_PUBLISH gld/gateway/uplink len=180",
    "GW_MESH_RX src=1001 dst=0001 type=0x10 rssi=-83 snr=7",
    "GW_MQTT_PUBLISH gld/gateway/uplink len=214",
]

GW_LOG_PRIME = """
async (lines) => {
  const u = await import('/js/gw-ui.js');
  for (const line of lines) u.appendLog(line, 'in');
}
"""

CH_UNLOCK = """
async () => {
  const u = await import('/js/ch-ui.js');
  const s = await import('/js/ch-state.js');
  s.state.expertUnlocked = true;
  u.applyExpertLockUi();
}
"""

GW_UNLOCK = """
async () => {
  const u = await import('/js/gw-ui.js');
  const s = await import('/js/gw-state.js');
  s.state.expertUnlocked = true;
  u.applyExpertLockUi();
}
"""

# --------------------------------------------------------------------------
# Shot definitions
# --------------------------------------------------------------------------
# step kinds: ("click", sel) ("js", code) ("jsarg", code, arg) ("wait", ms)
#             ("scroll", sel, y) ("hide", sel)

SHOTS = [
    # ---------------- HUB ----------------
    dict(id="00-hub-landing", url=HUB, vp=(1920, 1500), prime=[], boxes=[
        dict(sel="#tabs", n="1", label="Tab bar: GLD / CH / Gateway", place="below"),
        dict(sel='[data-launch-app="gld"]', n="2", label="Kartu GLD"),
        dict(sel='[data-launch-app="ch"]', n="3", label="Kartu CH"),
        dict(sel='[data-launch-app="gw"]', n="4", label="Kartu Gateway"),
        dict(sel="#readiness", n="5", label="Status preflight", color="blue", place="below"),
        dict(sel="#homeBtn", n="6", label="Kembali ke pemilihan", color="blue", place="below"),
    ]),

    # ---------------- GLD ----------------
    dict(id="gld-01-shell", url=GLD, vp=(1920, 1500), prime="gld", boxes=[
        dict(sel=".strip-gauges", n="1", label="Badge status live", place="below"),
        dict(sel="#opsPanelBtn", n="2", label="Ops Panel"),
        dict(sel="#firmwareUploadBtn", n="3", label="Firmware Upload"),
        dict(sel="#portSetupBtn", n="4", label="Port Setup"),
        dict(sel=".segmented-nav-track", n="5", label="6 tab kerja GLD", color="blue", place="below"),
    ]),
    dict(id="gld-02-portsetup", url=GLD, crop=["#setupPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("click", "#portSetupBtn"), ("wait", 400)], boxes=[
        dict(sel="#portSelect", n="1", label="Pilih COM hasil scan"),
        dict(sel="#refreshPortsBtn", n="2", label="Scan ulang", place="below"),
        dict(sel=".manual-port-row", n="3", label="Isi COM manual", place="below"),
        dict(sel="#connectBtn", n="4", label="Connect Serial", place="below"),
        dict(sel="#portDetail", n="5", label="Detail port terpilih", color="blue"),
    ]),
    dict(id="gld-03-fwdialog", url=GLD, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="gld",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1500)], boxes=[
        dict(sel="#firmwareUploadEnv", n="1", label="Pilih ENV firmware"),
        dict(sel="#firmwareUploadPort", n="2", label="Pilih COM target"),
        dict(sel="label:has(#firmwareResetNvs)", n="3", label="Reset NVS?", place="right"),
        dict(sel="#firmwareUploadStatus", n="4", label="Baris status", color="blue"),
        dict(sel="#firmwareUploadConfirmBtn", n="5", label="Klik Upload", place="below"),
    ]),
    dict(id="gld-04-fwprogress", url=GLD, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="gld",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1500),
                ("js", """() => {
                    const s = document.getElementById('firmwareUploadStatus');
                    s.textContent = 'Disconnecting serial, then uploading to COM7…';
                    s.dataset.state = 'loading';
                    s.setAttribute('aria-busy','true');
                    document.getElementById('firmwareUploadConfirmBtn').disabled = true;
                    document.getElementById('firmwareUploadCancelBtn').disabled = true;
                    document.getElementById('firmwareResetNvs').disabled = true;
                }""")], boxes=[
        dict(sel="#firmwareUploadStatus", n="1", label="Progres upload berjalan"),
        dict(sel=".modal-actions", n="2", label="Tombol terkunci selama upload", color="blue", place="below"),
    ]),
    dict(id="gld-05-fwdone", url=GLD, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="gld",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1500),
                ("js", """() => {
                    const s = document.getElementById('firmwareUploadStatus');
                    s.textContent = 'Upload berhasil. Parameter NVS dipertahankan. Connected to COM7.';
                    s.dataset.state = 'success';
                    document.getElementById('firmwareUploadCancelBtn').textContent = 'Close';
                }""")], boxes=[
        dict(sel="#firmwareUploadStatus", n="1", label="Upload selesai + reconnect", color="green"),
    ]),
    dict(id="gld-06-running", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="running"]'), ("wait", 4000)], boxes=[
        dict(sel=".gauge-row", n="1", label="4 kartu ringkas", place="below"),
        dict(sel=".module--full-bleed .toolbar", n="2", label="Toolbar telemetry"),
        dict(sel="#sensorChannelsLeft", n="3", label="Kanal 1-4", color="blue"),
        dict(sel=".chart-wrap", n="4", label="Grafik 8 kanal", color="blue"),
        dict(sel="#sensorChannelsRight", n="5", label="Kanal 5-8", color="blue"),
        dict(sel="#runningSettingsBtn", n="6", label="Konfigurasi Running", place="above"),
    ]),
    dict(id="gld-07-running-boot", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("wait", 2500), ("js", "() => { document.querySelector('#running details.disclosure').open = true; }"),
                ("scrollel", "#running details.disclosure")], boxes=[
        dict(sel="#running details.disclosure", n="1", label="Power & Boot Health"),
    ]),
    dict(id="gld-08-runsettings-a", url=GLD, crop=["#runningSettingsPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("wait", 1500), ("click", "#runningSettingsBtn"), ("wait", 500)], boxes=[
        dict(sel="#pollIntervalMs", n="1", label="Poll interval (default 500 ms)", place="right"),
        dict(sel="label:has(#chartYAxisFixed)", n="2", label="Kunci sumbu Y", place="above"),
        dict(sel="#targetDeviceId", n="3", label="GLD ID target", place="right"),
        dict(sel="#targetChAddress", n="4", label="Alamat CH tujuan", place="right"),
    ]),
    dict(id="gld-09-runsettings-b", url=GLD, crop=["#runningSettingsPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("wait", 1500), ("click", "#runningSettingsBtn"), ("wait", 500),
                ("scrolldrawer", "#runningSettingsPanel .drawer-panel", "#loraFreqMHz")], boxes=[
        dict(sel="#loraFreqMHz", n="1", label="Frekuensi STAR", place="right"),
        dict(sel="#applyLoraConfigBtn", n="2", label="Apply LoRa"),
        dict(sel="#sensorCheckSummary", n="3", label="Ringkasan MQ check", color="blue"),
    ]),
    dict(id="gld-10-dataset", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="dataset"]'), ("wait", 500)], boxes=[
        dict(sel="#switchDatasetBtn", n="1", label="Switch to Dataset"),
        dict(sel="#datasetSettingsBtn", n="2", label="Konfigurasi Dataset"),
        dict(sel="#datasetWizard", n="3", label="Wizard 6 langkah", color="blue", place="below"),
        dict(sel="#dataset .gauge-row", n="4", label="Status sesi", color="blue", place="below"),
        dict(sel="#startDatasetBtn", n="5", label="Start (aktif setelah Confirm)"),
        dict(sel="#stopDatasetBtn", n="6", label="Stop", place="below"),
    ]),
    dict(id="gld-11-dataset-rows", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="dataset"]'), ("wait", 500),
                ("scrollel", ".dataset-table-wrap")], boxes=[
        dict(sel=".dataset-table-wrap", n="1", label="Baris dataset terbaru"),
        dict(sel="#downloadDatasetCsvBtn", n="2", label="Snapshot CSV"),
        dict(sel="#openDatasetFolderBtn", n="3", label="Buka folder hasil"),
    ]),
    dict(id="gld-12-datasetsettings", url=GLD, crop=["#datasetSettingsPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="dataset"]'), ("wait", 300),
                ("click", "#datasetSettingsBtn"), ("wait", 500)], boxes=[
        dict(sel="#wifiSsid", n="1", label="WiFi GLD", place="right"),
        dict(sel="#mqttHost", n="2", label="Broker MQTT", place="right"),
        dict(sel="#applyConfigBtn", n="3", label="Apply GLD Settings"),
        dict(sel="#useThisPcBtn", n="4", label="Pakai PC ini", place="above"),
    ]),
    dict(id="gld-13-datasetsettings-b", url=GLD, crop=["#datasetSettingsPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="dataset"]'), ("wait", 300),
                ("click", "#datasetSettingsBtn"), ("wait", 500),
                ("scrolldrawer", "#datasetSettingsPanel .drawer-panel", "#confirmDatasetConfigBtn")], boxes=[
        dict(sel="#datasetLabel", n="1", label="Label kelas data", place="right"),
        dict(sel="#sampleIntervalMs", n="2", label="Interval sampling", place="right"),
        dict(sel="label:has(#datasetNullingFirst)", n="3", label="Nulling dulu?", place="above"),
        dict(sel="#confirmDatasetConfigBtn", n="4", label="Confirm Config & Create File"),
    ]),
    dict(id="gld-14-nulling", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="nulling"]'), ("wait", 300),
                ("click", '#nulling [data-mode="nulling"]'), ("wait", 14000)], boxes=[
        dict(sel='#nulling [data-mode="nulling"]', n="1", label="Switch to Nulling"),
        dict(sel="#nullingSummary", n="2", label="Ringkasan proses", color="blue"),
        dict(sel="#nullingChannels", n="3", label="Kartu per kanal", color="blue", place="below"),
        dict(sel="#nullingSettingsBtn", n="4", label="Ambang nulling"),
    ]),
    dict(id="gld-15-nullinglog", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="nulling"]'), ("wait", 300),
                ("click", '#nulling [data-mode="nulling"]'), ("wait", 16000),
                ("scrollel", "#nullingLog")], boxes=[
        dict(sel="#nullingLog", n="1", label="Raw nulling log"),
    ]),
    dict(id="gld-16-nullingsettings", url=GLD, crop=["#nullingSettingsPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="nulling"]'), ("wait", 300),
                ("click", "#nullingSettingsBtn"), ("wait", 500)], boxes=[
        dict(sel="#nullingThresholdV", n="1", label="Minimum delta threshold", place="right"),
        dict(sel="#applyNullingConfigBtn", n="2", label="Apply Thresholds", place="below"),
        dict(sel="#refreshNullingConfigBtn", n="3", label="Baca ulang dari GLD", place="below"),
    ]),
    dict(id="gld-17-qc", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="qc"]'), ("wait", 1200)], boxes=[
        dict(sel="#qcGroupNavTrack", n="1", label="Grup MQ / TPL"),
        dict(sel="#qcSubnavTrack", n="2", label="All Sensor + 8 kanal", place="below"),
        dict(sel="#qcLatchBtn", n="3", label="QC-OFF / QC-ON"),
        dict(sel="#qcPanels", n="4", label="Kartu verdict per kanal", color="blue", place="below"),
    ]),
    dict(id="gld-18-qc-channel", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="qc"]'), ("wait", 1200),
                ("click", '[data-qctab="0"]'), ("wait", 800)], boxes=[
        dict(sel="#qcPanels", n="1", label="Panel satu kanal (MQ8)", place="below"),
    ]),
    dict(id="gld-19-log", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="log"]'), ("wait", 3000)], boxes=[
        dict(sel="#pauseLogBtn", n="1", label="Pause / Resume"),
        dict(sel="#downloadLogBtn", n="2", label="Unduh ke browser"),
        dict(sel="#saveSessionLogBtn", n="3", label="Simpan ke disk", place="below"),
        dict(sel="#serialLog", n="4", label="Aliran serial mentah", color="blue", place="below"),
    ]),
    dict(id="gld-20-ops", url=GLD, crop=["#opsPanel .drawer-panel"], vp=(1920, 1500), prime="gld",
         steps=[("wait", 1200), ("click", "#opsPanelBtn"), ("wait", 500)], boxes=[
        dict(sel="#fleetCountBadge", n="1", label="Slot armada", place="right"),
        dict(sel="#addSlotBtn", n="2", label="Tambah slot GLD", place="right"),
        dict(sel="#opsPanel .control-grid", n="3", label="Perintah cepat", color="blue", place="right"),
        dict(sel='#opsPanel [data-mode="dataset"]', n="4", label="Ganti mode perangkat"),
    ]),
    dict(id="gld-21-expert", url=GLD, vp=(1920, 1500), prime="gld",
         steps=[("click", '.tab[data-tab="expert"]'), ("wait", 400)], boxes=[
        dict(sel="#unlockExpertBtn", n="1", label="Unlock dengan PIN"),
        dict(sel=".terminal-row", n="2", label="Kirim perintah mentah", place="below"),
        dict(sel=".form-grid", n="3", label="Timeout serial & dataset", color="blue", place="below"),
    ]),

    # ---------------- CH ----------------
    dict(id="ch-01-shell", url=CH, vp=(1920, 1500), prime="ch", boxes=[
        dict(sel=".badges", n="1", label="Badge status CH", place="below"),
        dict(sel="#settingsBtn", n="2", label="CH Settings"),
        dict(sel="#firmwareUploadBtn", n="3", label="Firmware Upload"),
        dict(sel="#portSetupBtn", n="4", label="Port Setup"),
        dict(sel="#tabs", n="5", label="5 tab kerja CH", color="blue", place="below"),
    ]),
    dict(id="ch-02-portsetup", url=CH, crop=["#setupPanel"], vp=(1920, 1500), prime="ch",
         steps=[("click", "#portSetupBtn"), ("wait", 400)], boxes=[
        dict(sel="#portSelect", n="1", label="Pilih COM", place="right"),
        dict(sel="#manualPortInput", n="2", label="Override manual", place="right"),
        dict(sel="#connectBtn", n="3", label="Connect", place="below"),
    ]),
    dict(id="ch-03-fwdialog", url=CH, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="ch",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1800)], boxes=[
        dict(sel="#firmwareUploadEnv", n="1", label="ENV: ch / chFieldtest"),
        dict(sel="#firmwareUploadPort", n="2", label="Pilih COM target"),
        dict(sel="label:has(#firmwareResetNvs)", n="3", label="Reset NVS?", place="right"),
        dict(sel="#firmwareUploadStatus", n="4", label="Baris status", color="blue"),
        dict(sel="#firmwareUploadConfirmBtn", n="5", label="Klik Upload", place="below"),
    ]),
    dict(id="ch-04-fwprogress", url=CH, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="ch",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1800),
                ("js", """() => {
                    const s = document.getElementById('firmwareUploadStatus');
                    s.textContent = 'Disconnecting serial, then uploading to COM5…';
                    s.dataset.state = 'loading'; s.setAttribute('aria-busy','true');
                    document.getElementById('firmwareUploadConfirmBtn').disabled = true;
                }""")], boxes=[
        dict(sel="#firmwareUploadStatus", n="1", label="Progres upload"),
    ]),
    dict(id="ch-05-overview-a", url=CH, vp=(1920, 1500), prime="ch", boxes=[
        dict(sel="#refreshOverviewBtn", n="1", label="Refresh (GET_INFO+GET_STATUS)"),
        dict(sel="#pollToggleBtn", n="2", label="Start polling"),
        dict(sel=".grid .card:nth-child(1)", n="3", label="State", place="below"),
        dict(sel=".grid .card:nth-child(2)", n="4", label="Battery", place="below"),
        dict(sel=".grid .card:nth-child(3)", n="5", label="Uptime", place="below"),
        dict(sel=".grid .card:nth-child(4)", n="6", label="Nodes seen", place="below"),
        dict(sel=".grid .card:nth-child(5)", n="7", label="Identity", color="blue", place="below"),
        dict(sel=".grid .card:nth-child(6)", n="8", label="Active parent", color="blue", place="below"),
    ]),
    dict(id="ch-06-overview-b", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("scrollel", "#pullStepper")], boxes=[
        dict(sel=".grid .card:nth-child(7)", n="9", label="CH_HELLO keepalive"),
        dict(sel=".grid .card:nth-child(8)", n="10", label="CH_CONFIG discovery"),
        dict(sel=".grid .card:nth-child(9)", n="11", label="STAR radio (ke GLD)", color="blue"),
        dict(sel=".grid .card:nth-child(10)", n="12", label="MESH radio (ke Gateway)", color="blue"),
        dict(sel="#pullStepper", n="13", label="3 langkah pull request", color="green", place="below"),
    ]),
    dict(id="ch-07-overview-c", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("scrollel", "#battChart")], boxes=[
        dict(sel="#pullStepper", n="1", label="Stepper pull request"),
        dict(sel="#battChart", n="2", label="Tren baterai", color="blue"),
    ]),
    dict(id="ch-08-settings-a", url=CH, crop=["#settingsPanel"], vp=(1920, 1500), prime="ch",
         steps=[("click", "#settingsBtn"), ("wait", 500)], boxes=[
        dict(sel="#setChId", n="1", label="CH ID (0010-0FFF)", place="right"),
        dict(sel="#setRootGw", n="2", label="Root gateway (0001-000F)", place="right"),
        dict(sel="#applyChIdBtn", n="3", label="Apply + reboot", place="below"),
    ]),
    dict(id="ch-09-settings-b", url=CH, crop=["#settingsPanel"], vp=(1920, 1500), prime="ch",
         steps=[("click", "#settingsBtn"), ("wait", 500),
                ("scrolldrawer", "#settingsPanel .body", "#applyMeshLoraBtn")], boxes=[
        dict(sel="#applyStarLoraBtn", n="1", label="STAR LoRa -> harus sama dengan GLD"),
        dict(sel="#applyMeshLoraBtn", n="2", label="MESH LoRa -> harus sama dengan Gateway"),
    ]),
    dict(id="ch-10-nodes", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("click", '.tab[data-tab="nodes"]'), ("wait", 500)], boxes=[
        dict(sel="#refreshNodesBtn", n="1", label="Refresh (GET_NODES)"),
        dict(sel="#nodesTable thead", n="2", label="Kolom NodeCache", place="below"),
        dict(sel="#nodesBody", n="3", label="Satu baris per GLD", color="blue", place="below"),
        dict(sel="#nodes .hint, .panel[data-panel='nodes'] .hint", n="4", label="Aturan stale 300 s", color="blue"),
    ]),
    dict(id="ch-11-mesh", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("click", '.tab[data-tab="mesh"]'), ("wait", 500)], boxes=[
        dict(sel="#sendHelloBtn", n="1", label="Paksa hello"),
        dict(sel="#clearParentBtn", n="2", label="Hapus parent NVS"),
        dict(sel="#forceFailoverBtn", n="3", label="Paksa failover"),
        dict(sel="#parentsTable", n="4", label="Kandidat parent + kualitas link", color="blue", place="below"),
    ]),
    dict(id="ch-12-mesh-pull", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("click", '.tab[data-tab="mesh"]'), ("wait", 500),
                ("scrollel", "#pullSeenAt")], boxes=[
        dict(sel=".panel[data-panel='mesh'] .card", n="1", label="Detail pull request terakhir"),
    ]),
    dict(id="ch-13-log", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("click", '.tab[data-tab="log"]'), ("wait", 500)], boxes=[
        dict(sel="#pauseLogBtn", n="1", label="Pause"),
        dict(sel="#downloadLogBtn", n="2", label="Download"),
        dict(sel="#saveLogBtn", n="3", label="Save to disk", place="below"),
        dict(sel="#serialLog", n="4", label="Log serial CH", color="blue", place="below"),
    ]),
    dict(id="ch-14-expert", url=CH, vp=(1920, 1500), prime="ch",
         steps=[("click", '.tab[data-tab="expert"]'), ("wait", 300),
                ("js", CH_UNLOCK), ("wait", 300)], boxes=[
        dict(sel="#lockBtn", n="1", label="Lock / Unlock (PIN)"),
        dict(sel=".cmdrow", n="2", label="Perintah bebas", place="below"),
        dict(sel=".panel[data-panel='expert'] .btn-row", n="3", label="Perintah cepat", color="blue", place="below"),
    ]),

    # ---------------- GATEWAY ----------------
    dict(id="gw-01-shell", url=GW, vp=(1920, 1500), prime="gw", boxes=[
        dict(sel=".badges", n="1", label="Badge status Gateway", place="below"),
        dict(sel="#brokerSetupBtn", n="2", label="Gateway Setup"),
        dict(sel="#firmwareUploadBtn", n="3", label="Firmware Upload"),
        dict(sel="#tabs", n="4", label="6 tab kerja Gateway", color="blue", place="below"),
    ]),
    dict(id="gw-02-fwdialog", url=GW, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="gw",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1800)], boxes=[
        dict(sel="#firmwareUploadPort", n="1", label="Pilih COM target"),
        dict(sel="label:has(#firmwareResetNvs)", n="2", label="Reset NVS?", place="right"),
        dict(sel="#firmwareUploadStatus", n="3", label="Baris status", color="blue"),
        dict(sel="#firmwareUploadConfirmBtn", n="4", label="Klik Upload", place="below"),
    ]),
    dict(id="gw-03-fwprogress", url=GW, crop=[".upload-dialog-box"], vp=(1920, 1500), prime="gw",
         steps=[("click", "#firmwareUploadBtn"), ("wait", 1800),
                ("js", """() => {
                    const s = document.getElementById('firmwareUploadStatus');
                    s.textContent = 'Disconnecting serial, then uploading to COM9…';
                    s.dataset.state = 'loading'; s.setAttribute('aria-busy','true');
                    document.getElementById('firmwareUploadConfirmBtn').disabled = true;
                }""")], boxes=[
        dict(sel="#firmwareUploadStatus", n="1", label="Progres upload"),
    ]),
    dict(id="gw-04-setup-a", url=GW, crop=["#setupPanel"], vp=(1920, 1500), prime="gw",
         steps=[("click", "#brokerSetupBtn"), ("wait", 500)], boxes=[
        dict(sel="#serialSetupStep", n="1", label="Langkah 1: COM"),
        dict(sel="#wifiSetupStep", n="2", label="Langkah 2: Wi-Fi (terkunci)", color="blue"),
    ]),
    dict(id="gw-05-setup-b", url=GW, crop=["#setupPanel"], vp=(1920, 1500), prime="gw",
         steps=[("click", "#brokerSetupBtn"), ("wait", 500),
                ("scrolldrawer", "#setupPanel .body", "#mqttSetupStep")], boxes=[
        dict(sel="#mqttSetupStep", n="3", label="Langkah 3: MQTT (terkunci)"),
    ]),
    dict(id="gw-06-setup-c", url=GW, crop=["#setupPanel"], vp=(1920, 1500), prime="gw",
         steps=[("click", "#brokerSetupBtn"), ("wait", 500),
                ("scrolldrawer", "#setupPanel .body", "#meshApplyStatus")], boxes=[
        dict(sel="#meshLoraSetupStep", n="4", label="MESH LoRa (butuh COM saja)"),
    ]),
    dict(id="gw-07-overview-a", url=GW, vp=(1920, 1500), prime="gw", boxes=[
        dict(sel="#refreshOverviewBtn", n="1", label="Refresh"),
        dict(sel=".grid .card:nth-child(1)", n="2", label="State", place="below"),
        dict(sel=".grid .card:nth-child(2)", n="3", label="Umur status (~10 s)", place="below"),
        dict(sel=".grid .card:nth-child(3)", n="4", label="WiFi / MQTT / Mesh", color="blue", place="below"),
        dict(sel=".grid .card:nth-child(4)", n="5", label="Antrean uplink", color="blue", place="below"),
        dict(sel=".grid .card:nth-child(5)", n="6", label="Identity", color="green", place="below"),
    ]),
    dict(id="gw-08-overview-b", url=GW, vp=(1920, 1500), prime="gw",
         steps=[("scrollel", "#ovMeshFrequency")], boxes=[
        dict(sel=".grid .card:nth-child(6)", n="7", label="Wi-Fi gateway"),
        dict(sel=".grid .card:nth-child(7)", n="8", label="MQTT gateway"),
        dict(sel=".grid .card:nth-child(8)", n="9", label="MESH radio", color="blue"),
    ]),
    dict(id="gw-09-uplinks", url=GW, vp=(1920, 1500), prime="gw",
         steps=[("click", '.tab[data-tab="uplinks"]'), ("wait", 500)], boxes=[
        dict(sel="#uplinksTable thead", n="1", label="Kolom frame MESH", place="below"),
        dict(sel="#uplinksBody", n="2", label="Frame terbaru di atas", color="blue", place="below"),
        dict(sel="#clearUplinksBtn", n="3", label="Bersihkan tabel"),
    ]),
    dict(id="gw-10-topology", url=GW, vp=(1920, 1500), prime="gw",
         steps=[("click", '.tab[data-tab="topology"]'), ("wait", 500)], boxes=[
        dict(sel="#topologyNodesTable", n="1", label="Status terakhir tiap CH", place="below"),
        dict(sel="#topologyEventsTable", n="2", label="Umpan event mentah", color="blue", place="below"),
    ]),
    dict(id="gw-11-commands", url=GW, vp=(1920, 1500), prime="gw",
         steps=[("click", '.tab[data-tab="commands"]'), ("wait", 500)], boxes=[
        dict(sel=".compose-grid .card:nth-child(1)", n="1", label="Pull request ke CH"),
        dict(sel=".compose-grid .card:nth-child(2)", n="2", label="Node command ke GLD"),
        dict(sel="#commandLogTable", n="3", label="Log perintah terkirim", color="blue", place="below"),
    ]),
    dict(id="gw-12-bootlog", url=GW, vp=(1920, 1500), prime="gw",
         steps=[("click", '.tab[data-tab="log"]'), ("wait", 500)], boxes=[
        dict(sel="#bootLog", n="1", label="Log boot & runtime 115200 baud", place="below"),
        dict(sel=".panel[data-panel='log'] .actions", n="2", label="Pause / unduh / simpan"),
    ]),
    dict(id="gw-13-firmware", url=GW, vp=(1920, 1500), prime="gw",
         steps=[("click", '.tab[data-tab="firmware"]'), ("wait", 300),
                ("js", GW_UNLOCK), ("wait", 300)], boxes=[
        dict(sel="#lockBtn", n="1", label="Lock / Unlock (PIN)"),
        dict(sel="#fwEnvSelect", n="2", label="Profil firmware", place="right"),
        dict(sel="#fwPickBtn", n="3", label="Pilih folder paket", place="below"),
        dict(sel="#fwUploadBtn", n="4", label="Upload & flash", place="below"),
    ]),
]


def clip_for(page, shot, vw: int, vh: int):
    """Screenshot region: the drawer/dialog when the shot names one, otherwise
    the full width trimmed to the last row that carries content."""
    pad = 28
    if shot.get("crop"):
        box = page.evaluate("(sels) => window.__cropBox(sels)", shot["crop"])
        if box:
            left = max(0, box["left"] - pad)
            top = max(0, box["top"] - pad)
            right = min(vw, box["right"] + pad)
            bottom = min(vh, box["bottom"] + pad)
            return {"x": left, "y": top,
                    "width": max(80, right - left), "height": max(80, bottom - top)}
    bottom = page.evaluate("() => window.__contentBottom()")
    height = min(vh, max(320, bottom + pad))
    return {"x": 0, "y": 0, "width": vw, "height": height}


def prime_page(page, kind):
    if kind == "gld":
        page.evaluate(GLD_PRIME)
        page.wait_for_timeout(2500)
    elif kind == "ch":
        page.evaluate(CH_PRIME, CH_LINES)
        page.wait_for_timeout(500)
    elif kind == "gw":
        page.evaluate(GW_PRIME, {"status": GW_STATUS, "uplinks": GW_UPLINKS})
        page.evaluate(GW_LOG_PRIME, GW_BOOTLOG)
        page.wait_for_timeout(500)


def run_steps(page, steps):
    for step in steps or []:
        kind = step[0]
        if kind == "click":
            page.click(step[1], timeout=8000)
        elif kind == "js":
            page.evaluate(step[1])
        elif kind == "wait":
            page.wait_for_timeout(step[1])
        elif kind == "scrollel":
            page.evaluate(
                "(sel) => { const e = document.querySelector(sel);"
                " if (e) e.scrollIntoView({block:'center'}); }", step[1])
            page.wait_for_timeout(350)
        elif kind == "scrolldrawer":
            page.evaluate(
                "([panelSel, targetSel]) => {"
                " const p = document.querySelector(panelSel), t = document.querySelector(targetSel);"
                " if (p && t) p.scrollTop = t.offsetTop - 120; }", [step[1], step[2]])
            page.wait_for_timeout(350)
        elif kind == "hide":
            page.evaluate("(sel) => { const e = document.querySelector(sel);"
                          " if (e) e.style.visibility='hidden'; }", step[1])


def main():
    only = sys.argv[1:] or None
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for shot in SHOTS:
            if only and not any(shot["id"].startswith(o) for o in only):
                continue
            w, h = shot["vp"]
            ctx = browser.new_context(viewport={"width": w, "height": h},
                                      device_scale_factor=DSF,
                                      color_scheme="light")
            page = ctx.new_page()
            page.add_init_script(ANNOTATE_JS)
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            # The consoles hold an open SSE stream, so "networkidle" never fires.
            page.goto(shot["url"], wait_until="load", timeout=30000)
            page.wait_for_timeout(1500)
            try:
                prime_page(page, shot.get("prime"))
                run_steps(page, shot.get("steps"))
                page.wait_for_timeout(250)
                boxes = shot["boxes"]
                if shot.get("crop"):
                    # Drawers and dialogs are too narrow for text tags; the
                    # numbers are explained in the slide body instead.
                    boxes = [{**b, "label": ""} for b in boxes]
                page.evaluate("(specs) => window.__ann(specs)", boxes)
                page.wait_for_timeout(200)
                path = OUT / f"{shot['id']}.png"
                page.screenshot(path=str(path), clip=clip_for(page, shot, w, h))
                print(f"OK   {shot['id']} -> {Image.open(path).size}")
            except Exception as exc:  # keep going; report at the end
                print(f"FAIL {shot['id']}: {type(exc).__name__}: {str(exc)[:180]}")
            if errs:
                print(f"     console errors: {errs[:2]}")
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
