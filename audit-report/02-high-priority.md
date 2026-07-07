# 02 — High-priority issues

Continues from `01-critical-bugs.md` (C1). Two high-severity findings.

---

## H1 — Multi-hop alarm ACK chain is broken: any CH at mesh depth ≥ 2 never receives an alarm ACK

**Severity:** High — alarms still reach the server, but every alarm from a
depth-2+ CH is retransmitted 5×, and repeated alarms drive the CH into
`PARENT_FAILOVER` and eventually a full `RECOVERY` restart, destabilizing the
mesh exactly when a gas alarm is active.

### What breaks

When a CH pushes a GLD alarm upstream (`ChTxKind::AlarmPush`), it arms an ACK
timer and expects a frame with `FLAG_ALARM_ACK` back **from its parent**:

- Waiter: `firmware/ch/src/ChStarMeshRuntimeMain.cpp:1166` — ACK accepted only if
  `decoded.srcId == parentId && decoded.dstId == CH_ID`.
- Timeout/retry/giveup: `ChStarMeshRuntimeMain.cpp:865-898` — after
  `ALARM_RETRY_MAX` (5) retries it gives up, and each failed round increments
  `parentFailCnt` and `noAckBurst`; `checkFailover()` (`:847`) then triggers
  `PARENT_FAILOVER` at 3 and a full `ESP.restart()` via `RECOVERY` at 5.

Only the **gateway** ever generates that ACK
(`firmware/gateway/src/GatewayMqttMeshMain.cpp:803`, `sendGatewayAckIfNeeded`),
and it addresses it to `decoded.srcId` — the immediate sender it heard.

An intermediate CH that receives a child CH's alarm frame takes the
"uplink relay to parent" branch (`ChStarMeshRuntimeMain.cpp:1240-1251`): it
re-encodes the frame with `srcId = CH_ID` (its own ID) and enqueues it as
`ChTxKind::RelayFrame`. Two consequences:

1. The intermediate CH **never sends an ACK downstream** to the child — no code
   path does.
2. When the gateway finally hears the relayed alarm, its ACK goes to the
   *relaying* CH (`dstId = relayer`), which discards it because it has no
   `alarmAck.active` for a relay (`onAlarmAckFromParent`, `:837`, returns when
   `!alarmAck.active`). The ACK is never forwarded down to the originating CH.

So for topology `GLD → CH-B (depth 2) → CH-A (depth 1) → Gateway`: CH-B's alarm
is delivered (via CH-A) but CH-B times out, retries 5×, gives up, and its
fail counters climb. Three alarms → parent failover (possibly to a worse
parent); five → watchdog-style restart, dropping the NodeCache and any pending
downlinks (`handleRadioInit` clears all queues, `:1319-1323`).

### Trigger

Any GLD alarm while the serving CH's parent is another CH rather than the
gateway. The firmware actively supports this topology (depth tracking, parent
candidates with `depth + 1`, `allowedAsRuntimeParent` upstream-depth checks), and
`ChConfig.h` tunes multi-hop behavior, so this is a supported configuration, not
a theoretical one. Bench setups where every CH hears the gateway directly
(depth 1) never hit it — which is presumably why it has not been observed.

### Root cause

The hop-by-hop ACK contract is only implemented at the gateway edge. The relay
path (`enqueueRelayFrame`) treats alarm frames as opaque relays: it neither
emits a local ACK to the downstream sender nor keeps state to forward the
gateway's ACK back down.

### Exact fix (hop-by-hop ACK — smallest correct change)

In `handleMeshPacketReceived`, in the uplink-relay branch
(`ChStarMeshRuntimeMain.cpp:1240`), after successfully enqueueing a relayed
`MSG_SENSOR_DATA` frame that carries `FLAG_ALARM_ACK`, send a compact alarm ACK
back to the child on the MESH radio:

```cpp
if (queued && msgType == pgl::protocol::MSG_SENSOR_DATA &&
    pgl::protocol::hasAlarmAckFlag(decoded.typeFlags)) {
    uint8_t ack[pgl::protocol::APPFRAME_OVERHEAD]{};
    size_t ackSize = 0;
    if (pgl::ch::buildCompactAlarmAck(CH_ID, decoded.srcId, decoded.seq,
                                      ack, sizeof(ack), ackSize) ==
        pgl::ch::ChUplinkStatus::Ok) {
        transmitRadio(meshRadio, MESH_PINS, ack, ackSize, "MESH_CHILD_ACK");
    }
}
```

This makes the ACK hop-by-hop: the child is ACKed as soon as the relay is
accepted into the parent's TX queue, mirroring what the gateway already does at
the top hop. `buildCompactAlarmAck` (`firmware/ch/src/ChUplink.cpp:52`) already
produces the right frame; the child's existing check
(`srcId == parentId && dstId == CH_ID && FLAG_ALARM_ACK`) accepts it unchanged.
End-to-end delivery of the relayed frame remains protected by the relayer's own
retry once it is an `AlarmPush`… note the relay is a `RelayFrame`, which is
fire-and-forget — if you want end-to-end guarantees instead, enqueue relayed
alarms as `AlarmPush` (so the relayer also waits for its parent's ACK) rather
than adding the downstream ACK. Pick one; hop-by-hop is the lighter change and
matches the existing gateway behavior.

Add a regression case to `firmware/tests/test_shared_protocol.py` modeling a
depth-2 chain: child alarm → relay → assert child receives an ACK.

---

## H2 — A dead classifier silently reports "clear air, 100% confidence" over LoRa

**Severity:** High — a GLD whose ML stack failed to initialize (or whose sensors
never prime) keeps transmitting healthy-looking "no gas" uplinks indefinitely,
masking a non-functional detector at the server.

### What breaks

`lastResult` is initialized to `{GLD_GAS_CLEAR, 100}` at
`firmware/gld/src/GldUnifiedMain.cpp:121` and is only ever overwritten by a
successful `network->predict()` inside `runInference()`
(`GldUnifiedMain.cpp:1489-1507`). Every failure mode short-circuits before that:

- `mlReady == false` (TFLite arena/alloc/schema failure in
  `firmware/gld/model/NeuralNetwork.cpp:24-74`) → `runInference` returns at
  `:1490`.
- ADS never primes (`primedChannels < SENSOR_COUNT`, `:1523`) → inference skipped.
- `predict()` returns `< 0` (interpreter invoke error) → early return at `:1500`.

Meanwhile `transmitOnce()` (`:1564`) unconditionally encrypts and transmits
`lastResult` every `TX_INTERVAL_MS` as long as the radio is up and an AES key is
provisioned. The uplink is indistinguishable from a genuinely healthy node
reporting clear air at maximum confidence — the strongest possible "all clear"
signal, produced by a device that cannot actually classify anything. `runScan()`
(`:1509-1533`) also derives the local alarm outputs from the same stale value,
so lamp/buzzer stay off too.

The boot report does print `mlReady=0` and `MODE_READY=NOT_OK` on serial
(`:1767-1791`), but nothing in the radio payload or server pipeline carries that
health state; the 4-byte plaintext (`gasClass, confidence, batteryMv`) has no
room for it and no reserved value is used.

### Trigger

Any ML init failure (model/schema mismatch after a model update, arena
exhaustion — the arena is a fixed 40 KB at `NeuralNetwork.cpp:10`), any
persistent ADS1256 fault after boot, or an interpreter invoke error at runtime.
All are realistic after a firmware/model update or a hardware fault in the field.

### Root cause

`lastResult`'s initial value doubles as a valid protocol payload. There is no
"unknown / sensor-fault" representation on the wire, and `transmitOnce()` does
not gate on `mlReady`/primed state.

### Exact fix

The protocol already reserves a class for this: `GLD_GAS_ANOMALY = 6`
(`firmware/shared/include/ProtocolConstants.h:41`) and the decoder maps class 6
to `"anomaly"` (`server/nodered/functions/pertamina-gld-decode.js:8`). Use it
with confidence 0 as the "not classifying" sentinel:

1. `GldUnifiedMain.cpp:121` — initialize
   `lastResult{pgl::protocol::GLD_GAS_ANOMALY, 0}` instead of `{GLD_GAS_CLEAR, 100}`.
2. In `runScan()` (`:1509`), when `!primed || !mlReady`, set
   `lastResult = {GLD_GAS_ANOMALY, 0}` rather than leaving the previous value —
   this also stops a *stale* last classification from being re-sent forever after
   a mid-life sensor failure.
3. Keep alarm logic as-is: `isGldAlarm` requires `confidence >= threshold`, so
   `{ANOMALY, 0}` raises no alarm locally, and the server can distinguish
   "healthy clear" from "cannot classify" and raise a maintenance alert.
4. Server side, add a rule in the decoded-event consumer flagging
   `gasClass == 6 && confidence == 0` as device-health rather than gas data
   (one condition in `pertamina-gld-decode.js`'s `recordToEvent`, or downstream).

Note `isValidGasClass` already accepts 6, and `GldFrameBuilder`'s
`isValidInput` passes it, so no protocol change is needed.
