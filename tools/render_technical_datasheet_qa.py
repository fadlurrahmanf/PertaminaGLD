from __future__ import annotations

import shutil
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "output" / "pdf"
QA_DIR = ROOT / "tmp" / "pdfs" / "technical-datasheets-official"
PAGE_DIR = QA_DIR / "pages"
CONTACT_DIR = QA_DIR / "contacts"

SCALE = 1.55
THUMB_W = 340
COLS = 3
ROWS = 4
MARGIN = 18
LABEL_H = 26


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / filename), size=size)


def render_pdf(path: Path) -> tuple[list[Path], tuple[int, int]]:
    document = pdfium.PdfDocument(str(path))
    target_dir = PAGE_DIR / path.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    page_size = (0, 0)
    for index in range(len(document)):
        page = document[index]
        bitmap = page.render(scale=SCALE, rotation=0)
        image = bitmap.to_pil().convert("RGB")
        page_size = image.size
        output = target_dir / f"page-{index + 1:03d}.png"
        image.save(output, format="PNG", optimize=True)
        rendered.append(output)
        page.close()
    document.close()
    return rendered, page_size


def make_contacts(pdf_path: Path, pages: list[Path]) -> list[Path]:
    CONTACT_DIR.mkdir(parents=True, exist_ok=True)
    first = Image.open(pages[0])
    ratio = first.height / first.width
    first.close()
    thumb_h = round(THUMB_W * ratio)
    sheet_w = MARGIN + COLS * (THUMB_W + MARGIN)
    sheet_h = 52 + ROWS * (thumb_h + LABEL_H + MARGIN)
    per_sheet = COLS * ROWS
    results: list[Path] = []

    for sheet_index, start in enumerate(range(0, len(pages), per_sheet), start=1):
        sheet = Image.new("RGB", (sheet_w, sheet_h), "#DDE6EC")
        draw = ImageDraw.Draw(sheet)
        draw.rectangle((0, 0, sheet_w, 45), fill="#071B2D")
        draw.text((MARGIN, 12), f"{pdf_path.name} | sheet {sheet_index}", fill="white", font=font(18, bold=True))

        for local_index, page_path in enumerate(pages[start : start + per_sheet]):
            row, col = divmod(local_index, COLS)
            x = MARGIN + col * (THUMB_W + MARGIN)
            y = 52 + row * (thumb_h + LABEL_H + MARGIN)
            with Image.open(page_path) as image:
                thumb = image.convert("RGB").resize((THUMB_W, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x, y))
            page_no = start + local_index + 1
            draw.rectangle((x, y + thumb_h, x + THUMB_W, y + thumb_h + LABEL_H), fill="#FFFFFF")
            draw.text((x + 7, y + thumb_h + 5), f"Page {page_no}/{len(pages)}", fill="#14283A", font=font(14, bold=True))

        output = CONTACT_DIR / f"{pdf_path.stem}-sheet-{sheet_index:02d}.png"
        sheet.save(output, format="PNG", optimize=True)
        results.append(output)
    return results


def main() -> int:
    pdfs = sorted(PDF_DIR.glob("Technical-Datasheet-*.pdf"))
    if len(pdfs) != 10:
        raise RuntimeError(f"Expected 10 PDFs, found {len(pdfs)}")

    # A shorter rebuild must not inherit page PNGs or contact sheets from a
    # previous, longer PDF.  Constrain cleanup to this exact QA directory.
    resolved_qa = QA_DIR.resolve()
    resolved_parent = (ROOT / "tmp" / "pdfs").resolve()
    if resolved_qa.parent != resolved_parent or resolved_qa.name != "technical-datasheets-official":
        raise RuntimeError(f"Refusing to clear unexpected QA path: {resolved_qa}")
    if resolved_qa.exists():
        shutil.rmtree(resolved_qa)

    total_pages = 0
    total_contacts = 0
    for pdf_path in pdfs:
        pages, size = render_pdf(pdf_path)
        contacts = make_contacts(pdf_path, pages)
        total_pages += len(pages)
        total_contacts += len(contacts)
        print(f"RENDERED  {pdf_path.name:<52} {len(pages):>2} pages @ {size[0]}x{size[1]} | {len(contacts)} contact sheets")

    print(f"\nRENDER COMPLETE: {len(pdfs)} PDFs, {total_pages} page PNGs, {total_contacts} contact sheets")
    print(QA_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
