import json
import sys
from pypdf import PdfReader

pdf_path = r"D:\Github\PertaminaGLD\output\pdf\Presentasi-Rapat-Cilacap-Terkonfirmasi-2026-08-19.pdf"
reader = PdfReader(pdf_path)
text = "\n".join(page.extract_text() or "" for page in reader.pages)
text_lower = text.lower()

banned = [
    "gld1",
    "gld2",
    "easyeda",
    "summary recorder",
    "ch.zip",
    "20260814",
    "provisional",
    "tbd",
    "belum diketahui",
    "0,4–0,8",
    "safety hold",
    "flow drift",
    "mqtt plaintext",
]
required = [
    "24 vdc/2 a",
    "liitokala 4000 mah",
    "3 minggu",
    "kunjungan",
    "area sru",
    "3 unit gld",
    "agenda keamanan jaringan",
]

root = reader.trailer.get("/Root", {})
names = root.get("/Names", {}) if hasattr(root, "get") else {}
has_javascript = bool(names and hasattr(names, "get") and names.get("/JavaScript"))

result = {
    "pages": len(reader.pages),
    "encrypted": reader.is_encrypted,
    "javascript": has_javascript,
    "missing_required": [item for item in required if item not in text_lower],
    "found_banned": [item for item in banned if item in text_lower],
    "text_characters": len(text),
}
print(json.dumps(result, ensure_ascii=False, indent=2))

if (
    result["pages"] != 16
    or result["encrypted"]
    or result["javascript"]
    or result["missing_required"]
    or result["found_banned"]
):
    sys.exit(1)
