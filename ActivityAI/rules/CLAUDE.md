# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pertamina GLD is an IoT gas-leak detection system with three ESP32-S3 firmware targets, a Gateway, and a Node-RED server backend.

Data flow: **GLD** (sensor node) → [STAR LoRa] → **CH** (Cluster Head) → [MESH LoRa] → **Gateway** → [MQTT/LAN] → **Node-RED**

GLD payload is 4-byte plaintext (`gasClass`, `confidence`, `batteryMv`) encrypted with **AES-128-GCM** into a fixed **29-byte** encrypted payload. CH treats this payload as opaque bytes and never decrypts it.

Current firmware versions: GLD `v0.8.0`, CH `v0.7.0`, Gateway `v0.1.3`.

## Read Before Implementing

1. `docs/README.md` — document reading order
2. `docs/design/gld-ch/payload-contract.draft.md` — wire protocol contract (source of truth)
3. `docs/design/gld/design.updated.draft.md` and `docs/design/ch/design.updated.draft.md` — per-component design (updated drafts override original designs)
4. `docs/progress.md` — current milestone and live bench proof

**Never edit** `docs/design/gld/design.md` or `docs/design/ch/design.md` — these are immutable imports. Create `design.<topic>.draft.md` copies for edits.

Also read `ActivityAI/rules/AI_WORKFLOW_RULES.md` for Codex/Claude parallel workflow, ownership, save, and merge rules.

## Build & Upload (PlatformIO)

All commands run from the repo root. **Build one env at a time on Windows** — parallel builds in the same `firmware/.pio/build` directory collide.

```powershell
# Build only
pio run -d firmware -e <env_name>

# Build and upload (direct — no compile-only step needed first)
pio run -d firmware -e <env_name> -t upload --upload-port <COMx>

# Serial monitor
pio device monitor -p <COMx> -b 115200 --raw
```

### PlatformIO Environments

| Environment | Target | Board COM |
|---|---|---|
| `gld` | GLD unified final runtime | COM10 |
| `gldw` | GLD WROOM bench runtime | COM9 |
| `ch1` | CH1 - ID 0x0064 | COM39 |
| `ch2` | CH2 - ID 0x0065 | COM38 |
| `ch3` | CH3 - ID 0x0066, GLD parent in current bench | COM5 |
| `gw` | Gateway MESH+MQTT bridge (ID 0x006F) | COM3 |

`ch1` is the base/default CH env. For multi-hop topology use `ch1`, `ch2`, and `ch3`; active parent routing is discovered automatically through CH_CONFIG and is not flashed as a static parent.

Support/debug GLD per-mode envs live in `firmware/support/platformio.ini`.
Bench-only self-test envs live in `firmware/bench/platformio.ini`.

## Firmware Configuration

All editable parameters live in `firmware/config/`. Each file owns one domain:

| File | Domain |
|---|---|
| `LoraStarConfig.h` | GLD↔CH STAR LoRa radio params (`pgl::config::lora::star::`) |
| `LoraMeshConfig.h` | CH↔Gateway MESH LoRa radio params (`pgl::config::lora::mesh::`) |
| `ServerConfig.h` | WiFi SSID/pass, MQTT broker, dataset topic root |
| `GldConfig.h` | GLD node ID (`GLD_NODE_HEX`), target CH, timing, MQTT buffer |
| `ChConfig.h` | CH identity, root gateway, timing |
| `GwConfig.h` | Gateway identity, retry/status timing |

**Pattern**: editable `#define`/`constexpr` at top; derived aliases below. Only edit the top section.

`firmware/gld/include/GldUnifiedConfig.h` is now a **compatibility wrapper** that `#include`s `GldConfig.h`. Do not add new editable parameters there — add them in `firmware/config/` instead.

To change GLD node ID: edit only `GLD_NODE_HEX` in `GldConfig.h` (single source → all derived names/topics update automatically).

## Host-Level Protocol Tests

```powershell
python firmware/tests/run_tests.py
```

Expected: `26/27 tests passed`. One pre-existing fail: `test_gld_retry_snapshot_and_provisioning_scaffolds_present` (requires `GldRetryState.h` + `GldProvisioning.h` — future work, not a regression). Run after every protocol/shared layer change.

## Node-RED Flow Deploy

```powershell
.\server\nodered\apply-pertamina-gld-flow.ps1 `
  -NodeRedUrl "http://127.0.0.1:1880" `
  -MqttHost "127.0.0.1" `
  -MqttPort 1884
```

Aedes MQTT broker runs on port `1884` because port `1883` is occupied by the Mosquitto service on the bench laptop.

## Architecture

### Firmware Structure

```
firmware/
  shared/     # AppFrame, GldCrypto (AES-GCM), GldPayload, GldRecord, FirmwareConfig
  gld/        # GLD sensor reads, power modes, LoRa TX, frame builder, nulling DAC
  ch/         # NodeCache (opaque), AlarmQueue, ChTxQueue, ChRuntime, ClusterResponse
  gateway/    # GatewayMqttMeshMain — MESH radio + WiFi + MQTT bridge
  lib/        # Vendored ADS1256-main (sensor ADC) and ArduinoJson
  tests/      # Python host-level protocol contract tests
  versions/   # version.md + per-version diff backups for rollback
```

### Wire Protocol Summary

- All multi-byte integers on the wire are **big-endian**.
- `AppFrame` is the outer transport for both STAR (GLD→CH) and MESH (CH→Gateway).
  - `typeFlags`: `msgType` (bits 0–5) | `FLAG_ALARM_ACK` (bit 6) | `FLAG_GLD_EXT_POWER` (bit 7)
- Encrypted payload layout (29 bytes): `keyId(1) | nonce(12) | ciphertext(4) | tag(12)`
- `GLDRecord` wire: `nodeId(2) | seq(1) | flags(1) | payloadLen(1) | payload(N)` — 34 bytes for phase 1
- Normal pull response: `CLUSTER_DATA_RESPONSE (0x31)` — max 2 `GLDRecord`s per MESH frame
- Alarm push: `SENSOR_DATA (0x10) | FLAG_ALARM_ACK` — exactly one `GLDRecord`

### Alarm Rule

```c
alarm = (gasClass != 0) && (confidence >= GLD_LEL_THRESHOLD_PERCENT);
// GLD_LEL_THRESHOLD_PERCENT = 30 (default)
```

### CH State Machine (v0.7.0+)

CH firmware runs an 8-state machine: `ST_BOOT → ST_WAIT_BATT → ST_RADIO_INIT → ST_JOINING → ST_JOINED → ST_LOW_POWER → ST_PARENT_FAILOVER → ST_RECOVERY`. Key behaviors:
- Battery guard: GPIO4 ADC, 16-sample avg, formula `(avg×3)+200 mV`. Below 3150 mV → `ST_LOW_POWER`.
- Alarm ACK: alarm is NOT removed from queue on TX success — only on `FLAG_ALARM_ACK` received from parent (`markAlarmAcked()`).
- Parent failover: after 3 consecutive ACK failures, swap primary↔backup parent, save to NVS via `Preferences`.
- Housekeeping runs every 60 s: evicts NodeCache entries older than 1 h, drops pending downlinks older than 30 min.

### CH Non-Blocking Receive

CH uses `setPacketReceivedAction()` callbacks on both Radio A (STAR) and Radio B (MESH). Both radios are armed with `startReceive()` at boot — do not revert to blocking alternating receive.

### Feature Channel Remapping

`GldUnifiedMain.cpp` applies `HW_TO_MODEL[8] = {0,2,5,3,4,6,1,7}` before normalization. This maps hardware ADS1256 channel index to model input index. The design (`docs/design/gld/design.md` sec 8.6) states "no remap", but the current placeholder model was trained with this mapping — do not remove it until the real trained model is validated against the actual feature order.

### Key Provisioning

Phase 1 uses a single global AES-128 key (`keyId=1`). Copy `config/gld-crypto.env.example` to a local `.env` and fill in the real key. The `.env` file must not be committed.

### GLD Node ID Ranges

| Range | Use |
|---|---|
| `0x0001..0xEFFF` | Production GLD |
| `0xF000..0xFEFF` | Test/manual GLD (e.g., `0xF001` in self-tests) |
| `0xFF00..0xFFFF` | System/reserved |

## Manuals

`docs/manual/` contains generated PDF technical manuals:

| File | Isi |
|---|---|
| `gld-operation-manual.pdf` | GLD sensor node operation |
| `server-pull-request-flow.pdf` | End-to-end Server Pull Request flow (Gateway→CH1→CH2→response) |

Generator scripts live in `C:\Users\asus\AppData\Local\Temp\` (not committed). If PDF needs regenerating, ask Claude to re-run the generator.

## Versioning & Rollback

When a firmware version is released, only the changed files are backed up to `firmware/versions/backups/<version>/`. To roll back, restore those files from the backup folder. See `firmware/versions/version.md` for the full history and rollback instructions per version.

New version entries go in `firmware/versions/version.md` and must update `firmware/shared/include/FirmwareVersion.h`.

## AGENTS.md Rules (Summary)

- **Auto-compact:** When context window usage reaches >= 50%, run `/compact` immediately before continuing. Do not wait until near the limit. Compact proactively after any large output (long file reads, build logs, serial monitor dumps, multi-file diffs).
- If visible usage/context remaining is below 10%, save checkpoint first by updating `docs/chat/fullchat.md`, `docs/chat/summary.md`, and `docs/resume.md` before continuing long-running work.
- **Ask first** for non-trivial design, protocol, pin, or API decisions.
- Use Indonesian when the user writes in Indonesian.
- Only update `docs/chat/fullchat.md` and `docs/chat/summary.md` when the user explicitly says `save`.
- For large or risky tasks, ask 10–25 clarifying questions before implementing.
- **Activity log:** Before non-trivial work, read `ActivityAI/codexactivity.md` to check for Codex conflicts. Before changing files/state, using hardware/COM ports, deploying, touching databases, or running long work, write `PLANNED` or `ACTIVE` in `ActivityAI/claudeactivity.md` with exact scope/files/resources. After work completes or blocks, append/update `DONE` or `BLOCKED` in `ActivityAI/claudeactivity.md`. See `ActivityAI/claudeactivity.md` for format and ownership table.
