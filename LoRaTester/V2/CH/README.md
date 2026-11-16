# LoRaTester V2 CH — bench prototype

Separate PlatformIO project. `lt_ch1` and `lt_ch2` do not compile or replace
the original CH runtime. They are intended for the V3 rectangle-board pin map.
Do not use them as production CH firmware: they do not run mesh or alarm.

Build from this folder with `pio run -e lt_ch1 -e lt_ch2`. Building does not
upload. Preserve the known-good original CH package and NVS before any bench
flash. Hardware, packet delivery, antenna selection and recovery have not yet
been verified for this prototype.

LoRa radio B runs at 922 MHz, BW 125 kHz,
SF9, CR 4/5, sync 0x34 and 10 dBm. Although the application format differs,
the RF channel overlaps the existing mesh and can interfere with it. Use an
isolated, authorized test environment with correct antennas and attenuation.
The tester now uses the production AppFrame codec and CRC with a test-only
message type and synthetic payload, not production sensor/alarm semantics.
CH1 to CH2 frames are 39 bytes (GLD-sized), CH2 to CH1 50 bytes (one-record
CH-to-Gateway-sized). Different sizes affect airtime and loss comparisons.
An unknown type is not an isolation mechanism: a production gateway may
publish raw packets. Use an RF-isolated bench without live production nodes.

V2 sends a CH1 LoRa health poll automatically every 15–17 seconds while idle,
with a delayed CH2 reply. It does not inject these polls during a running or
starting test. CH2 also broadcasts a separate ESP-NOW health heartbeat every
2 seconds; that path needs its own 2.4 GHz antenna but failure to initialize
Wi-Fi does not prevent the LoRa test. Health ages and source paths are
independent; the random node nonce is not authentication.

After an idle poll, CH1 can delay a requested START for up to four seconds to
leave time for the reply. If STOP is requested during that wait, the queued
START is cancelled. After Timeout or Error, idle polling and any new START wait
14 seconds for the remote watchdog; these are timing mitigations, not proof that collisions
cannot occur on real radios. Physical testing remains necessary.

After CH1 boots, LoRa START and idle polls wait 24 seconds while ESP-NOW
discovery and status remain available. This allows an old CH2 session to
expire: CH2 limits the starting phase to 20 seconds and stops retrying final
reports after 12 seconds without a valid END. The actual timing requires bench
verification; the delays alone do not prove the remote device stopped.
During final exchange CH1 times out after 16 seconds without a report.
Reports processed eight seconds or more after their receive interrupt are
rejected instead of acknowledged. This margin reduces late acknowledgements;
it does not prove the remote is still listening under real RF conditions.
Direct CH2 health uses a per-boot `reportSeq`, incremented for every send
attempt and wrapping as uint32; receivers should reject duplicate/older
reports within a MAC and boot nonce, without treating it as authentication.

Battery voltage and percentage are **unknown by default**. The V3 schematic
shows a 200 kΩ / 100 kΩ BATMON divider (nominal ×3), but ADC gain/offset and
the battery's chemistry and state-of-charge curve have not been validated on
the actual board. Do not enable battery validity merely because an ADC pin
returns a number. First measure battery voltage with a multimeter at several
levels, check the battery connection and ADC saturation, and establish the
appropriate single-cell voltage range and an offset. A missing battery or
floating BATMON input may still require separate hardware detection.

Only after that verification, an intentionally configured build can add all
of these flags to the relevant `build_flags` (replace each placeholder with
measured, board-specific integer millivolts):

```
-DLT_BATTERY_CALIBRATED=1
-DLT_BATTERY_EMPTY_MV=<measured-empty-mV>
-DLT_BATTERY_FULL_MV=<measured-full-mV>
-DLT_BATTERY_OFFSET_MV=<measured-offset-mV>
```

The implementation uses ADC mV ×3 plus that explicit offset, rejects zero or
out-of-range samples, and derives a **linear voltage estimate**, not a fuel
gauge. Charging, load, temperature and cell chemistry can make the percentage
inaccurate. Samples are spread over 16 loop iterations and refreshed about
every 10 seconds. Health age measures the health report, not the exact age of
the most recent battery conversion.

CH1 uses ESP-NOW station channel 1. The monitor's periodic DISCOVER packet
binds its MAC in RAM and receives a PRESENCE heartbeat, without starting a
LoRa test. An idle binding expires after 10 seconds without discovery; the
peer cannot change during an active test. Binding is lost at reset and can be
re-established by discovery. START and STOP use `NowMessage` in
`include/LoRaTesterWire.h`; STATUS is sent unicast to the bound monitor.
When the same monitor discovers CH1 again, the current or last session STATUS
is sent immediately. A different monitor cannot adopt the old session. A CH1
restart erases the in-RAM session and results; only idle PRESENCE is sent.
`INFO` on the same UART prints radio/Wi-Fi initialization, pairing state,
channel, and receive/send counters without transmitting an RF test. A zero
`status_result` means the ESP-NOW send was queued, not that it was received.
`LT_NOW_TX` reports queued/rejected sends separately from MAC-layer ack/no_ack
callbacks and includes the bound peer and boot nonce; an ACK does not prove
that the monitor application accepted the message.
This prototype uses unencrypted radio and MAC/session filtering, which is not
cryptographic authentication; it must not be treated as secure against spoofing.

The monitor sends START with a fresh nonzero session. START, COMMIT, ACK and
GO establish one session. The two half-duplex radios then alternate 1-second
slots, with 100 scheduled data packets per direction (about 200 seconds).
CH1 starts its own slots at the agreed epoch even if initial CH2 packets are
lost; sustained silence still ends the session through the watchdog.
Each CH2 data packet carries its latest CH2 receive snapshot. Lost return
packets can delay that snapshot and the observed CH2 progress. Both directions
use unique received packets for RSSI and SNR. The V2 v8 96-byte ESP-NOW status
includes latest RSSI and 0.1 dB SNR per direction, progress and snapshot ages; latest
values require at least one received packet and 0xffff age denotes unknown. Phase 4
is the concurrent test and phase 3 is final-report exchange. The final report
is repeated until acknowledged. A skipped or failed local send makes the
overall outcome an error; loss cannot then be attributed solely to the link.
Timing, handshake loss and RF behavior remain unverified on physical devices.
Before transmitting, the tester enters standby and checks the latched RX_DONE
flag so completed receptions can be handled first. A packet still in flight
when the half-duplex radio leaves RX can still be lost. Standby/IRQ read
errors stop the tester with Error; hardware timing needs bench validation.

Realtime mode uses ESP-NOW START type 6 and phase 5. Both radios continue
alternating until STOP or timeout; the 8-bit LoRa sequence wraps modulo 256.
In this mode directional received=0/1 means latest-sample validity only,
expected=0 and sent counts=0xffff; no PDR or aggregate is implied. The normal
START type 1 remains the separate 100-packet-per-direction PDR test. Monitor
and both CH test firmwares must support the realtime extension.

STOP enters Stopping until CH2 returns a matching STOP acknowledgement. If
confirmation is lost, timeout means the remote state is unknown, not stopped.
During the data phase, either side stops with Timeout after 12 seconds without
a new valid unique packet from its peer (about six missed peer slots). Before
the first packet the interval starts at the agreed epoch; duplicates do not
extend it. This intentionally aborts very lossy tests and is not a final PDR.
An error can indicate a local transmit failure on CH2. A session timeout does
not by itself determine which of the command, data, or end report was lost.
Statistics in this prototype are not a certified RF measurement.

`tests/test_session.cpp` exercises unique counting, statistics, rounding,
saturation and wire layout on a host C++ compiler. It does not simulate the
ESP-NOW/radio state machine or replace an end-to-end test with both devices
and the monitor.
