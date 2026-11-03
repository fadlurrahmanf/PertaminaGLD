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
 old.step('Predicted Class + Confidence','Centang untuk mengisi inferensi. Kedua kolom selalu ada; nilainya kosong saat tidak dipilih atau belum valid. Checkbox menunggu Connect dan lokasi CSV. Prediksi Model 2 menunggu persetujuan model.'),
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
 old.step('Pilih sesuai model board','Untuk GLD pertama yang diuji, pilih GLD1 Model 1 - Hotspot Wizard Dataset. Model 1 - Board 1 biasa tidak menyalakan hotspot Dataset.'),
 old.step('24 V dan Reset NVS OFF','Gunakan 24 V dan biarkan Reset NVS tidak dicentang. Jika upload sebelumnya mereset NVS, siapkan nulling dan binding model pada firmware biasa dahulu. Tunggu boot selesai sebelum Scan.'),
 old.step('Kontrol COM dan Dataset Wi-Fi','Alur yang disepakati: kontrol normal lewat COM; Dataset lewat Wi-Fi. Revisi firmware yang mempertahankan semua fitur normal masih menunggu compile dan uji, bukan otomatis tersedia karena menu diringkas.')]))
PAGES.insert(11,('csv-format','Isi CSV: 12 kolom utama','Gunakan sesi/file baru setelah Ctrl+F5. CSV lama tetap utuh.',None,[],'schema',[]))

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

def build(author=False):
 raw=sources();pdf.fonts();layout=pdf.Layout();c=pdf.canvas.Canvas(str(OUTPUT),pagesize=(pdf.WIDTH,pdf.HEIGHT)) if author else None
 for number,(key,title,subtitle,crop,selectors,kind,notes) in enumerate(PAGES,1):
  layout.begin(dict(key=key,title=title),number)
  if c:
   c.setFillColor(pdf.PAPER);c.rect(0,0,pdf.WIDTH,pdf.HEIGHT,fill=1,stroke=0);c.setFillColor(pdf.TEAL);c.rect(0,pdf.HEIGHT-6,pdf.WIDTH,6,fill=1,stroke=0)
  caption='Screenshot pengujian GLD1002 sebelumnya; alur tombol dan grafik Dataset tetap sama.'
  if key in {'fields-current','firmware-final-choice'}:caption='Screenshot UI terbaru (baca saja); tidak ada upload atau pengoperasian GLD pada pengambilan gambar ini.'
  if kind=='schema':caption='Format CSV ringkas yang berlaku pada aplikasi saat ini; metadata teknis tersimpan internal.'
  for text,top,size,bold,height in [('PANDUAN OPERATOR / DATASET WORKSPACE - CSV 12 KOLOM',pdf.HEIGHT-17,9,True,16),(caption,pdf.HEIGHT-35,8.1,False,20),(title,pdf.HEIGHT-64,23,True,32),(subtitle,pdf.HEIGHT-99,10,False,24)]:label(c,layout,text,pdf.MARGIN,top,786,height,size,bold)
  if kind=='schema':schema(c,layout)
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
