"""Current Workspace manual; plan/import does not author a PDF."""
from pathlib import Path
import sys,importlib.util,json,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('workspace_pdf_layout',ROOT/'tmp/pdfs/gld-workflow-manual/build_manual.py')
pdf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pdf)
from PIL import Image
SOURCE=HERE/'real-browser-inference/evidence.json'
OUTPUT=ROOT/'output/pdf/Manual-GLD-Dataset-Workspace.pdf'
NOTE='GLD asli, Model 1 / protokol 3. Pada uji otomatis, lokasi CSV diisi runner; data dan kontrol GLD nyata.'
def step(title,body):return dict(title=title,body=body)
PAGES=[
 ('workspace-initial','1. Scan, pilih GLD, lalu Connect','Hubungkan USB hanya untuk daya/administrasi. Rekaman Dataset memakai Wi-Fi.',(245,275,265,230),['#wfScan','#wfDevice','#wfConnect'],'side',[
  step('Scan Nearby GLD','Nyalakan GLD dengan 24 V, firmware Hotspot Wizard Dataset dan profil nulling valid. Klik Scan dan tunggu daftar jaringan diperbarui.'),
  step('Pilih ID GLD','Pilih perangkat yang benar, misalnya GLD-1002. Firmware harus sesuai Model 1/2/3; saat upload, Reset NVS tetap OFF.'),
  step('Connect','Password diambil otomatis. Tunggu indikator Connected. Hotspot GLD tidak menyediakan Internet; koneksi Internet laptop akan terputus selama dipakai.')]),
 ('connected-replay','2. Pilih lokasi CSV','Lokasi rekaman dipilih setelah GLD terhubung.',(245,535,265,200),['#wfChooseFile'],'side',[
  step('Pilih file CSV','Klik Pilih file CSV, lalu tentukan folder dan nama file baru pada dialog Windows. File lama tidak ditimpa.'),
  step('Periksa tujuan','CSV akan bertambah di lokasi tersebut selama rekaman. Export CSV nanti mengunduh salinan file yang sama.'),
  step('Urutan nomor hijau','Langkah berikutnya baru dapat hijau setelah langkah sebelumnya terpenuhi. Nilai bawaan tidak melewati pemeriksaan koneksi dan file.')]),
 ('settings-replay','3-4. Pilih kolom dan mode','Pilihan mode berupa tombol bulat; hanya satu mode dapat aktif.',(245,330,265,335),['#wfPrediction','#wfMode'],'side',[
  step('Prediksi dan kolom tambahan','Predicted Class + Confidence aktif jika model, binding dan kalibrasi lolos. Gain, Status sensor dan Durasi/overrun bersifat opsional. Model 2 belum production-approved.'),
  step('Rekam langsung / Pulih otomatis','Rekam langsung membekukan CSV saat putus. Pulih otomatis memasukkan data tertahan ke CSV yang sama sesudah tersambung.'),
  step('Data wajib selalu tersimpan','Delapan tegangan, waktu, identitas dan label selalu masuk CSV. Prediksi saat pemanasan belum memiliki kelas/confidence yang valid.')]),
 ('settings-replay','5. Label, lalu Lock','Input tetap terlihat saat dikunci.',(245,710,265,210),['#wfLabelStamp','#wfLabel','#wfLock'],'side',[
  step('Timestamp otomatis','Format diawali jam 24 jam: HH:mm Hari dd/mm/yy. Waktu dibuat ketika lokasi CSV dipilih dan menjadi awalan label lengkap.'),
  step('Isi label pengujian','Isi kondisi sebenarnya, misalnya clear_air_test. Label berbeda dari hasil prediksi model.'),
  step('Aktifkan Lock','Lima nomor harus hijau. Lock menonaktifkan input dan menampilkan kontrol. Setelah CSV dimulai, konfigurasi tetap dilindungi; gunakan Reset dan file baru untuk mengubahnya.')]),
 ('recording-real','Start: mulai merekam','Satu tombol utama berganti fungsi sesuai keadaan.',(535,230,780,260),['#wfPrimary','#wfStop','#wfCount'],'wide',[
  step('Start menjadi Pause','Klik Start sekali. Setelah terkonfirmasi, tombol utama menjadi Pause. Stop aktif dan hitungan sampel bertambah setelah penyimpanan.'),
  step('Stop aktif','Stop dapat dipakai setelah Start terkonfirmasi, termasuk ketika pengukuran dijeda.'),
  step('Hitungan tersimpan','Hitungan bertambah setelah data disimpan. Jangan menutup proses backend, mematikan GLD atau mematikan laptop selama merekam.')]),
 ('recording-real','Grafik dan delapan nilai sensor','Renderer grafik mengikuti tab Running; CSV menyimpan seluruh data sesi.',(535,490,780,490),['#wfChart'],'wide',[
  step('Delapan kanal','MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6 dan MQ2. Nilai saat ini, gain dan status ditampilkan di bawah grafik.'),
  step('Kelas dan confidence','Hasil inferensi ada di atas grafik. Pemanasan membutuhkan 10 sampel, sekitar 5 detik, setelah Start atau Resume. Range hanya mengubah tampilan.'),
  step('Jeda pada grafik','Pause atau segmen baru dapat membuat celah. Aplikasi tidak membuat sampel pengisi untuk waktu tanpa pengukuran.')]),
 ('paused-real','Pause: tombol berubah menjadi Resume','Jeda menghentikan pengukuran di GLD setelah dikonfirmasi.',(535,230,780,145),['#wfPrimary','#wfStop','#wfState'],'wide',[
  step('Pause menjadi Resume','Klik Pause ketika merekam. Setelah terkonfirmasi tombol menjadi Resume; klik untuk melanjutkan sesi yang sama. Inferensi melakukan pemanasan lagi.'),
  step('Stop saat Pause','Stop tetap dapat dipakai ketika Dijeda. Reset saat Pause harus menyelesaikan Stop dan verifikasi dahulu.'),
  step('Periksa status Dijeda','Hitungan dan isi CSV berhenti bertambah setelah Pause terkonfirmasi. Aplikasi tidak membuat baris pengisi selama jeda.')]),
 ('stop-verified-0','Stop: tunggu verifikasi CSV, lalu OK','Popup muncul sesudah seluruh baris dan kolom file diperiksa.',(585,400,400,200),['#appModalTitle','#appModalMessage','#appModalOkBtn'],'wide',[
  step('Notifikasi CSV terverifikasi','Stop meminta GLD menyelesaikan sesi dan menunggu data tersisa. Popup baru muncul setelah verifikasi. Jangan menutup backend selagi proses berlangsung.'),
  step('Periksa hasil','Seluruh CSV dibandingkan dengan ledger, bukan hanya 10 baris tabel. Status tidak lengkap tetap harus dibaca sebagai tidak lengkap.'),
  step('OK','Baca pesan verifikasi, lalu klik OK. Setelah itu Continue dapat dipakai; Pause dan Stop menjadi nonaktif.')]),
 ('continue-real','Continue: lanjutkan CSV yang sama','Continue setelah Stop berbeda dari Resume setelah Pause.',(535,230,780,145),['#wfPrimary'],'wide',[
  step('Continue','Tombol utama berubah menjadi Continue setelah Stop terverifikasi. Klik untuk membuat segmen baru dalam CSV yang sama.'),
  step('File dilindungi','Aplikasi memeriksa konfigurasi, perangkat, profil, model dan integritas file sebelum append. Jangan mengedit CSV dari luar saat akan Continue.'),
  step('Reset sesi','Reset membersihkan pilihan sesi dan kembali ke langkah awal, tanpa menghapus CSV atau NVS. Reset tidak aktif selama merekam atau Resume.')]),
 ('export-real','Export CSV di bawah tabel','File tujuan sudah disimpan selama merekam; Export membuat salinan unduhan.',None,['#wfExport','#wfVerification'],'wide',[
  step('Export CSV','Klik Export CSV, lalu buka unduhan browser. Kelas dan confidence hanya ada di CSV jika dipilih sebelum Lock.'),
  step('Tunggu Stop terverifikasi','Sebaiknya lakukan Export setelah Stop dan hasil verifikasi dibaca. CSV asli tetap berada di folder yang dipilih.'),
  step('Tabel hanya sampel terakhir','Tabel menampilkan 10 baris terakhir. Gunakan scroll horizontal untuk kolom di kanan. CSV memuat semua baris sesi.')]),
 ('replay-disconnected','Jika koneksi Wi-Fi putus','Pertahankan GLD dan backend tetap menyala.',(535,230,780,165),['#wfState','#wfMessage'],'wide',[
  step('Pulih otomatis','Sambungkan laptop lagi ke GLD-DATASET dengan ID yang sama. Backend mengambil sampel tertunda ke CSV yang sama; jangan Start sesi baru.'),
  step('Ikuti pesan pemulihan','Tunggu data tersisa kembali. Pada mode Rekam langsung, CSV lama membeku; tunggu penutupan sesi sebelum Continue atau Reset.'),
  step('Batas 5 menit','Buffer berada di RAM GLD. Saat batas tercapai, sampling berhenti tidak lengkap. Mati/reboot menghapus buffer; restart backend bukan pemulihan yang dijamin.')]),
 ('replay-recovered','Sesudah tersambung kembali','Tunggu pemulihan selesai sebelum menutup sesi.',(535,230,780,145),['#wfCount'],'wide',[
  step('Periksa hitungan','Data tertunda kembali dengan timestamp aslinya. Wi-Fi tersambung saja belum berarti seluruh sampel sudah tersimpan.'),
  step('Stop dan Export','Setelah pulih, klik Stop dan tunggu verifikasi. Unduh salinan CSV untuk analisis.'),
  step('Hasil uji dan batasnya','Grafik, kontrol, CSV dan putus-sambung telah diuji di GLD1002. Uji radio ini berupa putus singkat; batas penuh 300 detik diperiksa pada simulasi PC.')])
]
def build(author=False):
 data=json.loads(SOURCE.read_text(encoding='utf-8'));assert data['hardware'] and data['ok']
 raw={s['key']:s for s in data['screenshots']};pdf.fonts();layout=pdf.Layout()
 extra=HERE/'real-browser-notice-confirmed/evidence.json'
 if extra.exists():
  current=json.loads(extra.read_text(encoding='utf-8'));assert current['hardware'] and current['ok']
  raw.update({s['key']:s for s in current['screenshots'] if s['key'] in {'replay-disconnected','replay-recovered'}})
 c=pdf.canvas.Canvas(str(OUTPUT),pagesize=(pdf.WIDTH,pdf.HEIGHT)) if author else None
 for number,(key,title,subtitle,crop,selectors,kind,notes) in enumerate(PAGES,1):
  entry=dict(raw[key]);entry['key']=key;entry['path']=Path(entry['path'])
  with Image.open(entry['path']) as im:entry['width'],entry['height']=im.size
  entry['boxes']=[]
  for b in raw[key]['boxes']:
   if b['selector'] not in selectors or b['y']<75 or b['y']>=entry['height']:continue
   clipped=pdf.clamp_box(b,entry['width'],entry['height'])
   if clipped:entry['boxes'].append(clipped)
  assert entry['boxes'],key
  entry.update(source_sha256=hashlib.sha256(entry['path'].read_bytes()).hexdigest(),skipped_offscreen_boxes=[])
  if crop is not None:entry['crop']=dict(zip(('x','y','w','h'),crop))
  page=dict(key=key,title=title);layout.begin(page,number)
  if c:
   c.setFillColor(pdf.PAPER);c.rect(0,0,pdf.WIDTH,pdf.HEIGHT,fill=1,stroke=0);c.setFillColor(pdf.TEAL);c.rect(0,pdf.HEIGHT-6,pdf.WIDTH,6,fill=1,stroke=0)
  for text,top,size,bold,height in [('PANDUAN OPERATOR / DATASET WORKSPACE',pdf.HEIGHT-17,9,True,16),(NOTE,pdf.HEIGHT-35,8.2,False,20),(title,pdf.HEIGHT-64,23,True,32),(subtitle,pdf.HEIGHT-99,10,False,24)]:
   pdf.label(c,layout,text,pdf.MARGIN,top,pdf.WIDTH-2*pdf.MARGIN,height,size,bold)
  if kind=='side':
   pdf.draw_screenshot(c,layout,entry,pdf.MARGIN,65,320,400)
   x=370;y=455;width=pdf.WIDTH-x-pdf.MARGIN
   for i,note in enumerate(notes):
    pdf.panel(c,layout,x,y-111,width,111,role='instruction_panel')
    pdf.bubble(c,entry['boxes'][i]['n'] if i<len(entry['boxes']) else 'i',x+16,y-18,8)
    pdf.label(c,layout,note['title'],x+32,y-10,width-44,26,12,True)
    pdf.label(c,layout,note['body'],x+12,y-43,width-24,62,10.8)
    y-=125
  else:
   pdf.draw_screenshot(c,layout,entry,pdf.MARGIN,180,pdf.WIDTH-2*pdf.MARGIN,290)
   items=[dict(n=entry['boxes'][i]['n'] if i<len(entry['boxes']) else 'i',**note) for i,note in enumerate(notes)]
   pdf.cards(c,layout,items,top=163,bottom=43,size=9.2)
  pdf.label(c,layout,'3 November 2026 | Screenshot browser asli; kotak dan nomor berupa anotasi vektor.',pdf.MARGIN,22,pdf.WIDTH-120,12,8)
  if c:
   c.setFillColor(pdf.MUTED);c.setFont('WizardBold',8);c.drawRightString(pdf.WIDTH-pdf.MARGIN,14,f'{number:02d} / {len(PAGES):02d}');c.showPage()
 if c:c.save()
 (HERE/'manual-layout-report.json').write_text(json.dumps(layout.pages,indent=2),encoding='utf-8')
 return len(layout.pages)
if __name__=='__main__':print(json.dumps({'pages':build('--author' in sys.argv),'authored':'--author' in sys.argv,'output':str(OUTPUT)}))
