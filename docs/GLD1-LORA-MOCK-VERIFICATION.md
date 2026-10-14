# GLD1 LoRa QC Matrix — Mock Verification

Run date: 2026-10-14 WIB  
Scope: `GLD1` only, using the local Operator Console mock. No COM port, RF radio, CH, gateway, upload, reset, or physical device was used.

## What this proves

- The Operator LoRa QC control flow sends a complete configuration and then runs `BEGIN_LORA`.
- The mock schedules actual TX events based on the active interval, with sequence numbers and millisecond deltas.
- The user-visible mode matrix, validation, Auto Begin debounce, and injected gate/radio faults behave as specified in the mock contract.

It does **not** prove on-air RF transmission, CH reception, AES authentication, gateway receipt, or hardware timing. In particular, Focus + Ke CH uses a structurally valid dummy AppFrame envelope with the real CH address, but is intentionally not AES-authenticated; a real CH may recognize its envelope and reject its payload.

## Parameter propagation

Manual LoRa Begin received and made active this complete non-default form:

```text
[22:02:56.609] LORA BEGIN SUCCESS | Manual
921.5 MHz | BW 250 kHz | SF 8 | CR 6 | 17 dBm | Interval 3 s |
Focus OFF | Target Transmit saja | Payload frame test
```

This exercises Frequency, Bandwidth, Spreading Factor, Coding Rate, TX Power, TX Interval, Focus, and Target as one configuration transaction.

## Scheduled TX proof

| Focus | Target | Active payload | Minimum interval | Observed TX proof |
|---|---|---|---:|---|
| OFF | Ke CH | CH normal | 3 s | #1 21:53:34.953; #2 21:53:37.953 (3.000 s); #3 21:53:40.952 (3.000 s); #4 21:53:43.952 (3.000 s); RX window flagged. |
| OFF | Transmit saja | frame test | 3 s | #1 21:54:28.670; #2 21:54:31.670 (3.000 s); #3 21:54:34.670 (3.000 s); #4 21:54:37.670 (3.000 s); RX off. |
| ON | Ke CH | CH dummy | 1 s | Gates deliberately unavailable; #1 21:54:58.399; #2 21:54:59.424 (1.025 s); #3 21:55:00.448 (1.024 s); #4 21:55:01.448 (1.000 s); #5 21:55:02.448 (1.000 s); #6 21:55:03.448 (1.000 s). Log states `CH ID 0064`, `frame 39 B`, `RX off`. |
| ON | Transmit saja | frame test | 1 s | #1 21:55:28.565; #2 21:55:29.565 (1.000 s); #3 21:55:30.566 (1.001 s); #4 21:55:31.565 (0.999 s); #5 21:55:32.590 (1.025 s); #6 21:55:33.590 (1.000 s); RX off. |

## Validation and debounce proof

```text
[21:57:03.925] KONFIGURASI DITOLAK
Interval di bawah 3 detik hanya saat Transmit Focus ON.
```

Auto Begin was enabled, a parameter stopped changing, and it began once after two seconds:

```text
[21:57:19.789] LORA BEGIN SUCCESS | Auto Begin
920 MHz | BW 125 kHz | SF 7 | CR 5 | 21 dBm | Interval 3 s |
Focus OFF | Target Ke CH | Payload CH normal
```

For cancellation, an initial edit was followed by a second edit one second later. Before the second edit's two-second quiet period elapsed there was no Auto Begin; then exactly one Begin occurred for the final value:

```text
[21:57:38.722] LORA BEGIN SUCCESS | Auto Begin
920 MHz | BW 125 kHz | SF 7 | CR 5 | 19 dBm | Interval 3 s |
Focus OFF | Target Ke CH | Payload CH normal
```

## Radio-fault proof

With an injected post-Begin `SX1262/SPI/radio tidak siap` fault, the first scheduled TX failed in every matrix combination:

| Focus | Target | Result |
|---|---|---|
| OFF | Ke CH | `TX #0001 GAGAL — SX1262/SPI/radio tidak siap` at 21:58:01.087 |
| OFF | Transmit saja | `TX #0001 GAGAL — SX1262/SPI/radio tidak siap` at 21:58:02.019 |
| ON | Ke CH | `TX #0001 GAGAL — SX1262/SPI/radio tidak siap` at 21:58:03.471 |
| ON | Transmit saja | `TX #0001 GAGAL — SX1262/SPI/radio tidak siap` at 21:58:04.605 |

## Build and package

- `pio run -e gld_model_1` passed after the GLD1-only guards were added: RAM 41.5%, flash 15.8%.
- Operator Hub package `apps/operator-hub/firmware-packages/gld_model_1/latest` was refreshed.
- Manifest firmware SHA-256 equals the packaged `firmware.bin` SHA-256: `16418ae4154a4305675e35a15b9ac2b2e4fa5a2de44572766d8d5bd0408bae86`.
- No GLD2 or GLD3 paths appear in the working diff.
