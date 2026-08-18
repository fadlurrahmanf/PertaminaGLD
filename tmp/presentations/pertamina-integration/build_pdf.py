from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

src = Path(r"D:\Github\PertaminaGLD\tmp\presentations\pertamina-integration\rendered")
out = Path(r"D:\Github\PertaminaGLD\output\pdf\PertaminaGLD-Pertanyaan-Integrasi.pdf")
out.parent.mkdir(parents=True, exist_ok=True)
images = sorted(src.glob("slide-*.png"))
if len(images) != 11:
    raise RuntimeError(f"Expected 11 slide images, found {len(images)}")

c = canvas.Canvas(str(out), pagesize=(1280, 720), pageCompression=1)
c.setTitle("Kesiapan Integrasi GLD - CH - Gateway - Server")
c.setAuthor("LGU")
c.setSubject("Pertanyaan dan keputusan untuk Pertamina sebelum pemasangan awal")
for image in images:
    c.drawImage(ImageReader(str(image)), 0, 0, width=1280, height=720, preserveAspectRatio=True, mask="auto")
    c.showPage()
c.save()
print(f"WROTE {out} pages={len(images)}")
