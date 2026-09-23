"""Diagram and calculation pages. Executed in the builder drawing context."""

def tag(x,y,words,size=11):
 for i,s in enumerate(words.split('\n')):
  yy=y+i*(size+4)
  width=pdfmetrics.stringWidth(s,'Arial',size)
  rect(x-3,yy-2,width+6,size+4,COL['bg'],r=2)
  txt(x,yy,s,size)

def power(points,label,x,y,size=11):
 assert 'V' in label and ('A' in label or 'Current' in label),label
 line(points,'power')
 tag(x,y,label,size)

def note(title,body,y=666):
 box(40,y,1120,76,title,body,'warn',12)

def section(title,subtitle): start(title,subtitle)

section('01  System architecture','Power, acquisition, control, and communications. Power values are calculated reference cases; see pages 10–17.')
box(40,145,240,130,'Power inputs','External 24 V\nBattery 4.2 V\nExternal 5 V','power')
box(445,145,280,130,'Power distribution','+5V / +5VA\nVCC / Always On\nAlarm supply','power')
box(880,145,280,130,'External interfaces','Alarm | RS485\nLoRa antenna\nUSB programming','control')
power([(280,210),(445,210)],'24 / 4,2 / 5 V\nCurrent not determined',300,167)
box(40,385,250,145,'Eight MQ modules','Analog output per module\nI2C and enable','signal')
box(420,345,295,110,'Analog acquisition','ADS1256\nReference and VMID','signal')
box(420,525,295,105,'Sensor control','TCA9548A | PCF8574\nSHT40','bus')
box(865,365,295,240,'Main control','ESP32-S3-WROOM\nSPI: ADS and LoRa\nI2C: sensor control\nUART: USB and RS485\nGPIO: alarm and power','control')
line([(290,415),(420,415)],'signal','AIN0...7',313,394)
line([(420,578),(335,578),(335,500),(290,500)],'bus','I2C / EN',339,545)
line([(715,405),(865,405)],'bus','SPI',775,382)
line([(865,555),(785,555),(785,578),(715,578)],'bus','I2C',792,585)
power([(585,275),(585,305),(950,305),(950,365)],'3,3 V 0,0917 A*',741,283)
line([(1055,365),(1055,275)],'control','interface signals',1065,310)
note('Reading the power labels','Brown = power. * = stated reference case, not a measured total. Approximate voltages include source/path variation.\nUnknown current is written in plain words. Calculation symbols and conditions are kept in the appendix.')
end()

section('02  Main power distribution','24 V at left, battery at right, source selector at centre. The external 5 V diode bypasses the selector.')
for x in (40,470,920):
 rect(x,128,85,22,'#F3E9F8',COL['control'],4); txt(x+12,133,'INPUT',11,COL['control'],True)
box(40,160,240,80,'24 V input','External supply','power',12)
box(40,300,240,80,'Protection and filter','Fuse, TVS and input filter','power',12)
box(40,440,240,90,'Buck converter','LMR51450\nPrimary source','power',12)
box(920,160,240,80,'Battery input','4.2 V reference point','power',12)
box(920,300,240,80,'Battery switch','TPS22964C','power',12)
box(920,440,240,90,'Battery boost','TPS61088\nBackup source','power',12)
box(470,160,260,80,'5VEXT input','External 5 V','power',12)
box(470,300,260,80,'Bypass diode','SS54 → +5V','power',12)
box(470,440,260,90,'5 V power selector','TPS2116','power',12)
box(470,635,260,100,'+5V distribution','To analog filter and I2C mux\nSensor headers and VCC','power',12)
box(40,635,260,100,'VCC (3.3V)','TPS62162\nDigital supply','power',12)
box(900,635,260,100,'Eight sensor modules','5 V reference heater model:\n1.315 A + module circuitry','power',12)
power([(160,240),(160,300)],'24 V\nCurrent not determined',176,253)
power([(160,380),(160,440)],'≈24 V\nCurrent not determined',176,393)
power([(1040,240),(1040,300)],'4,2 V\nCurrent not determined',865,253)
power([(1040,380),(1040,440)],'≈4,2 V\nCurrent not determined',865,393)
power([(600,240),(600,300)],'5 V\nCurrent not determined',615,253)
power([(280,475),(470,475)],'4,99 V\nCurrent not determined',300,432)
power([(730,340),(810,340),(810,587),(600,587)],'≈5 V\nCurrent not determined',645,390)
power([(920,500),(730,500)],'5,27 V*\nCurrent not determined',825,535,10)
power([(600,530),(600,635)],'≈5 V\nCurrent not determined',615,599)
power([(470,682),(300,682)],'≈5 V\nCurrent not determined',318,644)
power([(730,682),(900,682)],'5 V 1,315 A*\nHeaters only',755,644)
tag(40,553,'Protected 24 V also supplies the alarm.\nThe shared bus can receive battery boost (page 08).',11)
tag(40,749,'*Boost: 5,27 V PWM / 5,30 V PFM before path losses. Heater current: reference case at exactly 5 V; module ICs are additional.',11)
end()

section('03  Always On, watchdog, and latch','Purpose: retain supervision and wake control while the main switched circuitry is disabled.')
box(40,150,255,110,'Always On sources','Battery | buck | 5VEXT\nDiode OR','power',12)
box(455,150,260,110,'Always On regulator','TPS7A0233\n3.3 V output','power',12)
box(875,150,285,110,'3V3AON','Watchdog, latch, inverter\nand supervisor','power',12)
power([(295,205),(455,205)],'≈4,2 / 5 V\nCurrent not determined',310,164)
power([(715,205),(875,205)],'3,3 V\nCurrent not determined',730,164)
box(40,355,255,115,'Watchdog','TPL5010\nWake and reset timing','control',12)
box(455,355,260,115,'Wake inverter','SN74LVC1G06\nWAKE → PRE','control',12)
box(875,355,285,115,'Power latch','SN74AUP1G74\nControls ENA','control',12)
line([(295,410),(455,410)],'control','WAKE',352,387)
line([(715,410),(875,410)],'control','PRE',785,387)
power([(1020,260),(1020,310),(170,310),(170,355)],'3,3 V - Current not determined',502,283)
tag(185,327,'3,3 V 35 nA*',10)
line([(585,310),(585,355)],'power',arrow=False)
tag(596,319,'3,3 V ≤10 µA*',10)
line([(1020,310),(1020,355)],'power',arrow=False)
tag(1032,319,'3,3 V ≤0,5 µA*',10)
box(40,565,255,90,'ESP32','DONE / CLR / reset','control',12)
box(455,565,260,90,'Power supervisor','TPS3839\nMonitors 3V3AON','control',12)
box(875,565,285,90,'Battery and boost','ENA enables main power','power',12)
line([(170,565),(170,470)],'control','DONE / reset',185,501)
line([(715,610),(790,610),(790,450),(875,450)],'control','PRE / reset',800,547)
line([(1020,470),(1020,565)],'control','ENA',1037,512)
line([(295,625),(390,625),(390,515),(920,515),(920,470)],'control','CLR',399,494)
power([(740,310),(740,535),(585,535),(585,565)],'3,3 V 150 nA*',590,538,10)
note('AON budget','*Static, unloaded reference cases; conditions on page 13. Total current also includes pull-ups, switching activity and regulator losses.')
end()

section('04  Sensor module: functional path','One example of eight modules. Local analog supply is separate from the motherboard analog supply.')
rect(40,133,1120,514,'#EAF2F2',COL['signal'],12)
txt(58,148,'REFERENCE MODULE — functional paths; verify connector orientation before wiring',12,COL['signal'],True)
box(65,200,270,100,'Module power switch','TPS22919\n+5VIN / EN → local +5V','power',12)
box(515,200,260,100,'Local analog filter','Ferrite and capacitors\n+5V → local +5VA','power',12)
box(935,200,200,100,'Analog supply','DAC, buffer, INA333','power',12)
power([(335,250),(515,250)],'≈5 V\nCurrent not determined',355,210)
power([(775,250),(935,250)],'≈5 V\nCurrent not determined',800,210)
box(65,365,270,115,'Sensor slot 1 (example)','MQ8 element + heater\nReference case at 5 V:\nHeater: 0,167 A','signal',12)
box(515,365,260,115,'Analog amplifier','INA333\nVIN+ / VIN− / REF','signal',12)
box(935,365,200,115,'Module ANOUT','One ADS channel\nADS read by ESP32','signal',12)
power([(200,300),(200,365)],'5 V 0,167 A*',215,321)
line([(335,420),(515,420)],'signal','VIN+ / VIN−',380,397)
line([(775,420),(935,420)],'signal','ANOUT',838,397)
box(65,535,270,80,'DAC','MCP4725','bus',12)
box(515,535,260,80,'Reference buffer','LM321DTR (XBLW)','signal',12)
box(935,535,200,80,'VMID reference','From motherboard','signal',12)
line([(335,575),(515,575)],'signal','DAC VOUT',420,551)
line([(775,575),(850,575),(850,505),(645,505),(645,480)],'signal','REF',862,526)
line([(935,575),(915,575),(915,640),(385,640),(385,490),(200,490),(200,480)],'signal','Voltage reference',787,620)
note('Module input current','*Heater reference model. Module current includes heater, analog circuitry and switch. Sensing current comes from the motherboard reference.')
end()

section('05  Analog acquisition and voltage reference','ADS1256 multiplexes eight analog inputs. Channels are converted sequentially.')
box(40,145,250,110,'Sensor inputs','Eight module outputs','signal',12)
box(445,145,270,110,'Input filters','Series resistors and\ncapacitors to ground','signal',12)
box(880,145,280,110,'ADS 8 Channel','ADS1256\nAVDD / DVDD / VREF','signal',12)
line([(290,200),(445,200)],'signal','AIN0...7',340,176)
line([(715,200),(880,200)],'signal','filtered analog',745,176)
box(40,360,250,110,'+5V rail','System power','power',12)
box(445,360,270,110,'Analog +5VA filter','User-supplied filter detail\nFerrite and capacitors','power',12)
box(880,360,280,110,'Reference and buffer','ADR03 + OPA320\nNominal reference 2.5 V','signal',12)
power([(290,415),(445,415)],'≈5 V\nCurrent not determined',308,373)
power([(715,415),(880,415)],'≈5 V\nCurrent not determined',735,373)
line([(1020,360),(1020,255)],'signal','2.5 V reference',1037,292)
box(40,570,290,100,'VMID buffer','10k / 10k divider + OPA320\nHalf of the analog supply','signal',12)
box(480,570,270,100,'Module reference','VMID input to each module','signal',12)
box(895,570,265,100,'VCC (3.3V)','Digital ADC supply','power',12)
power([(445,447),(380,447),(380,535),(185,535),(185,570)],'≈5 V\nCurrent not determined',195,495)
line([(330,620),(480,620)],'signal','≈2,5 V reference*',342,597)
power([(660,360),(660,300),(930,300),(930,255)],'5 V 0,007 A*',740,275)
power([(1030,570),(1177,570),(1177,220),(1160,220)],'3,3 V 0,0009 A*',1020,540)
tag(40,703,'*Reference values: analog supply 5 V, digital supply 3,3 V. Midpoint voltage changes with supply and output load.',12)
tag(40,729,'At the datasheet reference point: ADS analog 7 mA + digital 0.9 mA typical = 37.97 mW. Conditions: page 13.',12)
end()

section('06  I2C and sensor control','The ESP32 addresses three devices on the main I2C bus. Only the sensor DAC branches pass through the I2C multiplexer.')
box(40,185,260,125,'ESP32','Main I2C master','bus',12)
box(490,150,285,110,'I2C branch selector','TCA9548A\nEight downstream branches','bus',12)
box(925,150,235,110,'Module DACs','MCP4725\nSelected branch','bus',12)
box(490,360,285,110,'GPIO expander','PCF8574\nEight enable signals','control',12)
box(925,360,235,110,'Module switches','TPS22919\nOne per module','control',12)
box(490,570,285,110,'Temperature / humidity','SHT40','signal',12)
line([(300,247),(390,247),(390,205),(490,205)],'bus','I2C',405,182)
line([(390,247),(390,415),(490,415)],'bus','I2C',406,392)
line([(390,415),(390,625),(490,625)],'bus','I2C',406,602)
line([(775,205),(925,205)],'bus','selected I2C',798,182)
line([(775,415),(925,415)],'control','8 × EN',817,392)
tag(40,710,'Supply: TCA9548A = +5V; PCF8574 and SHT40 = VCC (3.3V). Current references: pages 12–14.',12)
end()

section('07  ESP32 communications and connections','One link to each bus group. Branches show shared SPI/I2C and separate UART ports.',)
rect(40,130,700,180,'#EAF0F8',COL['bus'],12); txt(62,145,'SPI',16,COL['bus'],True)
box(75,180,220,75,'ADS 8 Channel','ADS1256','signal',13,16)
box(435,180,220,75,'LoRa radio','E22-900MM22S','bus',13,16)
box(870,180,270,75,'LoRa antenna','External antenna','signal',13,16)
line([(655,218),(870,218)],'signal','RF',752,193,label_size=12)
line([(185,255),(185,280),(545,280),(545,255)],'bus',arrow=False)
tag(318,286,'SPI bus',12)
box(450,350,300,130,'ESP32','ESP32-S3-WROOM\nSPI | I2C | UART\nControl and status','control',14,17)
line([(600,350),(600,310)],'bus','SPI',619,323,label_size=13)
rect(40,540,520,185,'#EAF0F8',COL['bus'],12); txt(62,554,'I2C',16,COL['bus'],True)
# Wrapped titles avoid the previous right-side I2C collision.
box(65,590,140,82,'I2C mux','TCA9548A\nFor DAC','bus',12,16)
box(220,590,140,82,'GPIO mux','PCF8574\nModule power','control',12,16)
box(375,590,155,82,'Temperature','Humidity | SHT40','signal',12,15)
line([(135,672),(135,691),(451,691),(451,672)],'bus',arrow=False)
line([(290,672),(290,691)],'bus',arrow=False)
tag(267,701,'I2C bus',12)
rect(640,540,520,185,'#EAF0F8',COL['bus'],12); txt(662,554,'UART',16,COL['bus'],True)
box(670,590,200,82,'RS485','THVD1410','bus',13,16)
box(915,590,210,82,'USB programming','CH340C','control',13,16)
line([(770,710),(770,672)],'bus','UART2',783,693,label_size=12)
line([(1020,710),(1020,672)],'bus','UART0',1033,693,label_size=12)
line([(520,480),(520,540)],'bus','I2C',535,506,label_size=13)
line([(680,480),(680,540)],'bus','UART',696,506,label_size=13)
box(930,355,210,100,'Alarm / power','GPIO control\nand status','control',14,16)
line([(750,409),(930,409)],'control','GPIO',814,384,label_size=13)
end()

section('08  Shared 24 V rail, alarm, and battery','The +24V bus feeds both the alarm and buck converter. Battery boost demand can include both loads.')
box(40,150,260,90,'External 24 V','Fuse and input filter','power',12)
box(480,150,280,90,'Shared +24V bus','External supply or boost','power',12)
box(920,150,240,90,'Buck input path','Switch → LMR51450','power',12)
box(40,365,260,90,'Switched battery','4,2 V before switch drop','power',12)
box(480,365,280,90,'24 V boost','TPS61175 → SS54 diode','power',12)
power([(300,195),(480,195)],'≈24 V\nCurrent not determined',322,151)
power([(760,190),(920,190)],'≈24 V\nCurrent not determined',780,146)
power([(300,410),(480,410)],'≈4,2 V\nCurrent not determined',320,366)
power([(620,365),(620,240)],'≈24 V\nCurrent not determined',638,279)
box(40,560,260,90,'Alarm command','ESP32 GPIO','control',12)
box(480,560,280,90,'Alarm switch','Low-side transistor\nSwitched GND','control',12)
box(920,560,240,90,'Sound / light alarm','24 V variant required\nExact model unresolved','power',12)
line([(300,605),(480,605)],'control','ALARM',367,581)
power([(920,605),(760,605)],'≈0 V when on\nCurrent not determined',780,561)
power([(760,220),(840,220),(840,510),(1040,510),(1040,560)],'≈24 V\nCurrent not determined',860,339)
note('Battery monitor','4.2 V / (200k + 100k) = 14 µA. ADC input = 1.4 V; divider power = 58.8 µW. This is separate from alarm current.')
end()

section('09  Energy, data, and control flow','Power feeds devices. Sensor data travels through ADS to ESP32, then to communications interfaces.')
box(40,150,245,105,'Power inputs','24 V | battery 4.2 V | 5 V','power',12)
box(450,150,270,105,'Power rails','5 V | analog 5 V\n3,3 V | alarm 24 V','power',12)
box(915,150,245,105,'Loads','Sensors, ICs and alarm','power',12)
power([(285,202),(450,202)],'24 / 4,2 / 5 V\nCurrent not determined',303,163)
power([(720,202),(915,202)],'≈5 / 3,3 / 24 V\nCurrent not determined',740,164)
box(40,370,245,105,'Sensor modules','Analog outputs','signal',12)
box(450,370,270,105,'ADS 8 Channel','ADS1256','signal',12)
box(915,370,245,105,'ESP32','Reads and processes','control',12)
line([(285,422),(450,422)],'signal','analog',349,399)
line([(720,422),(915,422)],'bus','SPI data',791,399)
box(40,620,245,85,'Sensor control','I2C and enable','control',12)
box(450,620,270,85,'LoRa / RS485','External communications','bus',12)
box(915,620,245,85,'Alarm and status','GPIO control','control',12)
line([(960,475),(960,540),(163,540),(163,620)],'control','I2C / enable',421,517)
line([(1010,475),(1010,575),(585,575),(585,620)],'bus','SPI / UART',764,581)
line([(1100,475),(1100,620)],'control','GPIO',1112,552)
end()

section('10  Voltage calculations','Nominal resistor values from the schematic. These values exclude tolerance, ripple and load-dependent path drops.')
table(40,140,1120,['Rail / device','Calculation from schematic','Result','Source'],[
 ['5VBUCK / LMR51450','0.8 × (1 + 100k / 19.1k)','4.98848 V','S01'],
 ['5VBOOST / TPS61088, PWM','1.204 × (1 + 189k / 56k)','5.26750 V','S02'],
 ['5VBOOST / TPS61088, PFM','1.212 × (1 + 189k / 56k)','5.30250 V','S02'],
 ['Alarm boost, before SS54','1.229 × (1 + 187k / 10k)','24.21130 V','S03'],
 ['VCC / TPS62162','Fixed output option','3.3 V','S04'],
 ['3V3AON / TPS7A0233','Fixed output option','3.3 V','S06'],
 ['VMID, unloaded','VA × 10k / (10k + 10k)','VA / 2','Schematic'],
 ['Battery monitor at 4.2 V','4.2 × 100k / (200k + 100k)','1.4 V','Schematic'],
 ],[320,440,215,145],rh=43,size=13)
box(40,562,540,165,'Actual rail voltage','V5 = selected buck/boost voltage minus selector drop,\nor 5VEXT minus diode drop.\nVA = V5 minus analog-filter DC drop.\nVA24 = external or boosted source minus path drops.','power',13)
box(610,562,550,165,'Source compatibility needs verification','The backup set point is above 5.25 V (ADS AVDD limit)\nand 5.1 V (the reference MQ heater upper limit).\nA diode/filter drop is load-dependent; it does not\nprove the output is within range.','warn',13)
end()

section('11  Eight MQ heaters: calculated reference','Configuration identifies sensor types; fitted manufacturers are unconfirmed. Sources below are explicit reference vendors.')
rows=[]
for i,(n,r,t,v,s) in enumerate(SENSORS,1):
 rows.append([f'{i}  {n}',v,f'{r:g} ± {t:g}',f'{1000*5/r:.2f}',f'{25/r:.4f}',f'{1000*5/(r-t):.2f}',s])
table(40,139,1120,['Slot / type','Reference','RH (Ω)','I at 5 V (mA)','P at 5 V (W)','I at min RH (mA)','Ref'],rows,[150,155,145,185,170,205,110],rh=37,size=12)
box(40,504,540,130,'All eight enabled at exactly 5.000 V',f'I = Σ(5 / RH) = {B["heater_current_A"]:.5f} A\nP = Σ(25 / RH) = {B["heater_power_W"]:.5f} W\nAt minimum RH: {B["heater_current_A_min_R"]:.5f} A (same 5 V).','power',14)
box(610,504,550,130,'Meaning of these numbers','Room-temperature resistance calculation only.\nNot a steady-state heater maximum or measured load.\nAdd sensing paths, analog ICs and conversion losses.','warn',13)
para(40,657,'MQ7: the Hanwei reference specifies 5 V for 60 s and 1.4 V for 90 s. The constant-resistance cycle gives 0.33867 W; that cycle is not present in the supplied fixed-5V module reference. Do not use the cycle average as this board’s continuous-5V load.',1110,13)
end()

section('12  Digital IC load reference cases','P = Vtest × I. Vtest = 3.3 V unless stated. Do not add mutually exclusive operating modes.')
table(40,138,1120,['Device / condition','Current','Calculated power','Basis'],[
 ['ESP32, 240 MHz dual-core data access','91.7 mA typ','302.61 mW','RF off; peripheral clocks off [S10]'],
 ['ESP32, Wi-Fi 802.11b TX, 20.5 dBm','355 mA peak','1171.50 mW','Separate RF-on condition [S10]'],
 ['LoRa, maximum TX operating mode','119 mA typ','392.70 mW','E22-900MM22S [S11]'],
 ['LoRa, receive','6.8 mA typ','22.44 mW','RX only [S11]'],
 ['LoRa, sleep','2 µA typ','6.60 µW','Sleep only [S11]'],
 ['SHT40, measurement','320 / 500 µA','1.056 / 1.650 mW','Typ / max; heater off [S12]'],
 ['SHT40, highest heater setting','60 / 100 mA','198 / 330 mW','Typ / max; during heating [S12]'],
 ['THVD1410, receiver only','0.700 / 0.960 mA','2.310 / 3.168 mW','Typ / max, unloaded [S15]'],
 ['THVD1410, driver only','2.0 / 2.5 mA','6.60 / 8.25 mW','Typ / max; add line load [S15]'],
 ['PCF8574, NXP reference at 6 V','40 / 100 µA','240 / 600 µW at 6 V','100 kHz, unloaded [S14]'],
 ['CH340C, active at 3.3 V','4 / 12 mA','13.2 / 39.6 mW','25°C; excludes USB pins [S32]'],
 ['TCA9548A, reference at 5.5 V','9 / 30 µA','49.5 / 165 µW at 5.5 V','100 kHz, unloaded [S13]'],
 ],[370,175,220,355],rh=37,size=12)
para(40,648,'PCF8574 vendor is unconfirmed: the NXP 6 V case is a reference, not a verified 3.3 V board value. TCA9548A is on +5V; its table above uses the specified 5.5 V test point. Its 400 kHz reference rises to 50 / 80 µA. Do not silently use either test voltage as the actual rail.',1110,12)
para(40,712,'ESP32 memory/I/O loads and duty cycle remain additional conditions. VCC also supplies ADS DVDD, pull-ups and LED. CH340C USB suspend is 40 µA typ / 150 µA max at 3.3 V (132 / 495 µW).',1110,12)
end()

section('13  Analog, AON, and module IC references','No-load IC figures do not include pull-ups, output loads, resistor networks or conversion losses.')
table(40,135,1120,['Device / condition','Current reference','Power / calculation','Source'],[
 ['ADS AVDD at 5 V, PGA1, buffer off','7 / 10 mA','35 / 50 mW (typ / max)','S07'],
 ['ADS DVDD at 3.3 V, CLKOUT off','0.9 / 2 mA','2.97 / 6.6 mW (typ / max)','S07'],
 ['OPA320, each, no load at 5.5 V','1.5 / 1.75 mA','8.25 / 9.625 mW at 5.5 V, 25°C','S08'],
 ['ADR03, no load at 5 V','0.65 / 1 mA','3.25 / 5 mW (typ / max)','S09'],
 ['VMID divider at VA = 5 V','5 / 20k = 250 µA','1.25 mW','Schematic'],
 ['TPL5010, normal operation','35 / 50 nA','0.1155 / 0.165 µW at 3.3 V','S16'],
 ['SN74AUP1G74, static, up to 85°C','0.5 µA max','1.65 µW at 3.3 V','S17'],
 ['SN74LVC1G06, static','10 µA max','33 µW at 3.3 V','S18'],
 ['TPS3839, no output load','150 / 500 nA','0.495 / 1.65 µW at 3.3 V','S19'],
 ['Module: INA333 + MCP4725 + XBLW buffer','50 + 210 + 100 = 360 µA typ','IC benchmark only; + other loads','S28–S31'],
 ['Module switch TPS22919','8 µA typ at 3.6 V','28.8 µW at 3.6 V; + I² × RON','S30'],
 ],[415,265,335,105],rh=37,size=11.5)
para(40,600,'ADS figures use the datasheet’s 7.68 MHz clock. The schematic has an 8 MHz crystal: these are reference cases, not guaranteed board maxima. Higher PGA/buffer settings increase analog current. Sum at the stated low-power case: 37.97 mW typ, 56.60 mW from table maxima.',1110,13)
para(40,672,'Module benchmark conditions: INA333 at midsupply/no output load; MCP4725 code 000h, digital inputs grounded/no load; XBLW LM321DTR at 5 V/no load. The switch’s 3.6 V figure is not a measured 5 V total. VMID and VREF output currents must be added to their buffers.',1110,13)
end()

section('14  Rail currents and complete budget equations','All I symbols are in amperes, P in watts. η is actual efficiency at the operating point; no efficiency is invented.')
table(40,135,1120,['Power path / symbol','Current / power equation or included load'],[
 ['VCC: I33; P33 = 3.3 × I33','IESP + ILORA + IADSD + ISHT + IPCF + IRS485 + IUSB + IPULL/LED'],
 ['VCC converter input: I33IN','P33 / (V5 × η33). η33 includes converter losses; do not add IQ twice.'],
 ['Module: IM; all modules: I8','IM = IH + IMA + IQSW; I8 = sum of eight IM, including off-state leakage.'],
 ['Local module analog: IMA','IDAC + IINA + IBUFFER + local passive/output loads. VMID-sourced ISENSE is excluded.'],
 ['Motherboard analog: IANA','IADSA + IREFSUP + IMIDSUP; add capacitor charging/leakage for transients.'],
 ['IREFSUP / IMIDSUP','ADR03 + reference OPA/load / VMID OPA + sensing/reference loads + VA / 20k.'],
 ['Main rail: I5; P5 = V5 × I5','I8 + IANA + I33IN + ITCA + I5PULL + leakage; no upstream regulator double count.'],
 ['Selector paths: IK / IX / IE5','Source share of I5 + applicable bias/leakage current. Conduction loss is a power term.'],
 ['Battery boost input: IB5','Boost output power / (VB × ηB5); output includes IX and feedback/control loads.'],
 ['Shared bus: I24EXT + I24BOOST','IAL + IKIN + I24PAR. Alarm branch PALBR = VA24 × IAL, including switch loss.'],
 ['24 V boost input: IB24','P24OUT / (VB × ηB24); include I24BOOST, diode loss and feedback load.'],
 ['Switched battery: IBSW','IB5 + IB24 + other switched-VBAT leakage.'],
 ['Battery source: IB at 4.2 V','IBSW + switch ground current + 14 µA monitor + battery share of IAIN.'],
 ['External 24 V input: I24','I24EXT + input leakage; IKIN = PK / (V24P × ηK). Series loss changes voltage/power.'],
 ['External 5 V input: IE','IE5 + external-5V share of IAIN; diode losses set the downstream voltage.'],
 ],[320,800],rh=33,size=11.5)
para(40,679,'IA = IWD + IINV + ILATCH + ISUP + AON pull-ups/switching; IAIN = IA + LDO ground current IG. PK includes selector demand, buck-fed AON, feedback and PR1 divider loads. I24PAR includes other shared-rail leakage. Set disabled-converter terms to their off-state leakage, not an assumed active load.',1110,12)
para(40,725,'VM = module switched +5V; VMA = local analog rail; VA = motherboard analog rail. VD = diode drop. VSW(on) = low-side switch drop; alarm load power = (VA24 − VSW) × IAL.',1110,11)
end()

section('15  Engineering notes and unresolved quantities','Schematic-based calculation boundaries. These are document corrections and findings, not hardware modifications.')
box(40,138,540,175,'4.2 V battery: meaningful lower-bound example',f'At the 5.000 V heater resistance reference:\n6.57468 W / 4.2 V = {B["heater_only_ideal_battery_A_at_4_2V"]:.5f} A.\nThis is the ideal source current for that heater case only.\nActual current includes electronics, alarm and losses.\nNo battery runtime is claimed without capacity.','power',13)
box(610,138,550,175,'Alarm cannot yet have a numeric load','BYS / YS-01 / YS-02 is not one identified part.\nThe schematic supplies a nominal 24 V alarm.\nEx marking and sound level do not determine watts.\nKeep IAL symbolic until manufacturer, 24 V variant,\noperating current and inrush are identified.','warn',13)
box(40,341,540,173,'Small paths that must remain in the budget','Buck FB: 4.98848 / 119.1k = 41.885 µA.\nSelector PR1: 4.98848 / 20.99k = 237.660 µA.\nBoost FB: 5.26750 / 245k = 21.500 µA.\nAlarm FB: 24.21130 / 197k = 122.900 µA.\nA low 10k pull-up draws Vrail / 10k while low.','power',13)
box(610,341,550,173,'Limits are not consumption','TPS62162: 1 A output rating, not a 1 A load.\nTPS2116: 2.5 A rating, not normal supply current.\nTPS61175: 3 A switch rating, not 3 A at 24 V.\nCheck thermal, inductor, switch and transient limits\nwith the complete operating-point budget.','warn',13)
para(40,549,'Passive-load handling: capacitor charging requires I = C × dV/dt. Ferrite “600 Ω” is an AC impedance label, not DC resistance. The module’s 1k QOD resistor is a discharge path, not a continuous 5 mA on-state load. Reference/filter resistors do not automatically draw V/R when their far end is high impedance.',1110,13)
para(40,627,'Provenance: motherboard connections come from the original ZIP and PCB net map; the +5V-to-motherboard-+5VA filter is from the user’s later 5VA.png detail. The reference module is a separate image. Sensor names come from BoardPinsGLD2.h. Original design files and firmware were not changed.',1110,13)
para(40,695,'Source interaction: the external +24V filter has no series reverse-block diode; boost operation and backfeed depend on source/control states. USB VBUS also reaches the AON diode OR. These paths prevent an unconditional single total-current figure.',1110,12)
end()

for group,title in ((SOURCES[:16],'16  Source references — power and digital'),(SOURCES[16:],'17  Source references — sensors and analog')):
 section(title,'Manufacturer documents and original manufacturer datasheets mirrored by distributors. Accessed 22 September 2026.')
 y=131
 for ident,part,location,url in group:
  txt(42,y,f'{ident}  {part} — {location}',11.2,bold=True)
  # Link label is short in the PDF; full URL is retained in the accompanying JSON.
  label=url.replace('https://','')
  if pdfmetrics.stringWidth(label,'Arial',10)>1110: label=label[:130]+'…'
  txt(42,y+17,label,10,COL['bus'])
  P.linkURL(url,(40,H-y-31,1155,H-y-15),relative=0,thickness=0)
  y+=37
 txt(42,746,'Full URLs and calculation inputs: power-sources.json, power-calculations.json and power_budget.py in the diagram package.',11)
 end()
