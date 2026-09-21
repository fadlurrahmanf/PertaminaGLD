"""Build source-derived GLD2 block diagrams: PDF, SVG and offline HTML."""
from pathlib import Path
import json, math, html, csv, textwrap
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PDF=ROOT/'output/pdf/GLD2-Block-Diagram.pdf'
DATA=json.loads((HERE/'source-net-evidence.json').read_text(encoding='utf8'))
C=DATA['components']; W,H=1200,800
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
P=canvas.Canvas(str(PDF),pagesize=(W,H)); P.setTitle('GLD2 | Diagram Blok Schematic'); P.setAuthor('PertaminaGLD')
COL={'ink':'#183044','muted':'#5D7180','line':'#CCD7DE','power':'#B86518','signal':'#147B75','bus':'#316FC0','control':'#8060AC','warn':'#AD4D35','bg':'#F4F7F9'}
sv=[]; pages=[]; number=0
def esc(x): return html.escape(str(x))
def rect(x,y,w,h,fill='white',stroke=None,r=8):
 P.setFillColor(fill); P.setStrokeColor(stroke or fill); P.roundRect(x,H-y-h,w,h,r,stroke=bool(stroke),fill=1)
 sv.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke or fill}"/>')
def txt(x,y,text,size=13,color=None,bold=False):
 color=color or COL['ink']; font='ArialBold' if bold else 'Arial'
 P.setFont(font,size); P.setFillColor(color); P.drawString(x,H-y-size*.82,str(text))
 sv.append(f'<text x="{x}" y="{y+size*.82}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{esc(text)}</text>')
def para(x,y,text,width,size=13,color=None,leading=None):
 leading=leading or size*1.4
 for line in str(text).split('\n'):
  words=line.split(); buf=''
  for word in words:
   test=(buf+' '+word).strip()
   if pdfmetrics.stringWidth(test,'Arial',size)>width and buf: txt(x,y,buf,size,color); y+=leading; buf=word
   else: buf=test
  txt(x,y,buf,size,color); y+=leading
 return y
def box(x,y,w,h,title,body='',kind='bus',size=13):
 rect(x,y,w,h,'white',COL['line']); rect(x,y,5,h,COL[kind],r=2)
 txt(x+16,y+14,title,15,bold=True)
 if body: para(x+16,y+40,body,w-30,size)
 return (x,y,w,h)
def line(points,kind='bus',label=None,lx=None,ly=None,dashed=False,arrow=True):
 color=COL[kind]; P.setStrokeColor(color); P.setLineWidth(1.8); P.setDash(5,4) if dashed else P.setDash()
 path=P.beginPath(); path.moveTo(points[0][0],H-points[0][1])
 for x,y in points[1:]: path.lineTo(x,H-y)
 P.drawPath(path); P.setDash()
 sv.append(f'<polyline points="'+ ' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="1.8"'+(' stroke-dasharray="5 4"' if dashed else '')+'/>')
 if arrow:
  a,b=points[-2:]; ang=math.atan2(b[1]-a[1],b[0]-a[0]); q=[b,(b[0]-8*math.cos(ang-.45),b[1]-8*math.sin(ang-.45)),(b[0]-8*math.cos(ang+.45),b[1]-8*math.sin(ang+.45))]
  P.setFillColor(color); path=P.beginPath(); path.moveTo(q[0][0],H-q[0][1]); [path.lineTo(x,H-y) for x,y in q[1:]]; path.close(); P.drawPath(path,stroke=0,fill=1)
  sv.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in q)+f'" fill="{color}"/>')
 if label:
  lx=lx if lx is not None else (points[0][0]+points[-1][0])/2
  ly=ly if ly is not None else (points[0][1]+points[-1][1])/2-17
  tw=pdfmetrics.stringWidth(label,'Arial',11); rect(lx-3,ly-2,tw+6,16,'#F4F7F9',r=2); txt(lx,ly,label,11,color)
def table(x,y,width,headers,rows,widths=None,rh=31,size=12):
 widths=widths or [width/len(headers)]*len(headers)
 rect(x,y,width,rh,COL['ink'],r=3); xx=x
 for h,w in zip(headers,widths): txt(xx+9,y+9,h,size,'white',True); xx+=w
 for i,row in enumerate(rows):
  yy=y+(i+1)*rh; rect(x,yy,width,rh,'white' if i%2==0 else '#EAF0F4',r=0); xx=x
  for val,w in zip(row,widths):
   assert pdfmetrics.stringWidth(str(val),'Arial',size)<w-15,(val,w)
   txt(xx+9,yy+9,val,size); xx+=w
 return y+(len(rows)+1)*rh
def start(title,subtitle):
 global sv,number
 sv=[]; number+=1; rect(0,0,W,H,COL['bg'],r=0)
 txt(38,24,'PERTAMINA GLD   /   SCHEMATIC BLOCK DIAGRAM',11,COL['signal'],True)
 txt(38,51,title,28,bold=True); txt(38,91,subtitle,13,COL['muted'])
def end():
 txt(38,765,'Sumber: source-GLD2.zip | Sheet_1 + net PCB; modul sensor: gambar referensi terpisah.',10,COL['muted'])
 txt(1000,765,f'09 Sep 2026   |   {number:02d} / 10',10,COL['muted'])
 name=f'{number:02d}-diagram.svg'; (HERE/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'+''.join(sv)+'</svg>',encoding='utf8'); pages.append(name); P.showPage()

start('01  Arsitektur keseluruhan','Batas motherboard, modul sensor, antarmuka eksternal, serta jalur sinyal dan catu daya.')
box(40,135,250,140,'Masukan daya','J1: 24 V / 5VEXT / baterai\nUSB1 VBUS: jalur AON\nProteksi, buck, boost, mux','power')
box(365,135,365,140,'Distribusi & supervisi daya','+5V | VCC (3,3 V) | 3V3AON\nVBAT | +24V alarm\n+5VA: sumber belum terlihat','power')
box(815,135,345,140,'Beban eksternal & antarmuka','J2 alarm; CN3 RS485 A/B\nG$1 U.FL LoRa; USB1 serial\nSW1 konfigurasi; LED1','control')
line([(290,200),(365,200)],'power')
box(40,360,250,180,'Modul sensor eksternal','8 kanal analog\nI2C dan enable per kanal\nContoh modul: sensor,\nDAC, dan sakelar daya','signal',12)
box(370,345,350,110,'Akuisisi analog','Delapan masukan analog\nADC, referensi, dan VMID','signal')
box(370,505,350,115,'Kontrol sensor','Pemilih 8 cabang I2C\nEnable sensor per kanal\nSuhu dan kelembapan','bus')
box(825,360,335,220,'Kontrol utama','ESP32-S3\nSPI: ADC dan LoRa\nI2C: sensor dan kontrol\nUART: USB dan RS485\nGPIO: alarm, daya, tombol, LED','control')
line([(290,400),(370,400)],'signal','AIN0...7',300,380,dashed=True)
line([(370,565),(325,565),(325,510),(290,510)],'bus',dashed=True)
line([(720,400),(825,400)],'bus','SPI',751,380)
line([(825,545),(760,545),(760,565),(720,565)],'bus','I2C',760,586)
line([(548,275),(548,315),(910,315),(910,360)],'power','catu utama',660,292)
line([(1030,360),(1030,275)],'control')
box(40,660,1120,74,'Cara membaca','Cokelat: daya. Hijau: analog. Biru: bus digital. Ungu: kontrol/status. Garis putus: padanan fungsi antarmodul.\nDiagram menjelaskan koneksi desain arsip; bukan hasil pengukuran atau bukti fungsi firmware.','signal',12)
end()

start('02  Distribusi daya utama','Jalur 24 V, baterai, 5VEXT, pemilihan sumber, dan rail logika.')
box(40,145,195,110,'J1.6 / J1.5','24V+ / 24V-\nMasukan eksternal','power')
box(295,145,225,110,'Proteksi & filter','Sekering, TVS, dan filter','power')
box(585,145,230,110,'Buck 24 V -> 5 V','Regulator utama\nStatus ke GPIO47','power')
box(885,145,275,110,'5VBUCK','Masuk ke pemilih daya','power')
line([(235,200),(295,200)],'power'); line([(520,200),(585,200)],'power','+24V',528,174); line([(815,200),(885,200)],'power')
box(40,315,195,110,'Masukan baterai','Baterai / GND\nProteksi arus balik','power')
box(295,315,225,110,'Sakelar baterai','VBAT_IN -> VBAT\nDikendalikan ENA','power')
box(585,315,230,110,'Boost baterai -> 5 V','Sumber 5 V cadangan\nDikendalikan ENA','power')
box(885,315,275,110,'5VBOOST','Masuk ke pemilih daya\nJuga untuk alarm','power')
line([(235,370),(295,370)],'power','VBAT_IN',237,345); line([(520,370),(585,370)],'power','VBAT',532,345); line([(815,370),(885,370)],'power')
box(70,510,300,110,'Pemilih daya 5 V','Memilih 5VBUCK atau 5VBOOST\nStatus ke GPIO18','power',12)
box(445,510,260,110,'Rail +5V','Catu header sensor\ndan regulator logika','power',12)
box(805,510,355,110,'Logika 3,3 V','Mencatu ESP32, komunikasi,\ndan kontrol digital','power',12)
line([(995,255),(995,282),(25,282),(25,480),(140,480),(140,510)],'power','masukan utama',385,265)
line([(1000,425),(1000,495),(230,495),(230,510)],'power','masukan cadangan',600,474)
line([(370,565),(445,565)],'power'); line([(705,565),(805,565)],'power','+5V',739,543)
line([(575,695),(575,620)],'power')
box(410,660,330,72,'Masukan 5VEXT','Suplai tambahan rail +5V','power',12)
para(40,660,'+5VA dibahas pada halaman 05.\nUSB VBUS masuk AON (hal. 03).\nTidak ada IC charger pada desain ini.',335,12,COL['muted'])
para(795,660,'+24V juga menuju J2.1 alarm.\nAngka rail mengikuti label schematic.\nRating kerja belum diuji dari hardware.',355,12,COL['muted'])
end()

start('03  Always-on, watchdog, dan latch','3V3AON tetap dipisahkan dari VCC; ENA mengendalikan jalur baterai dan boost 5 V.')
box(40,140,260,110,'Sumber always-on','Baterai, buck, 5VEXT,\ndan VBUS USB digabungkan','power',12)
box(385,140,260,110,'Regulator always-on','Keluaran 3V3AON\nProteksi pada VBUS','power',12)
box(735,140,425,110,'Rail 3V3AON','Untuk watchdog, latch,\ndan supervisor daya','power',12)
line([(300,195),(385,195)],'power'); line([(645,195),(735,195)],'power')
box(40,330,260,130,'Watchdog','DONE dari GPIO17\nReset ESP32\nSinyal wake','control',12)
box(390,330,260,130,'Inverter wake','Mengubah WAKE ke PRE\nDipantau supervisor','control',12)
box(740,330,420,130,'Latch daya','PRE dan CLR mengatur ENA\nENA mengaktifkan baterai\ndan boost 5 V','control',12)
line([(300,390),(390,390)],'control','WAKE',321,368); line([(650,390),(740,390)],'control','PRE',672,368)
box(40,535,365,160,'ESP32 dan reset','GPIO17: DONE\nGPIO16: CLR\nReset bersama USB dan watchdog','control',12)
box(465,535,330,160,'Waktu watchdog','Jaringan resistor mengatur\nwaktu reset','control',12)
box(855,535,305,160,'Supervisi daya','Memantau 3V3AON\nENA mengendalikan\nbaterai dan boost','power',12)
end()

start('04  Modul sensor: jalur fungsional','Sumber terpisah: references/sensor-module-tps22919-h1-h8.png; gambar contoh bertuliskan MQ2.')
rect(40,135,1120,520,'#EAF2F2',COL['signal'],12); txt(60,152,'BATAS MODUL SENSOR REFERENSI - diagram fungsional, bukan pinout pemasangan langsung',12,COL['signal'],True)
box(65,205,260,100,'Masukan daya & enable','+5VIN / GND / EN\nSakelar +5VIN -> +5V','power',12)
box(410,205,295,100,'Filter catu modul','+5V -> +5VA lokal\nUntuk rangkaian analog','power',12)
box(800,205,330,100,'Distribusi lokal','+5V untuk heater sensor\n+5VA untuk rangkaian analog\nBerbeda dari net +5VA motherboard','power',12)
line([(325,255),(410,255)],'power'); line([(705,255),(800,255)],'power')
box(65,365,255,110,'I1 MQ2 (contoh)','Elemen sensor + jaringan R/C\nMasukan referensi VMID_REF\nDua input ke penguat','signal',12)
box(435,365,285,110,'Penguat analog','Input VIN+ / VIN-\nREF dari buffer','signal',12)
box(840,365,290,110,'ANOUT modul','Keluaran analog menuju\nAINn motherboard melalui\npadanan fungsi konektor','signal',12)
line([(320,420),(435,420)],'signal','VIN+ / VIN-',331,398); line([(720,420),(840,420)],'signal','ANOUT',747,398)
box(65,530,255,95,'DAC','I2C cabang terpilih\nAtur referensi','bus',12)
box(435,530,285,95,'Buffer referensi','Keluaran DAC -> REF','signal',12)
line([(320,575),(435,575)],'signal','VOUT DAC',335,553); line([(720,575),(770,575),(770,495),(580,495),(580,475)],'signal','REF',755,508)
box(40,669,1120,72,'Batas interpretasi','Nama MQ tiap kanal motherboard tidak tercantum. Pin konektor modul berbeda dari motherboard; lihat tabel halaman 06.','warn',12)
end()

start('05  Akuisisi analog dan tegangan referensi','Sinyal dari header disaring sebelum masuk ADC.')
box(40,140,250,115,'Header sensor','Delapan input analog\nVMID bersama','signal',12)
box(370,140,310,115,'Filter delapan kanal','Resistor seri dan\nkapasitor ke GND','signal',11)
box(790,140,370,115,'ADC 8 kanal','AI0...AI7 masuk ADC\nReferensi dan clock terpisah\nAVDD=+5VA; DVDD=VCC','signal',12)
line([(290,195),(370,195)],'signal','AINn',310,174); line([(680,195),(790,195)],'signal','AIn',722,174)
box(40,335,250,120,'Referensi tegangan','+5VA menghasilkan\ntegangan referensi','signal',12)
box(370,335,310,120,'Buffer referensi','Menstabilkan VREF\nuntuk ADC','signal',12)
box(790,335,370,120,'Kontrol ADC','SPI bersama\nCS, DRDY, reset, dan power-down','bus',12)
line([(290,395),(370,395)],'signal'); line([(680,395),(735,395),(735,285),(850,285),(850,255)],'signal','VREF',732,308)
box(40,535,300,145,'VMID motherboard','Pembagi dan buffer\nKe semua header sensor','signal',12)
box(405,535,340,145,'Clock dan kontrol','Clock 8 MHz\nPull-up power-down dan reset','bus',12)
box(805,535,355,145,'Sumber +5VA belum terlihat','Net +5VA hanya terhubung ke\nbeban analog dan decoupling.\nTidak ditemukan komponen/wire\npenghubung +5V ke +5VA\npada motherboard dalam arsip.','warn',12)
end()

start('06  I2C, enable, dan matriks header','Urutan fisik kanal analog, cabang multiplexer, dan bit enable harus dibaca terpisah.')
box(40,135,240,100,'ESP32 I2C','SDA GPIO8; SCL GPIO9','bus',12)
box(340,135,250,100,'Pemilih I2C','Memilih satu dari\ndelapan cabang sensor','bus',12)
box(650,135,245,100,'Ekspander enable','Delapan keluaran enable\nuntuk sensor','control',12)
box(955,135,205,100,'Suhu & kelembapan','Sensor pada bus I2C\nutama','bus',12)
line([(160,135),(160,122),(1055,122),(1055,135)],'bus',arrow=False); line([(465,122),(465,135)],'bus',arrow=False); line([(770,122),(770,135)],'bus',arrow=False)
headers=['Kanal','Header','Pin 3 analog','Pin 4 SCL','Pin 6 SDA','Pin 7 EN','PCF pin','TCA cabang']
rows=[]
for i,h in enumerate(['H2','H1','H3','H4','H5','H6','H7','H8']):
 p=C[h]['pins']; en=p['7']['net']; bit=int(en[2:]); pcfpin=str([4,5,6,7,9,10,11,12][bit])
 rows.append([str(i),h,p['3']['net'],p['4']['net'],p['6']['net'],en,pcfpin,str(7-i)])
table(40,275,1120,headers,rows,[100,105,165,150,150,150,130,170],rh=31,size=12)
txt(40,579,'Pin tetap semua header motherboard: 1=GND, 2=+5V, 5=GND, 8=VMID.',13,bold=True)
table(40,615,1120,['Fungsi','Catu +5V','GND','Analog','SCL','SDA','Enable','VMID'],[
 ['Pin motherboard','2','1 / 5','3','4','6','7','8'],
 ['Pin modul referensi','1','2 / 6','4','3','5','8','7']],widths=[245,140,130,130,110,110,125,130],rh=30,size=12)
txt(40,719,'Padanan konektor berdasarkan fungsi, bukan orientasi kabel. Alamat I2C tersedia pada lampiran CSV/JSON.',11,COL['warn'])
end()

start('07  Komunikasi dan akses pemrograman','Bus SPI bersama, radio LoRa, RS485, serta USB-to-UART dan auto boot/reset.')
box(40,145,275,140,'ESP32 | SPI','MOSI GPIO11; SCK GPIO12\nMISO GPIO13\nCS ADC GPIO38\nNSS LoRa GPIO14','bus',13)
box(420,145,365,140,'Radio LoRa','Reset, busy, dan DIO1\nRXEN / TXEN\nSPI bersama','bus',12)
box(885,145,275,140,'Antena LoRa','U.FL ke radio LoRa\nTerpisah dari antena ESP32','bus',12)
line([(315,210),(420,210)],'bus','SPI',350,188); line([(785,210),(885,210)],'signal','RF ANT',805,188)
box(40,355,275,120,'ESP32 | UART2','TX2 GPIO21\nRX2 GPIO20\nDIR GPIO19','bus',12)
box(420,355,365,120,'RS485','Transceiver dan proteksi A/B\nTerminasi/bias tidak terlihat','bus',12)
box(885,355,275,120,'CN3 | RS485','Pin 1 = B\nPin 2 = A\nKonektor XH-2A-black','bus',12)
line([(315,415),(420,415)],'bus'); line([(785,415),(885,415)],'bus','A / B',816,391)
box(40,545,275,155,'USB1','1=VBUS; 2=D-; 3=D+\n4=ID tidak tersambung; 5=GND\nD4/D5: proteksi jalur data\nVBUS hanya ke jalur AON\nmelalui D10, bukan ke +5V','bus',12)
box(420,545,365,155,'USB ke serial','USB data ke UART0 ESP32\nDTR / RTS untuk boot dan reset','bus',12)
box(885,545,275,155,'Boot / reset','IO0 dan RST\nReset juga dari watchdog','control',12)
line([(315,605),(420,605)],'bus','D+ / D-',330,581); line([(785,605),(885,605)],'control','Q1',823,581)
end()

start('08  Alarm, pengukuran baterai, dan status','Satu output ALARM pada GPIO40; suplai boost alarm dikendalikan terpisah oleh GPIO15.')
box(40,145,260,115,'VBAT','Sumber boost alarm\nDikendalikan latch daya','power',12)
box(390,145,365,115,'Boost -> 24 V','GPIO15 mengendalikan boost\nKeluaran menuju rail alarm','power',12)
box(865,145,295,115,'Rail +24V','Untuk output alarm\ndan masukan eksternal','power',12)
line([(300,200),(390,200)],'power'); line([(755,200),(865,200)],'power')
box(40,345,260,130,'GPIO40 ALARM','Satu sinyal alarm\nMengendalikan sakelar output','control',12)
box(390,345,365,130,'Sakelar alarm','Low-side switch ke GND\nUntuk beban eksternal','control',12)
box(865,345,295,130,'Output alarm','Pin 1: +24V\nPin 2: switched GND\nDioda flyback tersedia','power',12)
line([(300,405),(390,405)],'control'); line([(755,405),(865,405)],'control')
box(40,560,340,140,'Pemantauan baterai','Pembagi tegangan ke GPIO4\nNilai aktual perlu ukur','signal',12)
box(420,560,350,140,'Status daya','Status buck ke GPIO47\nStatus pemilih ke GPIO18','control',12)
box(810,560,350,140,'Antarmuka lokal','Tombol konfigurasi\nLED status\nSatu GPIO lokal tanpa beban','control',12)
end()

start('09  Peta lengkap pin ESP32','Nomor pad modul dipisahkan dari nama GPIO; kosong berarti tidak terhubung dalam arsip.')
pinrows=[]
for pin in sorted(C['U49']['pins'],key=int):
 v=C['U49']['pins'][pin]; net=v['net'] or 'Tidak terhubung'
 if net=='U49_7': net='Lokal / tanpa beban'
 pinrows.append([pin,v['name'],net])
table(40,145,540,['Pad','Pin ESP32','Net motherboard'],pinrows[:21],[65,160,315],rh=25,size=11)
table(620,145,540,['Pad','Pin ESP32','Net motherboard'],pinrows[21:],[65,160,315],rh=25,size=11)
txt(620,700,'Pad 36/37 memakai nama RXD0/TXD0 dari simbol.',12,COL['muted'])
txt(620,722,'Pad 16 IO46 dan IO3/35/36/37 tidak tersambung.',12,COL['muted'])
end()

start('10  Cakupan, sumber, dan catatan verifikasi','Diagram lengkap pada tingkat blok; detail seluruh komponen dan pin disertakan sebagai lampiran digital.')
box(40,140,1120,137,'Sumber yang diperiksa','Arsip utama: docs/wiring/gld-project-ver2-2026-07-01/source-GLD2.zip\nArsip di dalamnya: MotherBoardGLDVer1_6c18d214f6b6445f816f6824785b8234.zip\nIsi: 1-Schematic_MotherBoardGLDVer1.json (Sheet_1) + 1-PCB_PCB_MotherBoardGLDVer1.json\nGambar terpisah: references/sensor-module-tps22919-h1-h8.png\nNama internal MotherBoardGLDVer1 dipertahankan sebagai identitas file sumber, bukan penentuan versi produk.','bus',12)
txt(56,291,'SHA-256 arsip: '+DATA['sha256'],11,COL['muted'])
table(40,330,1120,['Area','Hasil pembacaan / batas bukti'],[
 ['Cakupan motherboard','1 sheet; 204 komponen/simbol, termasuk casing dan komponen pasif.'],
 ['Pemetaan net','Nama pin schematic dicocokkan dengan pad PCB; 0 perbedaan pada pin berlabel net.'],
 ['Sumber analog +5VA','Tidak ditemukan koneksi suplai ke +5VA motherboard; jangan disatukan secara asumsi.'],
 ['Modul sensor','Gambar referensi saja; pinout berbeda dari header motherboard. Perlu padanan koneksi.'],
 ['Identitas sensor','MQ2 tertulis pada gambar contoh. Penempatan jenis MQ tiap kanal tidak tercantum.'],
 ['Hardware / firmware','Tidak diuji, tidak di-flash, dan tidak dijadikan bukti hasil operasi oleh diagram ini.'],
 ['Komponen pasif','Dirangkum per fungsi; seluruh nilai, pin, dan net tersedia pada lampiran CSV/JSON.']
 ],[220,900],rh=34,size=12)
box(40,635,540,100,'Lampiran yang dapat diedit','01...10-diagram.svg: vector per halaman\nindex.html: penampil offline dengan zoom\nbuild_diagram.py: sumber generator PDF/SVG','signal',12)
box(620,635,540,100,'Lampiran jejak bukti','source-net-evidence.json: pin/net dan label schematic\ncomponent-pins.csv: seluruh komponen/pin motherboard\nREADME.md: cara pakai, regenerasi, dan batas cakupan','signal',12)
end(); P.save()

with (HERE/'component-pins.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f); w.writerow(['ref','value','sheet','pin','pin_name','pcb_net','schematic_labels'])
 for ref,c in C.items():
  if not c['pins']: w.writerow([ref,c['value'],c['sheet'],'','','',''])
  for pin,v in c['pins'].items(): w.writerow([ref,c['value'],c['sheet'],pin,v['name'],v['net'],' | '.join(v['schematic_labels'])])
viewer='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GLD2 - Diagram Blok</title><style>body{margin:0;background:#dfe7ed;color:#183044;font:15px Arial}header{position:sticky;top:0;background:#183044;color:white;padding:16px 24px;z-index:2;display:flex;gap:20px;align-items:center;flex-wrap:wrap}header a{color:#9ee6dd}main{padding:20px;overflow:auto}.page{width:1200px;max-width:none;margin:0 auto 24px;background:white;box-shadow:0 4px 16px #18304424}.page img{width:100%;display:block}select,button{padding:6px}input{vertical-align:middle}nav{display:flex;gap:12px}p{margin:0}@media print{header{display:none}.page{break-after:page;margin:0;width:100%;box-shadow:none}main{padding:0}}</style><header><b>GLD2 | Diagram Blok Schematic</b><select id="jump">'''
titles=['Arsitektur','Daya utama','AON & watchdog','Modul sensor','Akuisisi analog','I2C & header','Komunikasi','Alarm & status','Pin ESP32','Cakupan & bukti']
viewer+=''.join(f'<option value="p{i}">{i:02d} - {t}</option>' for i,t in enumerate(titles,1))
viewer+='''</select><label>Zoom <input id="zoom" type="range" min="60" max="180" value="100"> <span id="zval">100%</span></label><nav><a href="../../pdf/GLD2-Block-Diagram.pdf">PDF</a><a href="component-pins.csv">Seluruh pin (CSV)</a><a href="README.md">Panduan</a></nav></header><main>'''
viewer+=''.join(f'<section class="page" id="p{i}"><img src="{n}" alt="Diagram {i}: {esc(titles[i-1])}"></section>' for i,n in enumerate(pages,1))
viewer+='''</main><script>const z=document.querySelector('#zoom');z.oninput=()=>{document.querySelectorAll('.page').forEach(p=>p.style.width=(12*z.value)+'px');document.querySelector('#zval').textContent=z.value+'%'};document.querySelector('#jump').onchange=e=>document.getElementById(e.target.value).scrollIntoView({behavior:'smooth',block:'center'});</script></html>'''
(HERE/'index.html').write_text(viewer,encoding='utf8')
readme='''# GLD2 - Diagram blok dari schematic

Buka `index.html` untuk melihat 10 diagram dengan pilihan halaman dan zoom, atau `../../pdf/GLD2-Block-Diagram.pdf` untuk versi PDF vector.
SVG dapat diedit dengan Inkscape/Illustrator atau editor teks. Tata letak dan isi sumber ada di `build_diagram.py`.

## Sumber dan cakupan

- Satu lembar motherboard (Sheet_1), seluruh 204 komponen/simbol, dan net pad PCB dari ZIP yang diberikan pengguna.
- Gambar referensi modul sensor dibaca terpisah; designator komponen pada gambar modul tidak identik dengan motherboard.
- `source-net-evidence.json` menyimpan nama pin simbol, net pad PCB, koordinat pin schematic, dan label net hasil penelusuran wire. Nol perbedaan ditemukan pada pin yang mempunyai label net. Ini bukan electrical rules check penuh atau validasi routing PCB.
- `component-pins.csv` memuat setiap pin komponen termasuk komponen pasif. Baris casing tidak memiliki pin elektrik.
- Identitas sensor per kanal tidak diasumsikan dari firmware. Nama MQ2 hanya contoh yang tertulis pada gambar modul.
- +5VA motherboard tidak mempunyai sumber yang terlihat; +5VA lokal modul sensor mempunyai filter L1 dari +5V. Keduanya tidak digabung tanpa bukti.
- Pin modul referensi berbeda dari header motherboard. Tabel halaman 06 menunjukkan padanan fungsi, bukan instruksi memasang kabel tanpa pemeriksaan orientasi.
- Tidak ada perubahan firmware, build, upload, COM, atau pengukuran hardware.

## Regenerasi

Jalankan dengan Python yang mempunyai reportlab: `python output/diagrams/gld2/build_diagram.py` dari root repository. Font menggunakan Arial Windows.
Generator mengeluarkan PDF, 10 SVG, HTML, CSV, dan README. Input utamanya adalah `source-net-evidence.json` hasil ekstraksi sumber.

SHA-256 arsip sumber: `'''+DATA['sha256']+'`\n'
(HERE/'README.md').write_text(readme,encoding='utf8')
print('Created',PDF,'with',len(pages),'SVG pages')
