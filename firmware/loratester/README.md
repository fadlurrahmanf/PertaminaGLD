# LoRaTester CH V3 — bench prototype

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
This prototype uses unencrypted radio and MAC/session filtering, which is not
cryptographic authentication; it must not be treated as secure against spoofing.

The monitor sends START with a fresh nonzero session. START, COMMIT, ACK and
GO establish one session. The two half-duplex radios then alternate 1-second
slots, with 100 scheduled data packets per direction (about 200 seconds).
Each CH2 data packet carries its latest CH2 receive snapshot. Lost return
packets can delay that snapshot and the observed CH2 progress. Both directions
use unique received packets for RSSI and SNR. The v4 53-byte ESP-NOW status
includes separate progress and snapshot ages; 0xffff denotes unknown. Phase 4
is the concurrent test and phase 3 is final-report exchange. The final report
is repeated until acknowledged. A skipped or failed local send makes the
overall outcome an error; loss cannot then be attributed solely to the link.
Timing, handshake loss and RF behavior remain unverified on physical devices.

STOP enters Stopping until CH2 returns a matching STOP acknowledgement. If
confirmation is lost, timeout means the remote state is unknown, not stopped.
An error can indicate a local transmit failure on CH2. A session timeout does
not by itself determine which of the command, data, or end report was lost.
Statistics in this prototype are not a certified RF measurement.

`tests/test_session.cpp` exercises unique counting, statistics, rounding,
saturation and wire layout on a host C++ compiler. It does not simulate the
ESP-NOW/radio state machine or replace an end-to-end test with both devices
and the monitor.
