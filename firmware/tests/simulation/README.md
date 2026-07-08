# Full-system simulation (host-side, no physical hardware)

This directory simulates the Pertamina GLD system end-to-end on a host
machine, for use in environments (like this one) with no physical ESP32
boards, LoRa radios, or sensors attached. It is a supplement to, not a
replacement for, `firmware/tests/test_shared_protocol.py` (the existing
Python protocol mirror) and `firmware/tools/validate_c1_scaler_order.py` (the
C1-specific ML validation).

## What actually runs here

This is not a from-scratch reimplementation. It compiles and executes the
**real, unmodified firmware source**, and the **real, unmodified server-side
JavaScript**, wherever that's possible off-target:

| Component | What runs | How |
|---|---|---|
| GLD uplink encode | **Real** `buildGldUplinkFrame`, `encryptGldPayload` (AES-128-GCM) | Compiled from `firmware/shared/src/*.cpp` + `firmware/gld/src/GldFrameBuilder.cpp`, linked against **real mbedtls** (`-DESP_PLATFORM=1` forces the firmware's real crypto path instead of its host no-op stub) |
| AppFrame encode/decode | **Real** `encodeAppFrame`/`decodeAppFrame`, CRC-16 | Same compile |
| CH cache/queues/cluster logic | **Real** `processGldStarFrame`, `NodeCache`, `AlarmQueue`, `ChTxQueue`, `ClusterResponse`, `ChPullRequest` | Same compile |
| CH-to-CH multi-hop relay + H1 fix | Mirrored orchestration, **real** `encodeAppFrame`/`hasAlarmAckFlag`/`markAlarmAcked` calls | See caveat below - the orchestrating file itself is Arduino-bound |
| Authenticated downlink signing | **Real** `computeAesCmac128` (C++/mbedtls) **and** the real JS `aesCmac` from `apply-pertamina-gld-flow.js`, cross-checked byte-for-byte | `host_protocol_sim` + `run_server_cmac.js` |
| Server-side decrypt/decode | **Real, unmodified** `server/nodered/functions/pertamina-gld-decode.js` | `run_decode_js.js`, via Node's `vm` module with a minimal Node-RED function-node shim (`msg`/`flow`/`global`/`env`) |
| ML classification | **Real, trained** TFLite model extracted from `firmware/gld/model/model_data.cpp` | `run_full_system_simulation.py`, reusing the approach from `validate_c1_scaler_order.py` (optional - degrades gracefully if `tflite-runtime` isn't installed) |

## What is NOT run — read this before trusting any result

- **No RF/PHY layer.** No actual LoRa modulation, airtime, collisions, link
  budget, or RSSI/SNR behavior. Frames are handed directly from one
  simulated node's memory to the next.
- **No Arduino main-loop, GPIO, ADC, or timing.** `ChStarMeshRuntimeMain.cpp`,
  `GatewayMqttMeshMain.cpp`, `GldUnifiedMain.cpp`, and `GldCommandParser.cpp`
  all depend on `<Arduino.h>` (and, for the mains, `RadioLib`/`WiFi`/
  `PubSubClient`/`Preferences`) and cannot be linked on a host. The specific
  orchestration sequences they contain (the CH-A relay + hop-by-hop-ACK
  branch, the GLD command-parsing wrapper) are reproduced by hand in
  `host_protocol_sim.cpp`, calling into the same real, compiled primitive
  functions - but the *sequencing* of those calls is mirrored, not compiled
  from the original file. `firmware/tests/test_shared_protocol.py` already
  carries an equivalent Python mirror of the same H1 sequencing, for
  cross-reference.
- **No MQTT broker, no real network.** The "gateway MQTT publish" and
  "Node-RED subscribe" steps are collapsed into directly calling
  `run_decode_js.js` with the wire frame that would have been the MQTT
  payload.
- **No real training-pipeline confirmation for the ML leg.** As documented in
  `audit-report/01-critical-bugs.md` and `validate_c1_scaler_order.py`, the C1
  fix's directionality (physical channel order vs. some other order) still
  hasn't been confirmed against the actual training pipeline. This
  simulation exercises the model as fixed; it does not re-litigate that
  open question.

## Running it

```sh
# Optional, for the real-ML-model leg (falls back to a fixed input without it):
pip install tflite-runtime "numpy<2"   # in a virtualenv - see note below

python3 firmware/tests/simulation/run_full_system_simulation.py
```

Requires `g++` and `libmbedtls-dev` (or equivalent) to build
`host_protocol_sim`, and `node` for the two JS legs. If `tflite-runtime` is
installed under a `numpy>=2` environment, import will typically fail with
`_ARRAY_API not found` - install `tflite-runtime` and `numpy<2` together in a
dedicated virtualenv to avoid this (matches the note in
`validate_c1_scaler_order.py`).

You can also run `host_protocol_sim` directly with an explicit GLD1
classification, bypassing the ML leg:

```sh
./firmware/tests/simulation/build/host_protocol_sim <gasClass> <confidence> <batteryMv>
```

## What a clean run demonstrates

With the real, compiled crypto and framing code, a real trained model, and
the real production JS decoder, a single simulated pipeline run has shown:

- GLD1 raises a genuine alarm (ML-classified or fixed input), AES-GCM
  encrypts it, and frames it for CH-B.
- CH-B caches it, ACKs GLD1 over STAR, and queues it for its parent, CH-A.
- CH-A relays it toward the gateway **and** ACKs CH-B directly - the H1 fix -
  clearing CH-B's alarm queue via the real `markAlarmAcked`, with no timeout
  or retry.
- The gateway-bound frame, fed into the real, unmodified
  `pertamina-gld-decode.js`, decrypts to the *exact* gas class, confidence,
  and battery voltage GLD1 started with.
- A second GLD's normal reading is cached, retrieved via a real
  `handleServerPullRequestFrame` pull/cluster-response cycle, relayed to the
  gateway, and decoded correctly by the same real JS function.
- An authenticated `SET_MODE` downlink, signed with the real
  `computeAesCmac128`, is accepted by the (mirrored) firmware-side verifier -
  and rejected the instant one tag byte is tampered with.
- The real C++ (mbedtls) and real JS AES-CMAC implementations produce an
  identical tag for the same key and message.

This is a strong, multi-layer cross-check that the protocol, crypto, and CH
mesh logic are internally consistent end-to-end. It is not a substitute for
on-hardware validation, RF testing, or the still-open C1 training-pipeline
question.
