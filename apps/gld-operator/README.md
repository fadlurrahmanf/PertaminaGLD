# GLD Operator Lite

Lightweight GLD operator console. The UI is plain HTML/CSS/JS. Full desktop-like
features are provided by a small local Python bridge instead of Electron.

## Recommended Run (zero-install)

Copy the whole `apps/gld-operator` folder to the target Windows PC (including
`python-embed/`, which bundles Python 3.12 with `pyserial` and `paho-mqtt`
already installed) and double-click:

```text
run-gld-operator.bat
```

No system Python, `pip install`, or any other setup is required - the batch
file launches the bundled `python-embed\python.exe` directly. It only falls
back to a `python` on the system PATH if `python-embed\` is missing (e.g. a
checkout that hasn't fetched the bundle).

Open:

```text
http://127.0.0.1:5174/
```

To run GLD, CH, and Gateway together behind one switcher UI instead, use
`apps/operator-hub/run-operator-hub.bat` and open `http://127.0.0.1:5173/`.

### Rebuilding python-embed (maintainers only)

`python-embed/` is a committed, ready-to-run Python distribution, not
generated at install time. Rebuild it only when `requirements.txt` changes:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
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

Bridge features:

- COM scan and native serial connect at 115200 baud, with manual COM override
  for cases where Windows/pyserial does not enumerate the USB adapter yet.
- Serial command write/read for `APP_PING`, `GET_INFO`, `GET_STATUS`,
  `SET_MODE`, `SET_APP_CONFIG_JSON`, and `SET_DEVICE_ID_JSON`.
- Windows WiFi SSID/password and local IPv4 lookup for `Use this PC`.
- Visual alarm badge plus local sound/mute. Mute is local only and does not send
  an alarm clear command to GLD.
- Local bench MQTT broker on port `1884` from `run-gld-operator.bat`. The safe
  default binds only to `127.0.0.1`. To accept a physical GLD over WiFi,
  explicitly bind a LAN address and set `GLD_BENCH_MQTT_USER` plus a random
  `GLD_BENCH_MQTT_PASSWORD` of at least 16 characters; the bridge refuses an
  unauthenticated non-loopback broker.
- Dataset MQTT command publish when `paho-mqtt` is installed and the local
  broker is reachable.
- Dataset session monitor subscribes to MQTT `cmd/ack`, `dataset/status`,
  `dataset/data`, and `dataset/summary` for the selected GLD. It also shows
  serial fallback events such as `DATASET_START`, `DATASET_RECORD`,
  `DATASET_AUTOSTOP`, and `DATASET_STOP`.
- `Start Dataset` does not run nulling first by default. Use the Dataset tab
  `Run nulling before dataset` option only when the GLD needs a fresh nulling
  profile. With the option off, the app first sends `SET_MODE dataset`, then
  publishes `START_DATASET` with `run_nulling_first=false`.
- Dataset CSV output is saved by default to:

```text
D:\PertaminaGLD\apps\gld-operator\output\datasets
```

  Use the Dataset tab `Save CSV`, `Download CSV`, and `Open Folder` controls.
- For GLD app config, set `mqttHost` to the WiFi IPv4 shown by `Use this PC`
  and keep `mqttPort` as `1884`.
- Firmware packaging and upload use an immutable prebuilt package. From a clean
  checkout, create a schema-v2 package with the repository packager, then select
  the whole generated package directory in the Firmware tab:

```powershell
python firmware/tools/package_firmware_release.py --env gld --device-id F011 --board-profile GLD
```

The bridge verifies schema, source identity, every binary size/hash, flash-set
hash and offset, then invokes packaged esptool against those exact bytes. It
never rebuilds or uploads the current working tree. Privileged bridge requests
also require the same-origin per-run token returned by `/api/health`.

## Fallback HTML-Only Run

If you want to serve the static UI without any bridge features at all (no
serial, no MQTT, no firmware upload), a plain static server also works - this
path needs a system Python since it does not go through `run-gld-operator.bat`:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
python -m http.server 5174 --bind 127.0.0.1
```

In fallback mode the browser must show a COM permission dialog, cannot read the
Windows WiFi password, cannot publish MQTT TCP directly, and cannot run
PlatformIO/esptool. Only one GLD (one serial port) can be connected at a time
in this mode - the multi-GLD Fleet feature (Ops Panel) requires the bridge.

## Size Target

The checked-in app files are tiny; `python-embed/` (bundled interpreter plus
`pyserial`/`paho-mqtt`) adds roughly 30 MB so `run-gld-operator.bat` needs
nothing pre-installed on the target PC. PlatformIO (for the Firmware Upload
tab) and a Chrome/Edge browser are still expected to already be on the
machine - only the Python side of the bridge is bundled.
