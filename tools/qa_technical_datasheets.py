from __future__ import annotations

import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pdfplumber
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "output" / "pdf"

LANGUAGES = ("ID", "EN")
PAGE_RANGES = {
    "GasleakDetector": (10, 18),
    "CH": (9, 16),
    "Gateway": (8, 15),
    "Server": (8, 14),
    "Whole-System": (9, 16),
}

A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890
A4_TOLERANCE_PT = 0.9
MIN_OUTLINE_DESTINATIONS = 8
MIN_TOC_LINKS = 6

# Each tuple is (human-readable requirement, acceptable visible alternatives).
# Technical names are intentionally retained across both languages so parity does
# not depend on translating a product or protocol name.
REQUIRED_TERMS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "GasleakDetector": (
        ("product name", ("GasleakDetector",)),
        ("main input", ("24 VDC",)),
        ("operating band", ("920-923 MHz", "920 - 923 MHz")),
        ("local interface", ("Modbus RTU",)),
        ("analog converter", ("ADS1256",)),
        ("sensor manufacturer", ("Winsen",)),
        ("measured current", ("300 mA",)),
        ("alarm mode", ("AUTO",)),
        ("local physical layer", ("RS-485",)),
    ),
    "CH": (
        ("product name", ("CH",)),
        ("board variants", ("Rectangle",)),
        ("board variants", ("Circle",)),
        ("STAR radio", ("STAR",)),
        ("MESH radio", ("MESH",)),
        ("STAR antenna", ("3 dBi",)),
        ("MESH antenna", ("8 dBi",)),
        ("solar-panel rating", ("6 W",)),
        ("battery monitoring", ("VBAT",)),
        ("route recovery", ("failover",)),
    ),
    "Gateway": (
        ("product name", ("Gateway",)),
        ("board variants", ("Rectangle",)),
        ("board variants", ("Circle",)),
        ("IP interface", ("Wi-Fi STA",)),
        ("messaging protocol", ("MQTT",)),
        ("secure transport", ("TLS",)),
        ("trust anchor", ("Root CA", "CA root")),
        ("trusted time", ("NTP",)),
        ("queue capacity", ("8-item", "8 item", "8-item queue", "8 messages", "8 pesan", "8 publikasi")),
        ("queue persistence", ("volatile", "volatil")),
    ),
    "Server": (
        ("product name", ("Server",)),
        ("flow runtime", ("Node-RED",)),
        ("payload security", ("AES-128-GCM",)),
        ("replay protection", ("replay",)),
        ("database", ("MySQL",)),
        ("dataset fallback", ("CSV",)),
        ("deployment model", ("VM",)),
        ("messaging protocol", ("MQTT",)),
        ("engineering records", ("dataset",)),
    ),
    "Whole-System": (
        ("endpoint", ("GasleakDetector",)),
        ("field concentrator", ("CH",)),
        ("IP bridge", ("Gateway",)),
        ("application", ("Server",)),
        ("STAR radio", ("STAR",)),
        ("MESH radio", ("MESH",)),
        ("messaging protocol", ("MQTT",)),
        ("secure transport", ("TLS",)),
        ("payload security", ("AES-128-GCM",)),
        ("normal uplink", ("normal pull",)),
        ("alarm uplink", ("alarm push",)),
        ("messaging dependency", ("broker",)),
    ),
}

MONTHS = (
    "Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|"
    "Oktober|November|Desember|January|February|March|April|May|June|"
    "July|August|September|October|November|December"
)

BANNED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Indonesian word 'kanal'", re.compile(r"\bkanal\b", re.IGNORECASE)),
    ("removed gas claim", re.compile(r"\bfreon\b", re.IGNORECASE)),
    ("internal product generation", re.compile(r"\bGLD2\b|\bgld_v2\b", re.IGNORECASE)),
    ("placeholder", re.compile(r"\b(?:TBD|TBC|TO\s*DO)\b", re.IGNORECASE)),
    (
        "language/audience metadata",
        re.compile(r"(?im)^\s*(?:Bahasa|Language|Pembaca|Audience)\b"),
    ),
    (
        "publication-date metadata",
        re.compile(
            r"(?im)^\s*(?:Tanggal\s+terbit|Issue\s+date|Publication\s+date|"
            r"Release\s+date|Revisi\s*/\s*tanggal|Revision\s*/\s*date)\b"
        ),
    ),
    (
        "ISO calendar date",
        re.compile(r"\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b"),
    ),
    (
        "numeric calendar date",
        re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b"),
    ),
    (
        "named calendar date",
        re.compile(rf"\b(?:\d{{1,2}}\s+)?(?:{MONTHS})\s+(?:19|20)\d{{2}}\b", re.IGNORECASE),
    ),
    (
        "removed disclaimer",
        re.compile(
            r"Dokumen\s+engineering\s+ini\s+memisahkan|"
            r"This\s+engineering\s+document\s+separates|"
            r"Tidak\s+ada\s+klaim\s+performa\s+atau\s+sertifikasi\s+tanpa\s+bukti\s+produk|"
            r"No\s+performance\s+or\s+certification\s+claim\s+without\s+product\s+evidence",
            re.IGNORECASE,
        ),
    ),
    (
        "evidence-basis label",
        re.compile(r"\b(?:Basis\s+bukti|Evidence\s+basis|Kelas\s+bukti|Evidence\s+class)\b", re.IGNORECASE),
    ),
    (
        "owner-confirmation audit wording",
        re.compile(
            r"\bowner[- ]confirmed\b|\bdikonfirmasi\s+(?:oleh\s+)?pemilik\b|"
            r"\bkonfirmasi\s+pemilik\b",
            re.IGNORECASE,
        ),
    ),
    (
        "evidence badge",
        re.compile(
            r"(?im)^\s*(?:TERIMPLEMENTASI|IMPLEMENTED|TEST\s+CONFIRMED|"
            r"UJI\s+DIKONFIRMASI|SOURCE[- ]VERIFIED|BUILD[- ]VERIFIED|"
            r"OWNER\s+CONFIRMED|DIKONFIRMASI\s+PEMILIK)\s*$"
        ),
    ),
    (
        "internal validation commentary",
        re.compile(
            r"source\s*/\s*build\s*/\s*package|live\s+belum\s+divalidasi|"
            r"not\s+(?:yet\s+)?live[- ]validated|live\s+customer\s+broker\s+has\s+not\s+been\s+validated",
            re.IGNORECASE,
        ),
    ),
    (
        "internal firmware environment",
        re.compile(
            r"\b(?:ch_small|ch_large|gw_small(?:_tls)?|gw_large(?:_tls)?|"
            r"chFieldtest|dualRadioCH_E220Ver\d+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "local absolute path",
        re.compile(r"(?:\b[A-Z]:[\\/]|\b(?:D:/Github|C:/Users)/)", re.IGNORECASE),
    ),
    (
        "local repository path",
        re.compile(
            r"\b(?:firmware|tools|docs|operator_hub|ActivityAI|server[\\/]nodered)[\\/]"
            r"(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+",
            re.IGNORECASE,
        ),
    ),
    (
        "internal source filename",
        re.compile(
            r"\b(?:platformio\.ini|[A-Za-z0-9_.-]+\.(?:c|h|cpp|hpp|ino|py|zip))\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class PageMetrics:
    characters: int
    words: int
    main_characters: int
    main_words: int
    main_vertical_span: float


@dataclass(frozen=True)
class PdfMetrics:
    page_count: int
    outline_count: int
    outline_numbers: tuple[str, ...]
    toc_links: int
    body_word_count: int


def expected_paths() -> dict[Path, tuple[str, str, tuple[int, int]]]:
    result: dict[Path, tuple[str, str, tuple[int, int]]] = {}
    for product, page_range in PAGE_RANGES.items():
        for lang in LANGUAGES:
            path = PDF_DIR / f"Technical-Datasheet-{product}-{lang}.pdf"
            result[path] = (product, lang, page_range)
    return result


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_search(text: str) -> str:
    text = text.replace("\u2010", "-").replace("\u2011", "-")
    text = text.replace("\u2012", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    return normalize(text).casefold()


def dereference(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def outline_titles(items: Iterable[object]) -> list[str]:
    titles: list[str] = []
    for item in items:
        if isinstance(item, list):
            titles.extend(outline_titles(item))
            continue
        title = getattr(item, "title", None)
        titles.append(str(title if title is not None else item))
    return titles


def outline_number_sequence(titles: Iterable[str]) -> tuple[str, ...]:
    numbers: list[str] = []
    for title in titles:
        match = re.match(r"^\s*(\d+(?:\.\d+)*)\b", title)
        if match:
            numbers.append(match.group(1))
    return tuple(numbers)


def link_annotation_count(page: Any) -> int:
    annotations = page.get("/Annots")
    if annotations is None:
        return 0
    annotations = dereference(annotations)
    count = 0
    for annotation in annotations:
        obj = dereference(annotation)
        if obj.get("/Subtype") == "/Link":
            count += 1
    return count


def identify_content_start(page_texts: list[str], lang: str) -> int | None:
    marker = "Identifikasi produk" if lang == "ID" else "Product identification"
    status_marker = "Status produk" if lang == "ID" else "Product status"
    marker = marker.casefold()
    status_marker = status_marker.casefold()
    for index, text in enumerate(page_texts[2:], start=2):
        lowered = text.casefold()
        if marker in lowered and status_marker in lowered:
            return index
    return None


def object_vertical_extent(obj: dict[str, Any], page_height: float) -> tuple[float, float] | None:
    top = obj.get("top")
    bottom = obj.get("bottom")
    if top is None or bottom is None:
        return None
    top_f = float(top)
    bottom_f = float(bottom)
    if top_f < 40.0 or bottom_f > page_height - 40.0:
        return None
    return top_f, bottom_f


def measure_page(page: pdfplumber.page.Page) -> PageMetrics:
    raw_text = page.extract_text() or ""
    words = page.extract_words() or []
    height = float(page.height)
    width = float(page.width)

    main_words = [
        word
        for word in words
        if float(word.get("top", 0.0)) >= 40.0
        and float(word.get("bottom", height)) <= height - 40.0
    ]
    main_text = " ".join(str(word.get("text", "")) for word in main_words)

    extents: list[tuple[float, float]] = []
    for word in main_words:
        extents.append((float(word["top"]), float(word["bottom"])))

    # Tables and line diagrams count toward vertical use. The full-page white
    # background rectangle and the fixed header/footer rules are excluded.
    for obj in [*page.lines, *page.rects, *page.curves]:
        obj_width = abs(float(obj.get("x1", 0.0)) - float(obj.get("x0", 0.0)))
        obj_height = abs(float(obj.get("y1", 0.0)) - float(obj.get("y0", 0.0)))
        if obj_width > width * 0.90 and obj_height > height * 0.90:
            continue
        extent = object_vertical_extent(obj, height)
        if extent is not None:
            extents.append(extent)

    available_height = height - 80.0
    if extents and available_height > 0:
        vertical_span = (max(bottom for _, bottom in extents) - min(top for top, _ in extents)) / available_height
        vertical_span = max(0.0, min(vertical_span, 1.0))
    else:
        vertical_span = 0.0

    return PageMetrics(
        characters=len(normalize(raw_text)),
        words=len(words),
        main_characters=len(normalize(main_text)),
        main_words=len(main_words),
        main_vertical_span=vertical_span,
    )


def has_required_term(search_text: str, alternatives: tuple[str, ...]) -> bool:
    return any(normalize_for_search(term) in search_text for term in alternatives)


def check_pdf(
    path: Path,
    product: str,
    lang: str,
    page_range: tuple[int, int],
) -> tuple[list[str], PdfMetrics | None]:
    errors: list[str] = []
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pragma: no cover - defensive report for damaged artifacts
        return [f"cannot be opened by pypdf: {exc}"], None

    page_count = len(reader.pages)
    minimum_pages, maximum_pages = page_range
    if not minimum_pages <= page_count <= maximum_pages:
        errors.append(
            f"page count {page_count} is outside permitted range "
            f"{minimum_pages}-{maximum_pages}"
        )

    expected_title = f"Technical Datasheet - {product.replace('-', ' ')} - {lang}"
    actual_title = (reader.metadata.title or "").strip() if reader.metadata else ""
    if actual_title != expected_title:
        errors.append(f"metadata title {actual_title!r} != {expected_title!r}")

    titles = outline_titles(reader.outline)
    outline_count = len(titles)
    if outline_count < MIN_OUTLINE_DESTINATIONS:
        errors.append(
            f"outline has {outline_count} destinations; expected at least "
            f"{MIN_OUTLINE_DESTINATIONS}"
        )
    outline_numbers = outline_number_sequence(titles)
    if len(outline_numbers) < MIN_OUTLINE_DESTINATIONS - 1:
        errors.append(
            f"outline has only {len(outline_numbers)} numbered section destinations"
        )

    page_texts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if (
            abs(width - A4_WIDTH_PT) > A4_TOLERANCE_PT
            or abs(height - A4_HEIGHT_PT) > A4_TOLERANCE_PT
        ):
            errors.append(
                f"page {page_number}: media box {width:.2f} x {height:.2f} pt is not portrait A4"
            )
        raw_text = page.extract_text() or ""
        page_texts.append(raw_text)
        if page_number > 1 and f"{page_number} / {page_count}" not in normalize(raw_text):
            errors.append(f"page {page_number}: missing footer '{page_number} / {page_count}'")

    if page_count < 2:
        errors.append("document has no contents page")
        content_start = None
        toc_links = 0
        toc_page_indices: set[int] = set()
    else:
        toc_heading = "Daftar isi" if lang == "ID" else "Contents"
        if toc_heading.casefold() not in page_texts[1].casefold():
            errors.append(f"page 2 does not contain the expected {toc_heading!r} heading")
        content_start = identify_content_start(page_texts, lang)
        if content_start is None or content_start < 2:
            errors.append("cannot identify the first numbered product-content page after the TOC")
            toc_page_indices = {1}
        else:
            toc_page_indices = set(range(1, content_start))
        toc_links = sum(link_annotation_count(reader.pages[index]) for index in toc_page_indices)
        expected_link_floor = max(MIN_TOC_LINKS, outline_count - 2)
        if toc_links < expected_link_floor:
            errors.append(
                f"TOC has {toc_links} link annotations; expected at least {expected_link_floor} "
                f"for {outline_count} outline destinations"
            )

    try:
        with pdfplumber.open(path) as plumber_pdf:
            page_metrics = [measure_page(page) for page in plumber_pdf.pages]
    except Exception as exc:  # pragma: no cover - defensive report for damaged artifacts
        errors.append(f"cannot be measured by pdfplumber: {exc}")
        page_metrics = []

    body_indices: list[int] = []
    if page_metrics:
        final_index = page_count - 1
        exceptions = {0, final_index, *toc_page_indices}
        body_indices = [index for index in range(page_count) if index not in exceptions]

        for index, metrics in enumerate(page_metrics):
            page_number = index + 1
            if metrics.characters < 45 or metrics.words < 7:
                errors.append(
                    f"page {page_number}: blank or nearly blank "
                    f"({metrics.words} words, {metrics.characters} characters)"
                )
            if index not in body_indices:
                continue
            if metrics.main_words < 90:
                errors.append(
                    f"page {page_number}: body has only {metrics.main_words} main-area words; minimum is 90"
                )
            if metrics.main_characters < 500:
                errors.append(
                    f"page {page_number}: body has only {metrics.main_characters} main-area characters; "
                    "minimum is 500"
                )
            if metrics.main_vertical_span < 0.52:
                errors.append(
                    f"page {page_number}: main-content vertical span is "
                    f"{metrics.main_vertical_span:.0%}; minimum is 52%"
                )

        final_metrics = page_metrics[-1]
        if final_metrics.main_words < 100:
            errors.append(
                f"final page has only {final_metrics.main_words} main-area words; minimum is 100"
            )
        if final_metrics.main_characters < 700:
            errors.append(
                f"final page has only {final_metrics.main_characters} main-area characters; minimum is 700"
            )
        if final_metrics.main_vertical_span < 0.42:
            errors.append(
                f"final-page main-content vertical span is {final_metrics.main_vertical_span:.0%}; "
                "minimum is 42%"
            )

        if not body_indices:
            errors.append("document has no body pages after cover/TOC exceptions")
        else:
            body_words = [page_metrics[index].main_words for index in body_indices]
            median_words = statistics.median(body_words)
            if median_words < 140:
                errors.append(
                    f"median body density is {median_words:.0f} words/page; minimum is 140"
                )
            dense_pages = sum(words >= 110 for words in body_words)
            required_dense_pages = max(1, int(len(body_words) * 0.75 + 0.999))
            if dense_pages < required_dense_pages:
                errors.append(
                    f"only {dense_pages}/{len(body_words)} body pages have at least 110 words; "
                    f"expected {required_dense_pages}"
                )
            median_span = statistics.median(
                page_metrics[index].main_vertical_span for index in body_indices
            )
            if median_span < 0.68:
                errors.append(
                    f"median main-content vertical span is {median_span:.0%}; minimum is 68%"
                )

    for page_number, raw_text in enumerate(page_texts, start=1):
        for label, pattern in BANNED_PATTERNS:
            match = pattern.search(raw_text)
            if match:
                errors.append(
                    f"page {page_number}: contains banned {label}: {normalize(match.group(0))!r}"
                )

    full_text = "\n".join(page_texts)
    search_text = normalize_for_search(full_text)
    for label, alternatives in REQUIRED_TERMS[product]:
        if not has_required_term(search_text, alternatives):
            rendered_alternatives = " / ".join(repr(term) for term in alternatives)
            errors.append(f"missing required {label}: {rendered_alternatives}")

    body_word_count = sum(page_metrics[index].main_words for index in body_indices) if page_metrics else 0
    metrics = PdfMetrics(
        page_count=page_count,
        outline_count=outline_count,
        outline_numbers=outline_numbers,
        toc_links=toc_links,
        body_word_count=body_word_count,
    )
    return errors, metrics


def parity_errors(product: str, id_metrics: PdfMetrics, en_metrics: PdfMetrics) -> list[str]:
    errors: list[str] = []
    prefix = f"{product} ID/EN parity"
    if id_metrics.page_count != en_metrics.page_count:
        errors.append(
            f"{prefix}: page counts differ "
            f"({id_metrics.page_count} ID vs {en_metrics.page_count} EN)"
        )
    if id_metrics.outline_count != en_metrics.outline_count:
        errors.append(
            f"{prefix}: outline counts differ "
            f"({id_metrics.outline_count} ID vs {en_metrics.outline_count} EN)"
        )
    if id_metrics.outline_numbers != en_metrics.outline_numbers:
        errors.append(f"{prefix}: numbered outline structure is not identical")
    if abs(id_metrics.toc_links - en_metrics.toc_links) > 1:
        errors.append(
            f"{prefix}: TOC link counts differ "
            f"({id_metrics.toc_links} ID vs {en_metrics.toc_links} EN)"
        )
    if id_metrics.body_word_count and en_metrics.body_word_count:
        word_ratio = id_metrics.body_word_count / en_metrics.body_word_count
        if not 0.65 <= word_ratio <= 1.55:
            errors.append(
                f"{prefix}: body word-count ratio is {word_ratio:.2f} "
                f"({id_metrics.body_word_count} ID vs {en_metrics.body_word_count} EN)"
            )
    return errors


def main() -> int:
    expected = expected_paths()
    actual = set(PDF_DIR.glob("Technical-Datasheet-*.pdf")) if PDF_DIR.exists() else set()
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    failures: list[str] = []
    per_file_errors: dict[Path, list[str]] = {}
    results: dict[tuple[str, str], PdfMetrics] = {}

    if len(actual) != 10:
        failures.append(f"expected exactly 10 technical-datasheet PDFs, found {len(actual)}")
    failures.extend(f"MISSING: {path.name}" for path in missing)
    failures.extend(f"UNEXPECTED: {path.name}" for path in extra)

    checked_pages = 0
    for path, (product, lang, page_range) in expected.items():
        if not path.exists():
            continue
        errors, metrics = check_pdf(path, product, lang, page_range)
        per_file_errors[path] = errors
        failures.extend(f"{path.name}: {error}" for error in errors)
        if metrics is not None:
            results[(product, lang)] = metrics
            checked_pages += metrics.page_count

    for product in PAGE_RANGES:
        id_metrics = results.get((product, "ID"))
        en_metrics = results.get((product, "EN"))
        if id_metrics is not None and en_metrics is not None:
            failures.extend(parity_errors(product, id_metrics, en_metrics))

    for path in expected:
        metrics = results.get((expected[path][0], expected[path][1]))
        if path.exists() and not per_file_errors.get(path) and metrics is not None:
            print(
                f"PASS  {path.name:<52} {metrics.page_count:>2} pages  "
                f"{metrics.outline_count:>2} outline entries"
            )

    if failures:
        print("\nQA FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        f"\nQA PASSED: 10 bilingual official-style datasheets, {checked_pages} A4 pages, "
        "with structure, content, density, and parity gates satisfied."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
