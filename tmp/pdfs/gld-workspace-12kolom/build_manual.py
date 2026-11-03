"""Illustrated current UI / compact CSV guide. --plan does not author a PDF."""
from pathlib import Path
import importlib.util,json,hashlib,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('previous_workspace_guide',ROOT/'tmp/workspace-live-20261103/build_manual.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);pdf=old.pdf
from PIL import Image
OUTPUT=ROOT/'output/pdf/Manual-GLD-Dataset-Workspace-12-Kolom.pdf'
PAGES=list(old.PAGES)
field=list(PAGES[2]);field[0]='fields-current';field[1]='3. Pilih kolom CSV';field[2]='CSV dasar 12 kolom. Gain dan status tidak dicentang otomatis.';field[3]=None;field[4]=['#wfPrediction','#wfGain','#wfSensorStatus'];field[6]=[
 old.step('Predicted Class + Confidence','Centang untuk mengisi inferensi. Dua kolom selalu ada; kosong bila OFF atau belum valid. Checkbox menunggu Connect, lokasi CSV, serta model, binding dan nulling siap. Model 2 kini sudah disetujui operator.'),
 old.step('Gain opsional','Biarkan tidak dicentang untuk 12 kolom. Jika dipilih, delapan kolom gain ditambahkan sehingga jumlahnya 20.'),
 old.step('Status sensor opsional','Status juga menambah delapan kolom. Gain dan status sekaligus menghasilkan 28 kolom. Durasi/overrun dan metadata teknis tetap tersimpan internal.')]
PAGES[2]=tuple(field)
mode=list(PAGES[3]);mode[1]='4-5. Mode, label, lalu Lock';mode[2]='Pilih satu tombol bulat, isi label, lalu kunci setelah lima nomor hijau.';mode[3]=(245,550,265,380);mode[4]=['#wfMode','#wfLabel','#wfLock'];mode[6]=[
 old.step('Pilih satu mode','Rekam langsung membekukan CSV saat putus. Pulih otomatis mengembalikan data tertunda ke CSV yang sama. Hanya satu pilihan dapat aktif.'),
 old.step('Label dan timestamp','Isi kondisi sebenarnya, misalnya clear_air_test. Awalan HH:mm Hari dd/mm/yy dibuat saat lokasi CSV dipilih. Label berbeda dari hasil prediksi.'),
 old.step('Lock pengaturan','Setelah lima nomor hijau, aktifkan Lock. Input tetap terlihat tetapi tidak dapat diedit; kontrol rekaman muncul. Untuk konfigurasi baru setelah merekam, Reset lalu pilih CSV baru.')]
PAGES[3]=tuple(mode)
export=list(PAGES[9]);export[6]=[
 old.step('Export CSV','Klik Export CSV di bawah tabel untuk mengunduh salinan file rekaman. CSV baru default berisi 12 kolom; lihat halaman format CSV setelah ini.'),
 old.step('Tunggu verifikasi','Sebaiknya Stop dan tunggu verifikasi dahulu. File asli tetap berada di lokasi pilihan. CSV lama tidak diubah oleh pembaruan format.'),
 old.step('Tabel dan CSV','Tabel menampilkan 10 sampel terakhir dan nomor baris untuk navigasi. CSV menyimpan seluruh baris; metadata teknisnya berada di catatan internal.')]
PAGES[9]=tuple(export)
PAGES.insert(0,('firmware-final-choice','Pilih paket hotspot yang benar','Tiga pilihan hotspot terbaru menggantikan enam pilihan tahap lama.',None,['#firmwareUploadModel'],'firmware',[
 old.step('Pilih model yang sesuai','Pilih salah satu dari tiga paket final di bawah. GLD1002 terakhir memakai Model 2 (dipilih operator); angka ID perangkat tidak menentukan model. Paket Board biasa tidak menyalakan hotspot Dataset.'),
 old.step('24 V dan Reset NVS OFF','Gunakan 24 V, pilih COM GLD yang benar dan biarkan Reset NVS tidak dicentang. Tunggu upload terverifikasi dan boot selesai. Jangan kalibrasi atau bind ulang bila profil dan binding masih cocok.'),
 old.step('Fitur biasa ditambah hotspot','Ketiga paket final sudah dibuild dan dipasang di Hub. Running, Nulling dan pengaturan tetap lewat COM; Dataset lewat Wi-Fi. Stop, verifikasi CSV dan Disconnect Dataset sebelum kembali mengubah pengaturan COM.')]))
PAGES.insert(11,('csv-format','Isi CSV: 12 kolom utama','Gunakan sesi/file baru setelah Ctrl+F5. CSV lama tetap utuh.',None,[],'schema',[]))
PAGES.append(('connection-help','Wi-Fi tersambung, tetapi Connect gagal?','Indikator Windows dan koneksi data Operator Hub adalah dua pemeriksaan berbeda.',None,[],'connection',[]))

def label(c,layout,*args,**kwargs):return pdf.label(c,layout,*args,**kwargs)
def sources():
 raw={s['key']:s for s in json.loads(old.SOURCE.read_text(encoding='utf-8'))['screenshots']}
 extra=old.HERE/'real-browser-notice-confirmed/evidence.json'
 if extra.exists():raw.update({s['key']:s for s in json.loads(extra.read_text())['screenshots'] if s['key'] in {'replay-disconnected','replay-recovered'}})
 raw.update({s['key']:s for s in json.loads((HERE/'current-capture.json').read_text())['screenshots']})
 return raw
def schema(c,layout):
 names=['Waktu (ms)','Label pengujian','MQ8 (V)','MQ135 (V)','MQ3 (V)','MQ5 (V)','MQ4 (V)','MQ7 (V)','MQ6 (V)','MQ2 (V)','Predicted Class','Confidence']
 for side in range(2):
  x=pdf.MARGIN+side*399;w=387;pdf.panel(c,layout,x,235,w,230,role='column_list')
  for i,name in enumerate(names[side*6:side*6+6]):
   y=447-i*35;pdf.bubble(c,side*6+i+1,x+20,y-4,9);label(c,layout,name,x+40,y+3,w-52,24,12,True)
 for i,(title,body) in enumerate([('12 kolom','Gain dan Status sensor OFF.'),('20 kolom','Gain saja ATAU Status sensor saja.'),('28 kolom','Gain DAN Status sensor ON.')]):
  x=pdf.MARGIN+i*266;pdf.panel(c,layout,x,146,254,73,role='optional_count');label(c,layout,title,x+12,206,230,23,14,True);label(c,layout,body,x+12,180,230,28,10)
 label(c,layout,'Waktu adalah timestamp GLD dalam milidetik. Label memuat awalan jam/hari/tanggal. Predicted Class tetap indeks kelas model; Confidence bernilai 0..1 (misalnya 0,988 = 98,8%). Saat prediksi belum valid, kedua sel kosong.',pdf.MARGIN,125,786,49,10.5)
 label(c,layout,'ID perangkat/sesi/boot, urutan sampel, profil, model, waktu scan, overrun dan detail inferensi tetap tersimpan internal. Continue serta verifikasi penuh tetap menggunakan catatan tersebut.',pdf.MARGIN,72,786,29,9.8)

def connection_help(c,layout):
 items=[
  ('Hotspot tidak ditemukan','Pastikan 24 V terpasang dan boot selesai. Upload paket Hotspot Wizard Dataset sesuai Model 1/2/3, bukan paket Board biasa. Scan ulang dan pilih ID GLD yang benar.'),
  ('Windows: No Internet','Ini normal pada hotspot GLD. Tetap di jaringan GLD-DATASET-ID selama merekam. Password diambil otomatis oleh Hub. Tanda Wi-Fi tersambung belum membuktikan layanan data siap.'),
  ('Hub belum Connected','Pastikan tidak ada sesi aktif/pemulihan di tab atau aplikasi lain. Lepas koneksi COM untuk alur Dataset. Setelah sesi lama selesai, Connect sekali dan tunggu hasil; jangan menekan Start sebelum terhubung.'),
  ('Prediksi belum tersedia','Baca GET_STATUS lewat COM setelah Dataset Disconnect. Model harus disetujui, profil nulling valid dan profil bound sama dengan aktif. Jika memang mismatch, gunakan Running > Settings > Model & Nulling Profile > Use Latest Nulling Profile, lalu baca konfirmasi dan cek status lagi.'),
  ('Hub tidak bisa dibuka','Jalankan apps/operator-hub/run-operator-hub.bat pada terminal yang terlihat. Jika port sudah dipakai, buka Hub yang berjalan di http://127.0.0.1:5173. Jangan membuat proses kedua atau menutup backend ketika sesi masih aktif.'),
  ('Uji terbaru dan batasnya','3 Nov 2026: Model 2 di COM7 di-upload dengan Reset NVS OFF; profil/binding #2 utuh. Hello dan Connect Hub berhasil, prediksi tersedia. Sesudah handshake diputus, Hello kembali dalam 2,67 detik tanpa reboot. Tes ini tidak merekam grafik/CSV atau menguji putus Wi-Fi selama 5 menit.')]
 for i,(title,body) in enumerate(items):
  x=pdf.MARGIN+(i%2)*399;top=465-(i//2)*132
  pdf.panel(c,layout,x,top-121,387,121,role='connection_help')
  pdf.bubble(c,i+1,x+18,top-20,9)
  label(c,layout,title,x+36,top-10,339,26,12,True)
  label(c,layout,body,x+12,top-43,363,73,10.1)
 label(c,layout,'Screenshot halaman sebelumnya adalah bukti UI/pengujian terdahulu. Uji koneksi terbaru memakai API lokal Hub dan data Hello GLD asli; tidak ada screenshot rekaman baru yang dibuat.',pdf.MARGIN,57,786,28,9.1)

def build(author=False):
 raw=sources();pdf.fonts();layout=pdf.Layout();c=pdf.canvas.Canvas(str(OUTPUT),pagesize=(pdf.WIDTH,pdf.HEIGHT)) if author else None
 for number,(key,title,subtitle,crop,selectors,kind,notes) in enumerate(PAGES,1):
  layout.begin(dict(key=key,title=title),number)
  if c:
   c.setFillColor(pdf.PAPER);c.rect(0,0,pdf.WIDTH,pdf.HEIGHT,fill=1,stroke=0);c.setFillColor(pdf.TEAL);c.rect(0,pdf.HEIGHT-6,pdf.WIDTH,6,fill=1,stroke=0)
  caption='Screenshot GLD1002 terdahulu: ilustrasi kontrol/grafik, bukan uji Model 2 terbaru; format CSV lihat halaman 12.'
  if key in {'fields-current','firmware-final-choice'}:caption='Screenshot UI terbaru (baca saja); tidak ada upload atau pengoperasian GLD pada pengambilan gambar ini.'
  if kind=='schema':caption='Format CSV ringkas yang berlaku pada aplikasi saat ini; metadata teknis tersimpan internal.'
  if kind=='connection':caption='Panduan berdasarkan paket final dan hasil uji koneksi GLD1002 Model 2 pada 3 November 2026.'
  for text,top,size,bold,height in [('PANDUAN OPERATOR / DATASET WORKSPACE - CSV 12 KOLOM',pdf.HEIGHT-17,9,True,16),(caption,pdf.HEIGHT-35,8.1,False,20),(title,pdf.HEIGHT-64,23,True,32),(subtitle,pdf.HEIGHT-99,10,False,24)]:label(c,layout,text,pdf.MARGIN,top,786,height,size,bold)
  if kind=='schema':schema(c,layout)
  elif kind=='connection':connection_help(c,layout)
  else:
   entry=dict(raw[key]);entry['key']=key;entry['path']=Path(entry['path'])
   with Image.open(entry['path']) as im:entry['width'],entry['height']=im.size
   entry['boxes']=[pdf.clamp_box(b,entry['width'],entry['height']) for b in entry['boxes'] if b['selector'] in selectors and (key in {'fields-current','firmware-final-choice'} or b['y']>=75) and b['y']<entry['height']]
   entry['boxes']=[b for b in entry['boxes'] if b];assert entry['boxes'],key
   entry.update(source_sha256=hashlib.sha256(entry['path'].read_bytes()).hexdigest(),skipped_offscreen_boxes=[])
   if crop is not None:entry['crop']=dict(zip(('x','y','w','h'),crop))
   if kind=='firmware':
    pdf.draw_screenshot(c,layout,entry,pdf.MARGIN,345,786,120)
    for i,n in enumerate((1,2,3)):
     y=321-i*29;pdf.panel(c,layout,pdf.MARGIN,y-23,786,26,role='final_model');label(c,layout,f'GLD1 Model {n} - Hotspot Wizard Dataset',pdf.MARGIN+12,y-2,762,23,11,True)
    pdf.cards(c,layout,[dict(n=1 if i==0 else 'i',**n) for i,n in enumerate(notes)],top=214,bottom=43,size=9.3)
   elif kind=='side':
    pdf.draw_screenshot(c,layout,entry,pdf.MARGIN,65,320,400);x=370;y=455;w=pdf.WIDTH-x-pdf.MARGIN
    for i,note in enumerate(notes):
     pdf.panel(c,layout,x,y-111,w,111,role='instruction_panel');pdf.bubble(c,entry['boxes'][i]['n'] if i<len(entry['boxes']) else 'i',x+16,y-18,8)
     label(c,layout,note['title'],x+32,y-10,w-44,26,12,True);label(c,layout,note['body'],x+12,y-43,w-24,62,10.8);y-=125
   else:
    pdf.draw_screenshot(c,layout,entry,pdf.MARGIN,180,786,290);pdf.cards(c,layout,[dict(n=entry['boxes'][i]['n'] if i<len(entry['boxes']) else 'i',**n) for i,n in enumerate(notes)],top=163,bottom=43,size=9.2)
  label(c,layout,'3 November 2026 | PNG asli; kotak dan nomor panduan berupa anotasi vektor.',pdf.MARGIN,22,720,12,8)
  if c:c.setFillColor(pdf.MUTED);c.setFont('WizardBold',8);c.drawRightString(pdf.WIDTH-pdf.MARGIN,14,f'{number:02d} / {len(PAGES):02d}');c.showPage()
 if c:c.save()
 (HERE/'layout-report.json').write_text(json.dumps(layout.pages,indent=2),encoding='utf-8')
 return len(layout.pages)
if __name__=='__main__':print(json.dumps({'pages':build('--author' in sys.argv),'authored':'--author' in sys.argv,'output':str(OUTPUT)}))
