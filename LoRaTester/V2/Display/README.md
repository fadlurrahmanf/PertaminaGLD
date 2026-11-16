# Display V2

V2 uses its own v8 wire format and does not communicate with V1. A normal
`platformio run` only builds and does not flash a device.

The monitor battery reading is **disabled by default** and displays `--`.
The proposed wiring is a 100 kΩ / 100 kΩ divider from the switched 03962A
OUT+ / MT3608 IN+ battery node to ADC1 GPIO34 and GND. A 100 nF capacitor
between GPIO34 and GND is optional. Verify the wiring, ADC input voltage,
divider ratio and calibration on the actual board before enabling
`LT_DISPLAY_BATTERY_ENABLED=1` in the build. Never connect the battery
directly to GPIO34. The enabled reading assumes a nominal 2:1 divider and
maps 3.3–4.2 V linearly to 0–100%; it is a rough loaded-voltage estimate,
not a calibrated state-of-charge measurement.

For example only, after verifying the hardware, the V2 Display environment
can use `build_flags = -DLT_DISPLAY_BATTERY_ENABLED=1
-DLT_DISPLAY_BATTERY_DIVIDER_MILLI=2000 -DLT_DISPLAY_BATTERY_OFFSET_MV=0`.
Do not use those example values as measured calibration. With USB and
battery supplies arranged safely, `BATTERY` on the serial console reports
the ADC millivolts and calculated battery millivolts; it does not change
hardware. Compare both readings with a multimeter and set
`LT_DISPLAY_BATTERY_DIVIDER_MILLI` to `(actual battery mV / reported ADC mV)
* 1000`, rounded, with offset 0. Verify again at more than one voltage; a
single-point ratio cannot correct ADC nonlinearity. An optional offset in mV
is available for a separately measured calibration. Do not enable on an
unwired or unverified input.

The menu shows the monitor's voltage and estimated percentage; the CH1/CH2
battery icons show voltage and percentage together when their health fields
are valid. Unknown or invalid measurements show `--` for both.

CH batteries appear only with valid, calibrated health fields. CH2 direct
heartbeat is pinned separately from CH1 and can work when CH1 is off. Direct
and relayed CH2 data with conflicting boot nonces are reported as a conflict;
identity is not cryptographically authenticated. Health is unknown when
data is missing or older than 30 seconds. Duplicate or older CH2 direct
heartbeats do not extend its freshness; sequence wrap is handled per boot.

To look for a replacement CH2 direct peer, wait until the old direct report
is older than 30 seconds, then leave and re-enter a test mode. Rebinding only
occurs when CH1 is online and reports idle or a terminal state, with no
active/pending session, unconfirmed STOP or recovery delay. If CH1 is
offline or the test state is uncertain, the old binding is retained. CH1's
binding and relayed health are not cleared. If a new direct peer disagrees
with still-fresh relayed CH2 identity, `CONFLICT` remains until the evidence
agrees or becomes stale. This first-valid-MAC selection is not authentication.

Hold progress uses a partial TFT update; timing and smoothness must be
measured on hardware. The physical PDR/realtime path and visual appearance
remain unverified until a bench test is explicitly performed.

The renderer compares 16×16 tiles of an 8-bit sprite and sends only changed
tiles; it falls back to a full-screen write if the extra buffer cannot be
allocated or most tiles change. The display still scans independently, and
a full RGB565 frame at 10 MHz has a theoretical data-only minimum of about
92 ms. The 16 ms render request is not a measured 60 FPS guarantee.

Serial `FPS` returns the previous measured window (`window_us`), attempted
sprite render rate (`render_milli`, in 0.001 FPS), actual transfers of at
least one changed tile (`blit_milli`), number of full-frame transfers,
transferred pixel count and worst frame/blit/loop times in microseconds.
Separate `hold_updates` and `max_hold_us` measure direct progress-strip writes.
Zero-pixel renders are not counted as screen transfers. Measure while the
actual desired animation is moving and include scene transitions, not just
an idle screen. These are task/transfer measurements, not LCD scan rate.

`SPIHZ 10000000`, `SPIHZ 20000000` and `SPIHZ 40000000` try those display
SPI frequencies without changing the active pins, SPI mode or color settings.
The default remains 10 MHz after restart. Higher speeds are unverified on the
actual wiring: check the entire screen for corruption and restore 10 MHz if
needed. Switching reinitializes the panel and forces a full redraw.
