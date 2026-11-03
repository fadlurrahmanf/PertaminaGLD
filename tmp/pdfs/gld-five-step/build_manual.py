"""Five-step manual; importing/--plan never authors a PDF."""
import importlib.util
import json
import hashlib
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('wizard_manual_layout',ROOT/'tmp/pdfs/gld-workflow-manual/build_manual.py')
pdf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pdf)
EVIDENCE=ROOT/'tmp/workflow-ux-20261103/browser-output-final/browser-evidence.json'
OUTPUT=ROOT/'output/pdf/Manual-GLD-Dataset-5-Langkah.pdf'

def step(title,body):return dict(title=title,body=body)

PAGES=[
 ('02-device-connected','1. Hubungkan GLD','Scan, pilih GLD yang benar, lalu Connect. Password diambil otomatis oleh backend.',[
  step('Pilih ID perangkat','Klik Scan Nearby GLD, lalu pilih misalnya GLD-1002. Scan, pilihan dan koneksi kini berada dalam satu langkah.'),
  step('Tunggu Connected','Lanjutkan sesudah indikator hijau. Jika gagal, periksa hotspot, 24 V dan profil nulling. Tidak perlu mengetik password.'),
  step('Pilih file CSV','Tentukan lokasi dan nama baru setelah koneksi siap. Aplikasi tidak menimpa CSV lama.')]),
 ('03-options-ready','2-5. File, kolom, mode dan label','Nomor hijau mengikuti urutan. Langkah berikutnya menunggu langkah sebelumnya siap.',[
  step('Prediksi dan kolom lain','Centang Predicted Class + Confidence setelah GLD mendukung prediksi dan lokasi CSV dipilih. Gain, status dan durasi bersifat opsional.'),
  step('Pilih satu mode','Rekam langsung membekukan CSV saat putus. Pulih otomatis mengembalikan data tertunda ke CSV yang sama.'),
  step('Timestamp di depan label','Format HH:mm Hari dd/mm/yy, misalnya 07:35 Selasa 03/11/26. Waktu dan label lengkap ikut masuk CSV.'),
  step('Lock setelah siap','Lima nomor harus hijau sebelum Lock. Nilai bawaan yang valid baru hijau setelah prasyaratnya terpenuhi.')]),
 ('04-locked','Lock, lalu Start','Pengaturan tetap terlihat. Saat Lock aktif, input tidak bisa diubah.',[
  step('Kunci pengaturan','Aktifkan Lock setelah semua langkah siap. Sebelum rekaman pertama, Unlock mengizinkan pengaturan diedit kembali.'),
  step('Start satu kali','Start memulai rekaman dan menjadi disabled. Tunggu hitungan sampel bertambah.'),
  step('Pause belum aktif','Sebelum Start, Pause dan Stop disabled. Setelah merekam, keduanya tersedia.'),
  step('Stop menutup CSV','Saat merekam atau Pause, Stop meminta penyelesaian perangkat dan memeriksa file sebelum memberi konfirmasi.')]),
 ('05-recording','Grafik sama dengan Running','Delapan kurva, grid, sumbu nol, warna dan label sensor memakai renderer yang sama.',[
  step('Hitungan tersimpan','Sampel dihitung setelah penyimpanan. Target satu pembacaan lengkap delapan sensor adalah setiap 500 ms.'),
  step('Grafik dan prediksi','Predicted Class serta Confidence Score ada di atas grafik. Range mengubah tampilan saja, tidak mengurangi CSV.')]),
 ('06-paused','Pause dan Resume','Pause menghentikan akuisisi setelah terkonfirmasi, bukan sekadar menyembunyikan baris.',[
  step('Pause menjadi Resume','Saat dijeda, tidak ada baris pengukuran baru. Klik Resume untuk meneruskan sesi yang sama tanpa mengisi waktu jeda.'),
  step('Stop juga saat Pause','Stop tetap tersedia. Reset sesi berada pada baris Lock; saat Pause, Reset harus menutup dan memverifikasi sesi dahulu.')]),
 ('07-stop-verified','Stop: baca verifikasi, lalu OK','Notifikasi muncul sesudah seluruh baris dan kolom CSV cocok dengan ledger lengkap.',[
  step('Periksa hasil','Sesi lengkap dan tidak lengkap dibedakan. Terputus atau buffer habis dapat membuat sesi incomplete meskipun prefix file berhasil diperiksa.'),
  step('Cocokkan jumlah','Verifikasi memakai seluruh file, termasuk baris yang sudah tidak terlihat dalam tabel atau grafik.'),
  step('Tutup dengan OK','OK menutup pemberitahuan. Jangan menganggap respons tombol Stop saja sudah berarti file selesai.')]),
 ('08-continue-ready','Continue: CSV yang sama','Continue setelah Stop berbeda dari Resume setelah Pause.',[
  step('Lanjutkan file','Continue menambah segmen pengukuran baru dalam CSV yang sama. Timestamp label dan nomor baris global dipertahankan.'),
  step('CSV telah terverifikasi','Verifikasi file lama harus berhasil sebelum Continue. Perangkat, profil, model dan skema diperiksa sebelum menambah baris.'),
  step('Ubah melalui Reset','Setelah CSV dimulai, kolom, mode dan label tetap sama. Untuk mengubahnya, Reset sesi dan pilih CSV baru.')]),
 ('09b-owned-cleanup-retry','Jika penutupan sesi tertunda','Hanya GLD yang sama boleh dipakai untuk menyelesaikan rekaman yang belum ditutup.',[
  step('Hubungkan ulang','Tombol ini tetap tersedia ketika penutupan tertunda dan retry berhenti, walaupun Lock aktif. Password tetap diurus backend.'),
  step('Tunggu penyelesaian','CSV mode langsung tetap membeku. Jangan Reset atau membuat sesi baru sebelum aplikasi mengonfirmasi penutupan.')]),
 ('13-export-table','Export berada di bawah tabel','Export CSV mengunduh salinan file yang disimpan di lokasi pilihan Anda.',[
  step('Tabel sampel terakhir','Tabel memuat baris terakhir; CSV memuat seluruh baris. Prediksi yang warmup/error/not_ready disimpan kosong, bukan nilai pengganti.'),
  step('Export CSV','Gulir ke bawah tabel dan klik Export CSV. Sebaiknya lakukan setelah Stop dan verifikasi. File asli tetap tersimpan.')]),
 ('11-replay-complete','Batas pemulihan dan langkah berikutnya','Pertahankan GLD dan backend tetap menyala selama merekam atau memulihkan data.',[
  step('Periksa verifikasi','Setelah Pulih otomatis dan Stop, seluruh isi CSV harus cocok dengan ledger. Sesi incomplete tidak boleh disebut lengkap.'),
  step('Periksa hitungan','Jumlah sampel dan data lama tetap dalam file yang sama. Saat memulihkan, pertahankan GLD dan backend tetap menyala.'),
  step('Batas dan perangkat asli','Batas RAM lima menit; reboot GLD menghapus buffer. Native Wi-Fi, ADC 500 ms dan inferensi masih memerlukan uji GLD asli, bukan simulasi PC.')]),
]

def images():
 data=json.loads(EVIDENCE.read_text(encoding='utf-8'));records={e['key']:e for e in data['screenshots']}
 extra=ROOT/'tmp/workflow-ux-20261103/manual-capture.json'
 if extra.exists():records.update({e['key']:e for e in json.loads(extra.read_text())['screenshots']})
 out={}
 for key,*_ in PAGES:
  raw=records[key];path=Path(raw['path']);boxes=[]
  for source in raw['boxes']:
   if source['y']<75:continue # Sticky application header occludes these controls.
   b=pdf.clamp_box(source,raw['width'],raw['height'])
   if b:boxes.append(b)
  if key=='05-recording':boxes=[b for b in boxes if b['selector'] in ('#wfCount','#wfChart')]
  if key=='11-replay-complete':boxes=[b for b in boxes if b['selector']!='#wfChart']
  if key=='06-paused':boxes=[b for b in boxes if b['selector']!='#wfReset']
  if key=='08-continue-ready':boxes=[b for b in boxes if b['selector']!='#wfReset']
  assert boxes,key
  crops={'02-device-connected':(230,90,1105,470),'03-options-ready':(235,95,1100,590),'04-locked':(230,600,1105,360),'05-recording':(230,135,1105,640),'06-paused':(230,80,1105,360),'08-continue-ready':(230,80,1105,360),'09b-owned-cleanup-retry':(230,90,1105,340),'11-replay-complete':(230,80,1105,360),'13-export-table':(235,594,1100,380)}
  out[key]=dict(raw,path=path,boxes=boxes,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),skipped_offscreen_boxes=[])
  if key in crops:out[key]['crop']=dict(zip(('x','y','w','h'),crops[key]))
 return out

def build(author=False):
 sources=images();pdf.fonts();layout=pdf.Layout()
 c=pdf.canvas.Canvas(str(OUTPUT),pagesize=(pdf.WIDTH,pdf.HEIGHT)) if author else None
 for number,(key,title,subtitle,notes) in enumerate(PAGES,1):
  page=dict(key=key,title=title,subtitle=subtitle);layout.begin(page,number)
  if c:
   c.setFillColor(pdf.PAPER);c.rect(0,0,pdf.WIDTH,pdf.HEIGHT,fill=1,stroke=0)
   c.setFillColor(pdf.TEAL);c.rect(0,pdf.HEIGHT-6,pdf.WIDTH,6,fill=1,stroke=0)
  for content,top,size,bold in [('PANDUAN OPERATOR / DATASET GLD - 5 LANGKAH',pdf.HEIGHT-17,9,True),(pdf.DISCLOSURE,pdf.HEIGHT-33,8.2,False),(title,pdf.HEIGHT-57,23,True),(subtitle,pdf.HEIGHT-93,10,False)]:
   pdf.label(c,layout,content,pdf.MARGIN,top,pdf.WIDTH-2*pdf.MARGIN,33 if size==23 else 28,size,bold)
  pdf.draw_screenshot(c,layout,sources[key],pdf.MARGIN,190,pdf.WIDTH-2*pdf.MARGIN,280)
  # Match cards to actual numbered rectangles, never invent a hidden target.
  boxes=sources[key]['boxes'];items=[]
  for i,note in enumerate(notes):items.append(dict(n=boxes[i]['n'] if i<len(boxes) else '!',**note))
  pdf.cards(c,layout,items,top=171,bottom=42,size=9.2)
  pdf.label(c,layout,'SIMULASI PC | Screenshot asli + kotak panduan | 3 November 2026',pdf.MARGIN,21,pdf.WIDTH-120,12,8)
  if c:
   c.setFillColor(pdf.MUTED);c.setFont('WizardBold',8);c.drawRightString(pdf.WIDTH-pdf.MARGIN,13,f'{number:02d} / {len(PAGES):02d}');c.showPage()
 if c:c.save()
 (HERE/'layout-report.json').write_text(json.dumps(layout.pages,indent=2),encoding='utf-8')
 return len(layout.pages)

if __name__=='__main__':
 print(json.dumps({'pages':build('--author' in sys.argv),'authored':'--author' in sys.argv,'output':str(OUTPUT)}))
