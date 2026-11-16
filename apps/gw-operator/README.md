# Gateway Operator

A local desktop console for the Pertamina GLD **Gateway** firmware
(`firmware/gateway/src/GatewayMqttMeshMain.cpp`, PlatformIO env `gw` /
`gw_hello_ack_fieldtest`, chip ESP32-S3).

It follows the same pattern as [`apps/ch-operator`](../ch-operator) and
[`apps/gld-operator`](../gld-operator): a small stdlib-only Python bridge
(`bridge.py`) serves the static UI and exposes native features plain
browser JavaScript cannot reach (COM ports, MQTT, PlatformIO/esptool).

## Required setup order

The Gateway Setup drawer enforces COM connection, Gateway-side Wi-Fi save and
verification, then MQTT configuration. A save ACK is not treated as proof
that Wi-Fi connected. The serial provisioning surface is intentionally
limited to network provisioning, runtime Gateway identity
(`GET_GATEWAY_ADDRESS` / `SET_GATEWAY_ADDRESS_JSON`), plus `GET_MESH_LORA`
and `SET_MESH_LORA_JSON`; operational traffic still uses MQTT. The gateway
bridges LoRa MESH frames to MQTT entirely on its own:

The versioned Gateway firmware reports Wi-Fi RSSI during **Test Gateway
Wi-Fi**. The Expert UI warns when the signal is at or below -85 dBm; a device
may have an IP address yet still fail to establish a stable MQTT connection.
Move the Gateway or access point closer, or check the Gateway's Wi-Fi antenna.
Earlier firmware without RSSI reporting remains supported.

Step 2 can read the active Windows Wi-Fi profile with **Use this PC Wi-Fi**.
The password travels only through the token-protected localhost bridge into a
masked input; it is not logged or stored by the operator app. If Windows does
not expose the saved key, the SSID is still filled and the password remains
manual.

Step 3 has one shared broker form. The Gateway and operator monitor remain two
independent MQTT clients, but both use the same broker credentials; only their
connect actions and statuses are separate.
For the importable server flow use the PC running Node-RED and its Aedes port
1883; enter the same credentials configured in the Aedes node. **Use This PC
IP** fills the current LAN IP and, once a local broker connection test has
succeeded, the previously tested port, username, password, and topic root.
The saved profile is encrypted with Windows DPAPI for the current Windows user
under `%LOCALAPPDATA%\PertaminaGLD\aedes-broker.dpapi`; it is not in Git. On a
different PC, enter the Aedes settings once and use **Test broker from this PC**
to save that PC's profile. The button does not detect or launch Node-RED; after
changing Aedes credentials or port, enter and test the new values again.

- It publishes to `{topicRoot}/uplink`, `{topicRoot}/status`, and
  `{topicRoot}/topology` on the site broker.
- It subscribes to `{topicRoot}/cmd/pull` and `{topicRoot}/cmd/node` for
  downlink commands.

See `firmware/config/GwConfig.h` for the topic constants and
`server/nodered/README.md` for the payload contracts. So this app is an
**MQTT dashboard + downlink command composer**, plus staged network
provisioning, a boot-log tail, and a verified firmware flasher.

Gateway ID defaults to `0001` and is persisted in NVS at runtime. Gateway
Setup validates the role range `0001` through `000F`, then reboots,
reconnects, and verifies device readback after a change.

## Run it

```
run-gw-operator.bat
```

This opens `http://127.0.0.1:5373/`. The bridge falls back to a system
`python` install if `python-embed\python.exe` is not present (unlike
`ch-operator`/`gld-operator`, a bundled interpreter is **not** committed
here to avoid duplicating ~30 MB of binaries per app — copy
`python-embed/` from either of those apps into this folder if you want a
zero-install launch, or just `pip install -r requirements.txt` for a
system Python).

## Features

The header **Firmware Upload** dialog requires an explicit board shape and
MQTT transport selection. It loads the corresponding
`firmware-packages/<environment>/current-source-20261116` package, displays
its identity, and refuses upload when that package is unavailable. The
previous `latest` packages are retained. A manually selected package remains
available as a separate option. Select TLS only for a broker configured for
TLS; provision the trusted CA and NTP in Gateway Setup.

The owner-confirmed V1 and V3 version labels select separate rectangle builds
with GPIO47 TPL5010 keepalive; V2 selects a circle build. The V1/V3 archives
contain identical PCB and schematic files, so the two labels do not claim
different firmware wiring. The V1/V3 watchdog builds require physical-board
validation. Legacy profiles remain available for existing workflows.

The versioned non-TLS candidates retry a pull at most six times, 1.8 seconds
apart, stopping when a matching response arrives. This mitigates packet loss;
it does not eliminate radio CRC errors. The Gateway keeps one pending retry,
so issue pulls sequentially rather than overlapping requests for different CHs.

To refresh this dated package set from the current firmware source, build all
four Gateway environments with `PGL_OPERATOR_PACKAGE_NAME` set to a new
dedicated directory name, verify the resulting manifests and binaries, then
update the package name used by the Expert dialog and bridge. The normal
post-build default remains `latest` for existing workflows.

- **Gateway Setup** drawer — enforced COM -> verified Gateway Wi-Fi -> MQTT
  sequence, followed by the independent operator-monitor broker connection;
  its independent MESH LoRa section reads and persists frequency, bandwidth,
  SF, CR, sync word, and TX power through COM with verified NVS readback and reboot.
- **Overview** — gateway status (state, WiFi/MQTT/mesh, uplink queue
  depth/dropped/published, IP), refreshed every ~10 s from `/status`.
- **Uplinks** — live table of every mesh frame the gateway forwarded to
  MQTT (`/uplink`), newest first.
- **Topology** — latest known parent/battery/RSSI per CH derived from
  CH_HELLO / CH_CONFIG_REQUEST / CH_CONFIG_RESPONSE events (`/topology`),
  plus the raw event feed.
- **Commands** — compose and publish a pull request
  (`MSG_SERVER_PULL_REQUEST` via `cmd/pull`) or a node command
  (`MSG_SERVER_NODE_COMMAND` via `cmd/node`), with a log of what was sent.
- **Boot Log** — read-only COM port tail for firmware boot/debug output.
- **Firmware** — schema-v2 manifest-verified `esptool` flash over USB
  (same verification path as `ch-operator`/`gld-operator`), locked behind
  a local PIN.

## MQTT topic reference

| Topic | Direction | Payload |
|---|---|---|
| `{topicRoot}/uplink` | gateway → broker | mesh frame + parse result |
| `{topicRoot}/status` | gateway → broker | health snapshot, every `STATUS_INTERVAL_MS` |
| `{topicRoot}/topology` | gateway → broker | CH_HELLO / CH_CONFIG_* events |
| `{topicRoot}/cmd/pull` | broker → gateway | `{"hopList":[...]}` or `{"cluster":"0064"}` |
| `{topicRoot}/cmd/node` | broker → gateway | `{"cluster","node","id","ttl","hex","hopList"}` |

`topicRoot` defaults to `gld/gateway` (`PGL_SERVER_SITE_TOPIC_ROOT` in
`firmware/config/ServerConfig.h`).
