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
P=canvas.Canvas(str(PDF),pagesize=(W,H)); P.setTitle('GLD2 | Schematic Block Diagram'); P.setAuthor('PertaminaGLD')
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

start('01  System architecture','Power, sensor acquisition, control, and communications in one device.')
box(40,135,250,140,'Power inputs','External 24 V\nBattery\nExternal 5 V','power')
box(365,135,365,140,'Power distribution','+5 V | Analog +5VA\n3.3 V | Always On\n+24 V for alarm','power')
box(815,135,345,140,'External interfaces','Alarm\nRS485\nLoRa antenna\nProgramming and configuration','control')
line([(290,200),(365,200)],'power')
box(40,360,250,180,'External sensor modules','8 analog channels\nI2C and enable per channel\nExample modules: sensor,\nDAC, and power switch','signal',12)
box(370,345,350,110,'Analog acquisition','Eight analog inputs\nADC, reference, and VMID\n(ADS1256)','signal')
box(370,505,350,115,'Sensor control','8-branch I2C selector\nSensor enable per channel\nTemperature and humidity\n(TCA9548A, PCF8574, SHT40)','bus')
box(825,360,335,220,'Main control','ESP32-S3\nSPI: ADC and LoRa\nI2C: sensors and control\nUART: USB and RS485\nGPIO: alarm, power, button, LED\n(ESP32-S3-WROOM)','control')
line([(290,400),(370,400)],'signal','AIN0...7',300,380,dashed=True)
line([(370,565),(325,565),(325,510),(290,510)],'bus',dashed=True)
line([(720,400),(825,400)],'bus','SPI',751,380)
line([(825,545),(760,545),(760,565),(720,565)],'bus','I2C',760,586)
line([(548,275),(548,315),(910,315),(910,360)],'power','main supply',660,292)
line([(1030,360),(1030,275)],'control')
box(40,660,1120,74,'How to read','Brown: power. Green: analog. Blue: digital communication. Purple: control and status.\nDashed lines show interconnection between sensor modules.','signal',12)
end()

start('02  Main power distribution','Three power inputs, 5 V source selection, analog rail, and sensor supply.')
rect(40,126,96,23,'#F3E9F8','#8060AC',4); txt(54,131,'INPUT',11,'#8060AC',True)
rect(910,126,96,23,'#F3E9F8','#8060AC',4); txt(924,131,'INPUT',11,'#8060AC',True)
rect(470,126,96,23,'#F3E9F8','#8060AC',4); txt(484,131,'INPUT',11,'#8060AC',True)
box(40,155,250,105,'24 V input','External 24 V','power',12)
box(40,320,250,105,'Protection and filter','Fuse, TVS, and filter\nOutput: protected 24 V','power',12)
box(40,485,250,105,'24 V to 5 V buck','Output: 5VBUCK\nPrimary source\n(LMR51450)','power',12)
box(910,155,250,105,'Battery input','Battery / GND','power',12)
box(910,320,250,105,'Battery switch','Enables VBAT','power',12)
box(910,485,250,105,'Battery boost to 5 V','Output: 5VBOOST\nBackup source\n(TPS61088)','power',12)
box(470,155,260,105,'5VEXT input','Additional +5V rail supply','power',12)
box(470,485,260,110,'5 V power selector','Selects primary\nor backup source\n(TPS2116)','power',12)
box(470,645,260,90,'+5V rail','System supply','power',12)
box(120,645,250,90,'VCC (3.3V)','ESP32 and digital supply\n(TPS7A0233)','power',12)
box(830,645,250,90,'Sensor module supply','Sensor power switch\n(TPS22964)','power',12)
line([(165,260),(165,320)],'power','24 V',180,274)
line([(165,425),(165,485)],'power','protected 24 V',180,439)
line([(1035,260),(1035,320)],'power','battery',1050,274)
line([(1035,425),(1035,485)],'power','VBAT',1050,439)
line([(600,260),(600,485)],'power','5VEXT',616,365)
line([(290,540),(430,540),(430,520),(470,520)],'power','primary source',305,518)
line([(910,540),(770,540),(770,555),(730,555)],'power','backup source',755,518)
line([(600,595),(600,645)],'power','+5V',616,610)
line([(470,690),(370,690)],'power','+5V',398,668)
line([(730,690),(830,690)],'power','+5V to sensors',738,668)
para(40,755,'Protected 24 V: output after the fuse, TVS, and filter.',520,12,COL['muted'])
end()

start('03  Always On, watchdog, and latch','Always On (AON) is a continuously active power rail for supervision and power control.')
box(40,140,260,110,'Always On sources','Battery, buck, and\nexternal 5 V input','power',12)
box(385,140,260,110,'Always On regulator','3V3AON output\nInput protection\n(TPS62162)','power',12)
box(735,140,425,110,'3V3AON rail','For watchdog, latch,\nand power supervisor','power',12)
line([(300,195),(385,195)],'power'); line([(645,195),(735,195)],'power')
box(40,330,260,130,'Watchdog','DONE signal\nESP32 reset\nWake signal\n(TPL5010)','control',12)
box(390,330,260,130,'Wake inverter','Converts WAKE to PRE\nMonitored by supervisor\n(SN74LVC1G06)','control',12)
box(740,330,420,130,'Power latch','PRE and CLR control ENA\nENA enables the battery\nand 5 V boost\n(SN74AUP1G74)','control',12)
line([(300,390),(390,390)],'control','WAKE',321,368); line([(650,390),(740,390)],'control','PRE',672,368)
box(40,535,365,160,'ESP32 and reset','DONE and CLR signals\nReset from watchdog','control',12)
box(465,535,330,160,'Watchdog timing','Resistor network sets\nthe reset interval','control',12)
box(855,535,305,160,'Power supervision','Monitors 3V3AON\nENA controls the\nbattery and boost\n(TPS3839)','power',12)
end()

start('04  Sensor module: functional path','Each module receives power, I2C, enable, and provides one analog output.')
rect(40,135,1120,520,'#EAF2F2',COL['signal'],12); txt(60,152,'REFERENCE SENSOR MODULE BOUNDARY - functional diagram, not a direct installation pinout',12,COL['signal'],True)
box(65,205,260,100,'Power input and enable','+5VIN / GND / EN\n+5VIN switch -> +5V','power',12)
box(410,205,295,100,'Module power filter','+5V -> local +5VA\nFor analog circuitry','power',12)
box(800,205,330,100,'Local distribution','+5V for sensor heater\n+5VA for analog circuitry\nSeparate from motherboard +5VA net','power',12)
line([(325,255),(410,255)],'power'); line([(705,255),(800,255)],'power')
box(65,365,255,110,'Sensor slot 1 (example)','Sensor element + R/C network\nVMID_REF reference input\nTwo inputs to amplifier','signal',12)
box(435,365,285,110,'Analog amplifier','VIN+ / VIN- inputs\nREF from buffer','signal',12)
box(840,365,290,110,'Module ANOUT','To one ADS channel\nthen read by ESP32','signal',12)
line([(320,420),(435,420)],'signal','VIN+ / VIN-',331,398); line([(720,420),(840,420)],'signal','ANOUT',747,398)
box(65,530,255,95,'DAC','Selected I2C branch\nSets reference','bus',12)
box(435,530,285,95,'Reference buffer','DAC output -> REF','signal',12)
line([(320,575),(435,575)],'signal','DAC VOUT',335,553); line([(720,575),(770,575),(770,495),(580,495),(580,475)],'signal','REF',755,508)
box(40,669,1120,72,'Module connections','Connections are mapped by power, analog, I2C, enable, and voltage-reference functions.','warn',12)
end()

start('05  Analog acquisition and voltage reference','The analog path has a separate supply filter, voltage reference, VMID, and ADS 8 Channel.')
box(40,140,250,115,'Sensor inputs','Eight analog signals\nfrom sensor modules','signal',12)
box(370,140,310,115,'Signal filter','Series resistor and\ncapacitor to GND','signal',11)
box(790,140,370,115,'ADS 8 Channel','Receives 8 analog\nchannels simultaneously\n(ADS1256)','signal',12)
line([(290,195),(370,195)],'signal','analog signal',300,173); line([(680,195),(790,195)],'signal','filtered signal',687,173)
box(40,335,250,120,'+5V rail','System power supply','power',12)
box(370,335,310,120,'Analog +5VA filter','Ferrite and capacitors\nisolate analog supply','power',12)
box(790,335,370,120,'ADC reference','Stable reference and\nVREF buffer\n(ADR03, OPA320)','signal',12)
line([(290,395),(370,395)],'power','+5V',305,373); line([(680,395),(790,395)],'power','+5VA',710,373)
line([(975,335),(975,285),(975,255)],'signal','VREF',995,290)
box(40,535,300,145,'VMID','Divider and buffer\nfor sensor module reference','signal',12)
box(405,535,340,145,'Sensor module reference','Receives VMID\nfor each module','signal',12)
box(805,535,355,145,'ADC supply','+5VA for analog\n3.3 V for digital','power',12)
line([(340,607),(405,607)],'signal','VMID',350,585)
line([(680,410),(745,410),(745,605),(805,605)],'power','+5VA',697,453)
line([(982,535),(1175,535),(1175,195),(1160,195)],'power','ADC supply',1092,515)
end()

start('06  I2C and sensor control','I2C selects sensor branches, sets the DAC, and controls each module power supply.')
box(80,160,270,125,'ESP32','Main I2C bus\nControls acquisition and control\n(ESP32-S3-WROOM)','bus',12)
box(465,135,280,115,'I2C branch selector','Selects one of\neight sensor modules\n(TCA9548A)','bus',12)
box(865,135,230,115,'Sensor module','DAC and analog\nacquisition per module','signal',12)
line([(350,220),(465,220)],'bus','I2C',390,198); line([(745,190),(865,190)],'bus','I2C branch',768,168)
box(465,395,280,115,'Enable controller','Enables or disables\neach module\n(PCF8574, TPS22964)','control',12)
line([(605,250),(605,395)],'control','control',625,305)
box(865,395,230,115,'Eight modules','Enable per module\nPower and analog signals','power',12)
line([(745,450),(865,450)],'control','8 x enable',766,428)
box(80,555,270,115,'Temperature and humidity','Connected directly\nto the main I2C bus\n(SHT40)','bus',12)
line([(215,285),(215,555)],'bus','I2C',235,410)
box(430,600,680,70,'Main function','I2C selects sensors, sets the DAC reference, enables modules, and reads temperature and humidity.','signal',12)
end()

start('07  ESP32 communications and connections','Connections are grouped by SPI, I2C, and UART buses; device control is separate from communications.',14)
rect(40,130,700,180,'#EAF0F8',COL['bus'],12); txt(62,145,'SPI',14,COL['bus'],True)
box(80,180,220,75,'ADS 8 Channel','Sensor signal acquisition\n(ADS1256)','signal',12,16)
box(430,180,220,75,'LoRa radio','Radio communication\n(E22-900MM22S)','bus',12,16)
box(835,180,280,75,'LoRa antenna','External antenna','signal',13,16)
line([(650,218),(835,218)],'signal','RF',706,196,label_size=12)
line([(190,255),(190,275),(540,275),(540,255)],'bus','SPI bus',330,282,arrow=False,label_size=12)
box(450,340,300,145,'ESP32','Main processor\nSPI | I2C | UART\nControl and status\n(ESP32-S3-WROOM)','control',14,16)
line([(600,340),(600,310)],'bus','SPI',618,318,label_size=12)
rect(40,535,520,180,'#EAF0F8',COL['bus'],12); txt(62,550,'I2C',14,COL['bus'],True)
box(65,585,140,80,'I2C multiplexer','For DAC\n(TCA9548A)','bus',11,16)
box(220,585,140,80,'GPIO multiplexer','Sensor module power\n(PCF8574)','control',11,16)
box(375,585,150,80,'Temperature / humidity','(SHT40)','signal',12,13)
line([(135,665),(135,682),(500,682),(500,665)],'bus','I2C bus',300,689,arrow=False,label_size=12)
line([(290,665),(290,682)],'bus',arrow=False)
line([(450,665),(450,682)],'bus',arrow=False)
rect(640,535,520,180,'#EAF0F8',COL['bus'],12); txt(662,550,'UART',14,COL['bus'],True)
box(670,585,200,80,'RS485','To external devices\n(THVD1410)','bus',12,16)
box(910,575,210,90,'Programming','USB to serial\nBoot and reset\n(CH340C)','control',12,16)
line([(770,665),(770,682),(1015,682),(1015,665)],'bus','UART bus',855,689,arrow=False,label_size=12)
line([(520,485),(520,535)],'bus','I2C',535,500,label_size=12)
line([(680,485),(680,535)],'bus','UART',695,500,label_size=12)
box(900,350,220,90,'Alarm and power','Alarm output control\nand power status','control',13,16)
line([(750,410),(900,395)],'control','control',798,373,label_size=12)
end()

start('08  Alarm, battery, and power status','The +24 V alarm rail can be supplied by external 24 V input or battery boost.')
box(40,145,260,115,'24 V input','External 24 V\nFeeds the +24 V rail directly','power',12)
box(40,315,260,115,'Battery','Supplies alarm boost\nwhen battery power is active','power',12)
box(390,315,260,115,'Boost to 24 V','Raises battery voltage\nto the alarm rail\n(TPS61175)','power',12)
box(860,200,300,140,'+24 V rail','Source: external input\nor battery boost\nFor alarm output','power',12)
line([(300,200),(860,200)],'power','external 24 V',520,178); line([(300,370),(390,370)],'power'); line([(650,370),(760,370),(760,300),(860,300)],'power','boost 24 V',674,348)
box(40,545,260,110,'Alarm command','ESP32 controls the\nalarm switch','control',12)
box(390,545,260,110,'Alarm switch','Connects the load\nto GND','control',12)
box(860,545,300,110,'Alarm output','+24 V and switched GND\nFlyback diode provided','power',12)
line([(300,600),(390,600)],'control'); line([(650,600),(860,600)],'control')
box(40,670,340,65,'Battery monitoring','Voltage divider to ESP32','signal',12)
box(420,670,350,65,'Power status','Buck and source-selector status','control',12)
box(810,670,350,65,'Local interface','Configuration button and status LED','control',12)
end()

start('09  Energy, data, and control flow','Power supplies devices; sensor data flows to the ESP32; the ESP32 controls communications and outputs.')
box(55,145,220,100,'Power inputs','24 V, battery,\nand external 5 V','power',12)
box(370,145,240,100,'Power rails','+5 V, +5VA, VCC,\nAlways On, and +24 V','power',12)
box(730,145,400,100,'Power loads','ESP32, sensors, ADC,\nradio, and alarm output','power',12)
line([(275,195),(370,195)],'power','supplies',292,173); line([(610,195),(730,195)],'power','supplies',640,173)
box(55,365,220,105,'Sensor modules','Analog signals\nand reference','signal',12)
box(370,365,240,105,'ADS 8 Channel','Converts signals\nto digital data\n(ADS1256)','signal',12)
box(730,340,230,155,'ESP32','Reads data\nControls the system\nSends communications\n(ESP32-S3-WROOM)','control',13)
line([(275,418),(370,418)],'signal','analog signal',290,396); line([(610,418),(730,418)],'bus','SPI / digital data',620,396)
box(995,365,150,105,'LoRa and RS485','Data to external\nsystems\n(E22, THVD1410)','bus',11)
line([(960,418),(995,418)],'bus','data',964,396)
box(265,600,260,90,'Sensor control','I2C: select sensor,\nDAC, and enable','control',12)
box(675,600,260,90,'Alarm and status','Alarm output, power status,\nbutton, and LED','control',12)
line([(760,495),(395,600)],'control','I2C control',500,538); line([(850,495),(805,600)],'control','control',865,545)
end(); P.save()

with (HERE/'component-pins.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f); w.writerow(['ref','value','sheet','pin','pin_name','pcb_net','schematic_labels'])
 for ref,c in C.items():
  if not c['pins']: w.writerow([ref,c['value'],c['sheet'],'','','',''])
  for pin,v in c['pins'].items(): w.writerow([ref,c['value'],c['sheet'],pin,v['name'],v['net'],' | '.join(v['schematic_labels'])])
viewer='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GLD2 - Block Diagram</title><style>body{margin:0;background:#dfe7ed;color:#183044;font:15px Arial}header{position:sticky;top:0;background:#183044;color:white;padding:16px 24px;z-index:2;display:flex;gap:20px;align-items:center;flex-wrap:wrap}header a{color:#9ee6dd}main{padding:20px;overflow:auto}.page{width:1200px;max-width:none;margin:0 auto 24px;background:white;box-shadow:0 4px 16px #18304424}.page img{width:100%;display:block}select,button{padding:6px}input{vertical-align:middle}nav{display:flex;gap:12px}p{margin:0}@media print{header{display:none}.page{break-after:page;margin:0;width:100%;box-shadow:none}main{padding:0}}</style><header><b>GLD2 | Schematic Block Diagram</b><select id="jump">'''
titles=['Architecture','Main power','Always On','Sensor module','Analog acquisition','I2C and sensors','ESP32 connections','Alarm and status','System flow']
viewer+=''.join(f'<option value="p{i}">{i:02d} - {t}</option>' for i,t in enumerate(titles,1))
viewer+='''</select><label>Zoom <input id="zoom" type="range" min="60" max="180" value="100"> <span id="zval">100%</span></label><nav><a href="../../pdf/GLD2-Block-Diagram.pdf">PDF</a><a href="component-pins.csv">All pins (CSV)</a><a href="README.md">Guide</a></nav></header><main>'''
viewer+=''.join(f'<section class="page" id="p{i}"><img src="{n}" alt="Diagram {i}: {esc(titles[i-1])}"></section>' for i,n in enumerate(pages,1))
viewer+='''</main><script>const z=document.querySelector('#zoom');z.oninput=()=>{document.querySelectorAll('.page').forEach(p=>p.style.width=(12*z.value)+'px');document.querySelector('#zval').textContent=z.value+'%'};document.querySelector('#jump').onchange=e=>document.getElementById(e.target.value).scrollIntoView({behavior:'smooth',block:'center'});</script></html>'''
(HERE/'index.html').write_text(viewer,encoding='utf8')
readme='''# GLD2 - schematic block diagram

Open `index.html` to view the nine diagrams with page selection and zoom, or open `../../pdf/GLD2-Block-Diagram.pdf` for the vector PDF.
The SVG files can be edited with Inkscape, Illustrator, or a text editor. The layout and source content are in `build_diagram.py`.

## Source and scope

- One motherboard sheet (Sheet_1), all 204 component/symbol records, and PCB pad nets from the user-provided ZIP.
- The sensor-module reference image was read separately; its component designators do not match the motherboard.
- `source-net-evidence.json` stores symbol pin names, PCB pad nets, schematic pin coordinates, and traced net labels. No differences were found for pins with a net label. This is not a complete electrical-rules check or PCB-routing validation.
- `component-pins.csv` lists every component pin, including passive components. Case-only rows have no electrical pins.
- Sensor identity per channel is not inferred from firmware. MQ2 is only an example written on the module image.
- The motherboard +5VA source is not visible; local sensor-module +5VA has an L1 filter from +5V. They are not combined without evidence.
- Reference-module pins differ from the motherboard header. Page 06 presents functional mapping, not a wiring instruction without orientation verification.
- No firmware, build, upload, COM, or hardware measurements were changed.

## Regeneration

Run with Python and reportlab from the repository root: `python output/diagrams/gld2/build_diagram.py`. The font is Windows Arial.
The generator outputs the PDF, nine SVG files, HTML, CSV, and README. Its primary input is the extracted `source-net-evidence.json`.

SHA-256 arsip sumber: `'''+DATA['sha256']+'`\n'
(HERE/'README.md').write_text(readme,encoding='utf8')
print('Created',PDF,'with',len(pages),'SVG pages')
