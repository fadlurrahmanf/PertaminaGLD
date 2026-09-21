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
COL={'ink':'#183044','muted':'#183044','line':'#CCD7DE','power':'#B86518','signal':'#147B75','bus':'#316FC0','control':'#8060AC','warn':'#AD4D35','bg':'#F4F7F9'}
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
def box(x,y,w,h,title,body='',kind='bus',size=13,title_size=15):
 rect(x,y,w,h,'white',COL['line']); rect(x,y,5,h,COL[kind],r=2)
 txt(x+16,y+14,title,title_size,bold=True)
 if body: para(x+16,y+40,body,w-30,size)
 return (x,y,w,h)
def line(points,kind='bus',label=None,lx=None,ly=None,dashed=False,arrow=True,label_size=11):
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
  tw=pdfmetrics.stringWidth(label,'Arial',label_size); rect(lx-3,ly-2,tw+6,label_size+5,'#F4F7F9',r=2); txt(lx,ly,label,label_size,color)
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
def start(title,subtitle,subtitle_size=13):
 global sv,number
 sv=[]; number+=1; rect(0,0,W,H,COL['bg'],r=0)
 txt(38,24,'PERTAMINA GLD   /   SCHEMATIC BLOCK DIAGRAM',11,COL['signal'],True)
 txt(38,51,title,28,bold=True); txt(38,91,subtitle,subtitle_size,COL['muted'])
def end():
 txt(1035,765,f'{number:02d} / 9',10,COL['muted'])
 name=f'{number:02d}-diagram.svg'; (HERE/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'+''.join(sv)+'</svg>',encoding='utf8'); pages.append(name); P.showPage()

start('01  Arsitektur keseluruhan','Catu daya, akuisisi sensor, kendali, dan komunikasi dalam satu perangkat.')
box(40,135,250,140,'Masukan daya','24 V eksternal\nBaterai\n5 V eksternal','power')
box(365,135,365,140,'Distribusi daya','+5 V | +5VA analog\n3,3 V | Always On\n+24 V untuk alarm','power')
box(815,135,345,140,'Antarmuka eksternal','Alarm\nRS485\nAntena LoRa\nPemrograman dan konfigurasi','control')
line([(290,200),(365,200)],'power')
box(40,360,250,180,'Modul sensor eksternal','8 channel analog\nI2C dan enable per channel\nContoh modul: sensor,\nDAC, dan sakelar daya','signal',12)
box(370,345,350,110,'Akuisisi analog','Delapan masukan analog\nADC, referensi, dan VMID\n(ADS1256)','signal')
box(370,505,350,115,'Kontrol sensor','Pemilih 8 cabang I2C\nEnable sensor per channel\nSuhu dan kelembapan\n(TCA9548A, PCF8574, SHT40)','bus')
box(825,360,335,220,'Kontrol utama','ESP32-S3\nSPI: ADC dan LoRa\nI2C: sensor dan kontrol\nUART: USB dan RS485\nGPIO: alarm, daya, tombol, LED\n(ESP32-S3-WROOM)','control')
line([(290,400),(370,400)],'signal','AIN0...7',300,380,dashed=True)
line([(370,565),(325,565),(325,510),(290,510)],'bus',dashed=True)
line([(720,400),(825,400)],'bus','SPI',751,380)
line([(825,545),(760,545),(760,565),(720,565)],'bus','I2C',760,586)
line([(548,275),(548,315),(910,315),(910,360)],'power','catu utama',660,292)
line([(1030,360),(1030,275)],'control')
box(40,660,1120,74,'Cara membaca','Cokelat: daya. Hijau: analog. Biru: komunikasi digital. Ungu: kendali dan status.\nGaris putus menunjukkan hubungan antarmodul sensor.','signal',12)
end()

start('02  Distribusi daya utama','Tiga masukan daya, pemilihan sumber 5 V, rail analog, dan catu sensor.')
rect(40,126,96,23,'#F3E9F8','#8060AC',4); txt(54,131,'MASUKAN',11,'#8060AC',True)
rect(910,126,96,23,'#F3E9F8','#8060AC',4); txt(924,131,'MASUKAN',11,'#8060AC',True)
rect(470,126,96,23,'#F3E9F8','#8060AC',4); txt(484,131,'MASUKAN',11,'#8060AC',True)
box(40,155,250,105,'Masukan 24 V','24 V eksternal','power',12)
box(40,320,250,105,'Proteksi & filter','Sekering, TVS, dan filter\nKeluaran: 24 V terlindungi','power',12)
box(40,485,250,105,'Buck 24 V -> 5 V','Keluaran: 5VBUCK\nSumber utama\n(LMR51450)','power',12)
box(910,155,250,105,'Masukan baterai','Baterai / GND','power',12)
box(910,320,250,105,'Sakelar baterai','Mengaktifkan VBAT','power',12)
box(910,485,250,105,'Boost baterai -> 5 V','Keluaran: 5VBOOST\nSumber cadangan\n(TPS61088)','power',12)
box(470,155,260,105,'Masukan 5VEXT','Suplai tambahan rail +5V','power',12)
box(470,485,260,110,'Pemilih daya 5 V','Memilih sumber utama\natau cadangan\n(TPS2116)','power',12)
box(470,645,260,90,'Rail +5V','Catu sistem','power',12)
box(120,645,250,90,'VCC (3.3V)','Catu ESP32 dan digital\n(TPS7A0233)','power',12)
box(830,645,250,90,'Catu modul sensor','Sakelar daya sensor\n(TPS22964)','power',12)
line([(165,260),(165,320)],'power','24 V',180,274)
line([(165,425),(165,485)],'power','24 V terlindungi',180,439)
line([(1035,260),(1035,320)],'power','baterai',1050,274)
line([(1035,425),(1035,485)],'power','VBAT',1050,439)
line([(600,260),(600,485)],'power','5VEXT',616,365)
line([(290,540),(430,540),(430,520),(470,520)],'power','sumber utama',305,518)
line([(910,540),(770,540),(770,555),(730,555)],'power','sumber cadangan',755,518)
line([(600,595),(600,645)],'power','+5V',616,610)
line([(470,690),(370,690)],'power','+5V',398,668)
line([(730,690),(830,690)],'power','+5V ke sensor',738,668)
para(40,755,'24 V terlindungi: keluaran setelah sekering, TVS, dan filter.',520,12,COL['muted'])
end()

start('03  Always On, watchdog, dan latch','Always On (AON) adalah rail daya yang tetap aktif untuk menjaga pengawasan dan pengendalian daya.')
box(40,140,260,110,'Sumber Always On','Baterai, buck, dan\nmasukan 5 V eksternal','power',12)
box(385,140,260,110,'Regulator Always On','Keluaran 3V3AON\nProteksi masukan\n(TPS62162)','power',12)
box(735,140,425,110,'Rail 3V3AON','Untuk watchdog, latch,\ndan supervisor daya','power',12)
line([(300,195),(385,195)],'power'); line([(645,195),(735,195)],'power')
box(40,330,260,130,'Watchdog','Sinyal DONE\nReset ESP32\nSinyal wake\n(TPL5010)','control',12)
box(390,330,260,130,'Inverter wake','Mengubah WAKE ke PRE\nDipantau supervisor\n(SN74LVC1G06)','control',12)
box(740,330,420,130,'Latch daya','PRE dan CLR mengatur ENA\nENA mengaktifkan baterai\ndan boost 5 V\n(SN74AUP1G74)','control',12)
line([(300,390),(390,390)],'control','WAKE',321,368); line([(650,390),(740,390)],'control','PRE',672,368)
box(40,535,365,160,'ESP32 dan reset','Sinyal DONE dan CLR\nReset dari watchdog','control',12)
box(465,535,330,160,'Waktu watchdog','Jaringan resistor mengatur\nwaktu reset','control',12)
box(855,535,305,160,'Supervisi daya','Memantau 3V3AON\nENA mengendalikan\nbaterai dan boost\n(TPS3839)','power',12)
end()

start('04  Modul sensor: jalur fungsional','Setiap modul menerima daya, I2C, enable, dan menyediakan satu keluaran analog.')
rect(40,135,1120,520,'#EAF2F2',COL['signal'],12); txt(60,152,'BATAS MODUL SENSOR REFERENSI - diagram fungsional, bukan pinout pemasangan langsung',12,COL['signal'],True)
box(65,205,260,100,'Masukan daya & enable','+5VIN / GND / EN\nSakelar +5VIN -> +5V','power',12)
box(410,205,295,100,'Filter catu modul','+5V -> +5VA lokal\nUntuk rangkaian analog','power',12)
box(800,205,330,100,'Distribusi lokal','+5V untuk heater sensor\n+5VA untuk rangkaian analog\nBerbeda dari net +5VA motherboard','power',12)
line([(325,255),(410,255)],'power'); line([(705,255),(800,255)],'power')
box(65,365,255,110,'Slot sensor 1 (contoh)','Elemen sensor + jaringan R/C\nMasukan referensi VMID_REF\nDua input ke penguat','signal',12)
box(435,365,285,110,'Penguat analog','Input VIN+ / VIN-\nREF dari buffer','signal',12)
box(840,365,290,110,'ANOUT modul','Ke satu channel ADS\nlalu dibaca ESP32','signal',12)
line([(320,420),(435,420)],'signal','VIN+ / VIN-',331,398); line([(720,420),(840,420)],'signal','ANOUT',747,398)
box(65,530,255,95,'DAC','I2C cabang terpilih\nAtur referensi','bus',12)
box(435,530,285,95,'Buffer referensi','Keluaran DAC -> REF','signal',12)
line([(320,575),(435,575)],'signal','VOUT DAC',335,553); line([(720,575),(770,575),(770,495),(580,495),(580,475)],'signal','REF',755,508)
box(40,669,1120,72,'Koneksi modul','Padanan koneksi dilakukan berdasarkan fungsi daya, analog, I2C, enable, dan referensi tegangan.','warn',12)
end()

start('05  Akuisisi analog dan tegangan referensi','Jalur analog memiliki filter catu terpisah, referensi tegangan, VMID, dan ADS 8 Channel.')
box(40,140,250,115,'Masukan sensor','Delapan sinyal analog\ndari modul sensor','signal',12)
box(370,140,310,115,'Filter sinyal','Resistor seri dan\nkapasitor ke GND','signal',11)
box(790,140,370,115,'ADS 8 Channel','Menerima 8 channel\nanalog secara bersamaan\n(ADS1256)','signal',12)
line([(290,195),(370,195)],'signal','sinyal analog',300,173); line([(680,195),(790,195)],'signal','sinyal terfilter',687,173)
box(40,335,250,120,'Rail +5V','Catu daya sistem','power',12)
box(370,335,310,120,'Filter analog +5VA','Ferrite dan kapasitor\nmemisahkan catu analog','power',12)
box(790,335,370,120,'Referensi ADC','Referensi stabil dan\nbuffer VREF\n(ADR03, OPA320)','signal',12)
line([(290,395),(370,395)],'power','+5V',305,373); line([(680,395),(790,395)],'power','+5VA',710,373)
line([(975,335),(975,285),(975,255)],'signal','VREF',995,290)
box(40,535,300,145,'VMID','Pembagi dan buffer\nuntuk referensi modul sensor','signal',12)
box(405,535,340,145,'Referensi modul sensor','Menerima VMID\nuntuk masing-masing modul','signal',12)
box(805,535,355,145,'Catu ADC','+5VA untuk analog\n3,3 V untuk digital','power',12)
line([(340,607),(405,607)],'signal','VMID',350,585)
line([(680,410),(745,410),(745,605),(805,605)],'power','+5VA',697,453)
line([(982,535),(1175,535),(1175,195),(1160,195)],'power','catu ADC',1092,515)
end()

start('06  I2C dan kendali sensor','I2C memilih cabang sensor, mengatur DAC, dan mengendalikan daya tiap modul.')
box(80,160,270,125,'ESP32','Bus I2C utama\nMengatur pembacaan dan kontrol\n(ESP32-S3-WROOM)','bus',12)
box(465,135,280,115,'Pemilih cabang I2C','Memilih satu dari\ndelapan modul sensor\n(TCA9548A)','bus',12)
box(865,135,230,115,'Modul sensor','DAC dan pembacaan\nanalog per modul','signal',12)
line([(350,220),(465,220)],'bus','I2C',390,198); line([(745,190),(865,190)],'bus','I2C cabang',768,168)
box(465,395,280,115,'Pengendali enable','Mengaktifkan atau\nmematikan tiap modul\n(PCF8574, TPS22964)','control',12)
line([(605,250),(605,395)],'control','kendali',625,305)
box(865,395,230,115,'Delapan modul','Enable per modul\nCatu dan sinyal analog','power',12)
line([(745,450),(865,450)],'control','8 x enable',766,428)
box(80,555,270,115,'Suhu & kelembapan','Terhubung langsung\npada bus I2C utama\n(SHT40)','bus',12)
line([(215,285),(215,555)],'bus','I2C',235,410)
box(430,600,680,70,'Fungsi utama','I2C dipakai untuk memilih sensor, mengatur referensi DAC, mengaktifkan modul, serta membaca suhu dan kelembapan.','signal',12)
end()

start('07  Komunikasi dan koneksi ESP32','Koneksi dikelompokkan menurut bus SPI, I2C, dan UART; kendali perangkat dipisahkan dari komunikasi.',14)
rect(40,130,700,180,'#EAF0F8',COL['bus'],12); txt(62,145,'SPI',14,COL['bus'],True)
box(80,180,220,75,'ADS 8 Channel','Akuisisi sinyal sensor\n(ADS1256)','signal',12,16)
box(430,180,220,75,'Radio LoRa','Komunikasi radio\n(E22-900MM22S)','bus',12,16)
box(835,180,280,75,'Antena LoRa','Antena eksternal','signal',13,16)
line([(650,218),(835,218)],'signal','RF',706,196,label_size=12)
line([(190,255),(190,275),(540,275),(540,255)],'bus','SPI bus',330,282,arrow=False,label_size=12)
box(450,340,300,145,'ESP32','Pengolah utama\nSPI | I2C | UART\nKendali dan status\n(ESP32-S3-WROOM)','control',14,16)
line([(600,340),(600,310)],'bus','SPI',618,318,label_size=12)
rect(40,535,520,180,'#EAF0F8',COL['bus'],12); txt(62,550,'I2C',14,COL['bus'],True)
box(65,585,140,80,'Multiplexer I2C','Untuk DAC\n(TCA9548A)','bus',11,16)
box(220,585,140,80,'Multiplexer GPIO','Power modul sensor\n(PCF8574)','control',11,16)
box(375,585,150,80,'Suhu & kelembapan','(SHT40)','signal',12,13)
line([(135,665),(135,682),(500,682),(500,665)],'bus','I2C bus',300,689,arrow=False,label_size=12)
line([(290,665),(290,682)],'bus',arrow=False)
line([(450,665),(450,682)],'bus',arrow=False)
rect(640,535,520,180,'#EAF0F8',COL['bus'],12); txt(662,550,'UART',14,COL['bus'],True)
box(670,585,200,80,'RS485','Ke perangkat eksternal\n(THVD1410)','bus',12,16)
box(910,575,210,90,'Pemrograman','USB ke serial\nBoot dan reset\n(CH340C)','control',12,16)
line([(770,665),(770,682),(1015,682),(1015,665)],'bus','UART bus',855,689,arrow=False,label_size=12)
line([(520,485),(520,535)],'bus','I2C',535,500,label_size=12)
line([(680,485),(680,535)],'bus','UART',695,500,label_size=12)
box(900,350,220,90,'Alarm dan daya','Kendali output alarm\ndan status daya','control',13,16)
line([(750,410),(900,395)],'control','kendali',798,373,label_size=12)
end()

start('08  Alarm, baterai, dan status daya','Rail +24 V alarm dapat berasal dari masukan 24 V eksternal atau boost baterai.')
box(40,145,260,115,'Masukan 24 V','24 V eksternal\nMasuk langsung ke rail +24 V','power',12)
box(40,315,260,115,'Baterai','Menyuplai boost alarm\nsaat daya baterai aktif','power',12)
box(390,315,260,115,'Boost -> 24 V','Menaikkan tegangan baterai\nke rail alarm\n(TPS61175)','power',12)
box(860,200,300,140,'Rail +24 V','Sumber: masukan eksternal\natau boost baterai\nUntuk output alarm','power',12)
line([(300,200),(860,200)],'power','24 V eksternal',520,178); line([(300,370),(390,370)],'power'); line([(650,370),(760,370),(760,300),(860,300)],'power','24 V boost',674,348)
box(40,545,260,110,'Perintah alarm','ESP32 mengendalikan\nsakelar alarm','control',12)
box(390,545,260,110,'Sakelar alarm','Menghubungkan beban\nke GND','control',12)
box(860,545,300,110,'Output alarm','+24 V dan switched GND\nDioda flyback tersedia','power',12)
line([(300,600),(390,600)],'control'); line([(650,600),(860,600)],'control')
box(40,670,340,65,'Pemantauan baterai','Pembagi tegangan ke ESP32','signal',12)
box(420,670,350,65,'Status daya','Status buck dan pemilih sumber','control',12)
box(810,670,350,65,'Antarmuka lokal','Tombol konfigurasi dan LED status','control',12)
end()

start('09  Alur energi, data, dan kendali','Daya mencatu perangkat; data sensor mengalir ke ESP32; ESP32 mengendalikan komunikasi dan keluaran.')
box(55,145,220,100,'Masukan daya','24 V, baterai,\ndan 5 V eksternal','power',12)
box(370,145,240,100,'Rail daya','+5 V, +5VA, VCC,\nAlways On, dan +24 V','power',12)
box(730,145,400,100,'Beban daya','ESP32, sensor, ADC,\nradio, dan output alarm','power',12)
line([(275,195),(370,195)],'power','mencatu',292,173); line([(610,195),(730,195)],'power','mencatu',640,173)
box(55,365,220,105,'Modul sensor','Sinyal analog\ndan referensi','signal',12)
box(370,365,240,105,'ADS 8 Channel','Mengubah sinyal\nmenjadi data digital\n(ADS1256)','signal',12)
box(730,340,230,155,'ESP32','Membaca data\nMengendalikan sistem\nMengirim komunikasi\n(ESP32-S3-WROOM)','control',13)
line([(275,418),(370,418)],'signal','sinyal analog',290,396); line([(610,418),(730,418)],'bus','SPI / data digital',620,396)
box(995,365,150,105,'LoRa & RS485','Data ke sistem\neksternal\n(E22, THVD1410)','bus',11)
line([(960,418),(995,418)],'bus','data',964,396)
box(265,600,260,90,'Kendali sensor','I2C: pilih sensor,\nDAC, dan enable','control',12)
box(675,600,260,90,'Alarm & status','Output alarm, status daya,\ntombol, dan LED','control',12)
line([(760,495),(395,600)],'control','kendali I2C',500,538); line([(850,495),(805,600)],'control','kendali',865,545)
end(); P.save()

with (HERE/'component-pins.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f); w.writerow(['ref','value','sheet','pin','pin_name','pcb_net','schematic_labels'])
 for ref,c in C.items():
  if not c['pins']: w.writerow([ref,c['value'],c['sheet'],'','','',''])
  for pin,v in c['pins'].items(): w.writerow([ref,c['value'],c['sheet'],pin,v['name'],v['net'],' | '.join(v['schematic_labels'])])
viewer='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GLD2 - Diagram Blok</title><style>body{margin:0;background:#dfe7ed;color:#183044;font:15px Arial}header{position:sticky;top:0;background:#183044;color:white;padding:16px 24px;z-index:2;display:flex;gap:20px;align-items:center;flex-wrap:wrap}header a{color:#9ee6dd}main{padding:20px;overflow:auto}.page{width:1200px;max-width:none;margin:0 auto 24px;background:white;box-shadow:0 4px 16px #18304424}.page img{width:100%;display:block}select,button{padding:6px}input{vertical-align:middle}nav{display:flex;gap:12px}p{margin:0}@media print{header{display:none}.page{break-after:page;margin:0;width:100%;box-shadow:none}main{padding:0}}</style><header><b>GLD2 | Diagram Blok Schematic</b><select id="jump">'''
titles=['Arsitektur','Daya utama','Always On','Modul sensor','Akuisisi analog','I2C & sensor','Koneksi ESP32','Alarm & status','Alur sistem']
viewer+=''.join(f'<option value="p{i}">{i:02d} - {t}</option>' for i,t in enumerate(titles,1))
viewer+='''</select><label>Zoom <input id="zoom" type="range" min="60" max="180" value="100"> <span id="zval">100%</span></label><nav><a href="../../pdf/GLD2-Block-Diagram.pdf">PDF</a><a href="component-pins.csv">Seluruh pin (CSV)</a><a href="README.md">Panduan</a></nav></header><main>'''
viewer+=''.join(f'<section class="page" id="p{i}"><img src="{n}" alt="Diagram {i}: {esc(titles[i-1])}"></section>' for i,n in enumerate(pages,1))
viewer+='''</main><script>const z=document.querySelector('#zoom');z.oninput=()=>{document.querySelectorAll('.page').forEach(p=>p.style.width=(12*z.value)+'px');document.querySelector('#zval').textContent=z.value+'%'};document.querySelector('#jump').onchange=e=>document.getElementById(e.target.value).scrollIntoView({behavior:'smooth',block:'center'});</script></html>'''
(HERE/'index.html').write_text(viewer,encoding='utf8')
readme='''# GLD2 - Diagram blok dari schematic

Buka `index.html` untuk melihat 9 diagram dengan pilihan halaman dan zoom, atau `../../pdf/GLD2-Block-Diagram.pdf` untuk versi PDF vector.
SVG dapat diedit dengan Inkscape/Illustrator atau editor teks. Tata letak dan isi sumber ada di `build_diagram.py`.

## Sumber dan cakupan

- Satu lembar motherboard (Sheet_1), seluruh 204 komponen/simbol, dan net pad PCB dari ZIP yang diberikan pengguna.
- Gambar referensi modul sensor dibaca terpisah; designator komponen pada gambar modul tidak identik dengan motherboard.
- `source-net-evidence.json` menyimpan nama pin simbol, net pad PCB, koordinat pin schematic, dan label net hasil penelusuran wire. Nol perbedaan ditemukan pada pin yang mempunyai label net. Ini bukan electrical rules check penuh atau validasi routing PCB.
- `component-pins.csv` memuat setiap pin komponen termasuk komponen pasif. Baris casing tidak memiliki pin elektrik.
- Identitas sensor per channel tidak diasumsikan dari firmware. Nama MQ2 hanya contoh yang tertulis pada gambar modul.
- +5VA motherboard tidak mempunyai sumber yang terlihat; +5VA lokal modul sensor mempunyai filter L1 dari +5V. Keduanya tidak digabung tanpa bukti.
- Pin modul referensi berbeda dari header motherboard. Tabel halaman 06 menunjukkan padanan fungsi, bukan instruksi memasang kabel tanpa pemeriksaan orientasi.
- Tidak ada perubahan firmware, build, upload, COM, atau pengukuran hardware.

## Regenerasi

Jalankan dengan Python yang mempunyai reportlab: `python output/diagrams/gld2/build_diagram.py` dari root repository. Font menggunakan Arial Windows.
Generator mengeluarkan PDF, 9 SVG, HTML, CSV, dan README. Input utamanya adalah `source-net-evidence.json` hasil ekstraksi sumber.

SHA-256 arsip sumber: `'''+DATA['sha256']+'`\n'
(HERE/'README.md').write_text(readme,encoding='utf8')
print('Created',PDF,'with',len(pages),'SVG pages')
