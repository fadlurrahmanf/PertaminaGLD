# GLD2 - schematic block diagram

Open `index.html` to view the nine diagram pages with page selection and zoom, or open `../../pdf/GLD2-Block-Diagram.pdf` for the vector PDF. Former pages 10-17 have been removed. The external 5 V input and its paths are omitted at the user's request; original design files are unchanged.
The SVG files can be edited with Inkscape, Illustrator, or a text editor. Drawing helpers are in `build_diagram.py`, page content in `allocation_pages.py`, and calculations in `allocation_budget.py` and `power_budget.py`.

## Source and scope

- One motherboard sheet (Sheet_1), all 204 component/symbol records, and PCB pad nets from the user-provided ZIP.
- The sensor-module reference image was read separately; its component designators do not match the motherboard.
- `source-net-evidence.json` stores symbol pin names, PCB pad nets, schematic pin coordinates, and traced net labels. No differences were found for pins with a net label. This is not a complete electrical-rules check or PCB-routing validation.
- `component-pins.csv` lists every component pin, including passive components. Case-only rows have no electrical pins.
- The eight configured MQ types come from firmware/gld/include/BoardPinsGLD2.h. Fitted manufacturers are not established: heater calculations explicitly use reference manufacturer datasheets.
- The motherboard +5VA source is absent from the original ZIP. A later user-supplied filter image (5VA.png) supplies the +5V-to-+5VA connection shown here. Module and motherboard analog rails remain distinct.
- Reference-module pins differ from the motherboard header. Module pages show functional connections and load allocation, not a wiring instruction without orientation verification.
- No firmware, build, upload, COM, or hardware measurements were changed.

## Calculations

Brown power connections use calculated voltage/current labels for the 24 V reference scenario. Page 09 allocates load power back to the 24 V source and separates conversion losses. CALCULATION-NOTES.md and allocation-calculations.json retain formulas, source links, assumptions and exclusions outside the PDF. Reference estimates are not measured consumption or guaranteed hardware maxima. Alarm-on demand is excluded until its exact model is identified.

## Regeneration

Run with Python and reportlab from the repository root: `python output/diagrams/gld2/build_diagram.py`. The font is Windows Arial.
The generator outputs the PDF, nine SVG files, HTML, CSV, and README. Its primary input is the extracted `source-net-evidence.json`.

Source ZIP SHA-256: `aeb3d54180c596c5ee7fbc9adbb51e434651a238b19a31429d8cf5c82ec985f1`
