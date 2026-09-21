# GLD2 - schematic block diagram

Open `index.html` to view the nine diagrams with page selection and zoom, or open `../../pdf/GLD2-Block-Diagram.pdf` for the vector PDF.
The SVG files can be edited with Inkscape, Illustrator, or a text editor. The layout and source content are in `build_diagram.py`.

## Source and scope

- One motherboard sheet (Sheet_1), all 204 component/symbol records, and PCB pad nets from the user-provided ZIP.
- The sensor-module reference image was read separately; its component designators do not match the motherboard.
- `source-net-evidence.json` stores symbol pin names, PCB pad nets, schematic pin coordinates, and traced net labels. No differences were found for pins with a net label. This is not a complete electrical-rules check or PCB-routing validation.
- `component-pins.csv` lists every component pin, including passive components. Case-only rows have no electrical pins.
- Sensor identity per channel is not inferred from firmware. MQ2 is only an example written on the module image.
- The motherboard +5VA source is not visible; local sensor-module +5VA has an L1 filter from +5V. They are not combined without evidence.
- Reference-module pins differ from the motherboard header. Page 06 presents functional mapping, not a wiring instruction without orientation verification.
- No firmware, build, upload, COM, or hardware measurements were changed.

## Regeneration

Run with Python and reportlab from the repository root: `python output/diagrams/gld2/build_diagram.py`. The font is Windows Arial.
The generator outputs the PDF, nine SVG files, HTML, CSV, and README. Its primary input is the extracted `source-net-evidence.json`.

SHA-256 arsip sumber: `aeb3d54180c596c5ee7fbc9adbb51e434651a238b19a31429d8cf5c82ec985f1`
