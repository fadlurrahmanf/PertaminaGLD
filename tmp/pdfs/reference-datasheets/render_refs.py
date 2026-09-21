from pathlib import Path

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parent
SELECTIONS = {
    "esp32-s3-wroom.pdf": [1, 2, 5, 8, 13, 18, 27, 42, 53],
    "ads1256.pdf": [1, 2, 4, 5, 10, 22, 32, 40],
}

for filename, page_numbers in SELECTIONS.items():
    source = ROOT / filename
    document = pdfium.PdfDocument(str(source))
    output_dir = ROOT / source.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    for page_number in page_numbers:
        if page_number > len(document):
            continue
        page = document[page_number - 1]
        image = page.render(scale=1.6).to_pil().convert("RGB")
        image.save(output_dir / f"page-{page_number:03d}.png", format="PNG", optimize=True)
        page.close()
    print(f"{source.name}: {len(document)} pages")
    document.close()
