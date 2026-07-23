# Operator Hub guide — generator

Builds `docs/manual/operator-hub-guide.pptx` (60 slides, 16:9) and its PDF
export: a step-by-step operator guide for `apps/operator-hub` covering the GLD,
CH, and Gateway consoles, in Bahasa Indonesia.

Every screenshot carries numbered callout boxes drawn over the exact control
the slide is talking about, and each slide repeats those numbers as a legend.

## Files

| File | Purpose |
|---|---|
| `capture_shots.py` | Drives Chrome via Playwright, opens every screen/tab/drawer, draws the callouts, writes `screenshots/*.png` |
| `annotate.js` | Injected into each page: draws the boxes, and computes the crop region so a dialog or drawer fills the shot instead of the dimmed page behind it |
| `deck.py` | Slide layout primitives (cover, section divider, screenshot slide, text slide) |
| `build_guide.py` | The slide-by-slide content; run this to produce the PPTX |
| `screenshots/` | Generated, annotated PNGs |

## Regenerating

1. Start the consoles so the pages are reachable:

   ```text
   apps\operator-hub\run-operator-hub.bat
   ```

   Hub 5173, GLD 5174, CH 5273, Gateway 5373.

2. Capture the screenshots (needs `playwright` and a local Chrome; no
   `playwright install` required — it launches the installed browser via
   `channel="chrome"`):

   ```text
   python capture_shots.py           # all shots
   python capture_shots.py gld- ch-  # only ids starting with these prefixes
   ```

3. Build the deck (needs `python-pptx` and `Pillow`):

   ```text
   python build_guide.py
   ```

4. Export the PDF with PowerPoint:

   ```powershell
   $pp = New-Object -ComObject PowerPoint.Application
   $pres = $pp.Presentations.Open("...\operator-hub-guide.pptx", $true, $false, $false)
   $pres.SaveAs("...\operator-hub-guide.pdf", 32)
   $pres.Close(); $pp.Quit()
   ```

## About the data on screen

No hardware is attached during capture, so each console is primed to make its
panels representative:

- **GLD** uses the app's own simulator (`js/mock.js`), which is why the header
  badge reads `mock`.
- **CH** is fed `CH_*` serial lines in the exact format the firmware prints.
- **Gateway** is fed a status payload plus mesh/topology uplinks in the same
  shape the firmware publishes to MQTT.

The two "upload berjalan" / "upload selesai" slides set the dialog's status
line to the strings the app writes in those states; they are illustrations of
the UI, not records of an actual flashing run. The deck says so on its own
"Tentang tangkapan layar" slide.
