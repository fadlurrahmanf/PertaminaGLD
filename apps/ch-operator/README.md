# CH (ClusterHead) Operator Lite

Lightweight operator console for the Pertamina GLD **ClusterHead (CH)** firmware.
The UI is plain HTML/CSS/JS; native features come from a small local Python
bridge instead of Electron.

Unlike the GLD operator, this app is **serial-only over USB**: there is no MQTT
broker and no WiFi. The ClusterHead is a LoRa-only relay and is driven entirely
through its USB serial console. It uses HTTP port **5273** (the GLD operator uses
5173) so both can run side by side.

## Recommended Run (zero-install)

Copy the whole `apps/ch-operator` folder to the target Windows PC (including
`python-embed/`, which bundles Python 3.12 with `pyserial` already installed)
and double-click:

```text
run-ch-operator.bat
```

Then open:

```text
http://127.0.0.1:5273/
```

Open **Port Setup**, pick the CH COM port (e.g. `COM3`), and click **Connect**.

## What the app does

The app has two data sources feeding the same views:

1. **The CH_* log stream the firmware already prints.** Even without any firmware
   change, the Overview and the Nodes table populate from `CH_CACHE_ENTRY`,
   `CH_PARENT_CANDIDATE`, `CH_HELLO_TX`, `CH_STATE`, `CH_IDS`, and the boot header.
2. **Structured `CH_*_JSON` replies** returned by the CH serial command parser
   (added in `firmware/ch/src/ChCommandParser.cpp`) — `CH_INFO_JSON`,
   `CH_STATUS_JSON`, `CH_NODES_JSON`, `CH_PARENTS_JSON`, and `CH_CMD_ACK_JSON`.

Tabs:

- **Overview** — state machine, battery (+trend), uptime, identity (CH id, root
  gateway, firmware/protocol version, capabilities), and the active parent
  (RSSI/SNR/depth).
- **Nodes (GLD)** — every GLD reporting to this CH from the RAM NodeCache: node
  id, seq, alarm, external-power vs battery, unsent count, and a live
  **"last update"** counter. Nodes older than 300 s are flagged stale.
- **Mesh / Parent** — heard parent candidates with link quality, plus actions:
  `SEND_HELLO`, `CLEAR_PARENT_NVS`, `FORCE_FAILOVER`.
- **Log** — raw serial log (pause / download / save-to-disk / clear).
- **Expert** — PIN-gated raw command terminal and firmware upload.

## CH serial command surface

Query commands answer with a single `CH_*_JSON` line; actions acknowledge with
`CH_CMD_ACK_JSON {cmd,status,message}`:

| Command | Effect |
|---|---|
| `APP_PING` | handshake ack |
| `GET_INFO` | `CH_INFO_JSON` (identity, versions, STAR+MESH LoRa params) |
| `GET_STATUS` | `CH_STATUS_JSON` (state, battery, parent, queue depths) |
| `GET_NODES` | `CH_NODES_JSON` (NodeCache dump: which GLDs + ageMs) |
| `GET_PARENTS` | `CH_PARENTS_JSON` (parent candidate table) |
| `SEND_HELLO` | force a `CH_HELLO` now |
| `CLEAR_PARENT_NVS` | forget the stored parent, re-discover |
| `FORCE_FAILOVER` | enter `PARENT_FAILOVER` |
| `RESTART` | `ESP.restart()` |
| `DEBUG_ON` / `DEBUG_OFF` | toggle verbose logging |

`SET_CH_ADDRESS_JSON` validates a four-hex node ID, persists it in NVS, clears
the parent cache, verifies the stored value, and reboots. Root gateway and LoRa
parameters remain build-time constants; their setter commands still reply
`status:"unsupported"`.

## Firmware upload (Expert tab)

Flash a schema-v2 prebuilt CH package over the same COM port. The CH builds on
ESP32-S3 (env `ch`). Create a package with the repository
packager, then select the whole generated directory in the Expert tab:

```powershell
python firmware/tools/package_firmware_release.py --env ch --device-id 0064 --board-profile CH-LATEST
```

The bridge verifies schema, source identity, every binary size/hash, flash-set
hash and offset, then invokes packaged esptool against those exact bytes.
Privileged bridge requests also require the same-origin per-run token from
`/api/health`.

## Rebuilding python-embed (maintainers only)

`python-embed/` is a committed, ready-to-run Python distribution. Rebuild it
only when `requirements.txt` changes:

```powershell
cd D:\Github\PertaminaGLD\apps\ch-operator
Remove-Item -Recurse -Force python-embed
Invoke-WebRequest https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip -OutFile python-embed.zip
Expand-Archive python-embed.zip -DestinationPath python-embed
Remove-Item python-embed.zip
# Uncomment "import site" in python-embed\python312._pth, then:
Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile python-embed\get-pip.py
.\python-embed\python.exe .\python-embed\get-pip.py --no-warn-script-location
.\python-embed\python.exe -m pip install --no-warn-script-location -r requirements.txt
Remove-Item python-embed\get-pip.py
```
