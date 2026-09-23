"""Reproducible reference calculations, not measurements or an as-built guarantee."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = [
 ('S01','LMR51450','TI electrical characteristics: 0.8 V feedback','https://www.ti.com/lit/ds/symlink/lmr51450.pdf'),
 ('S02','TPS61088','TI electrical characteristics: PWM/PFM feedback','https://www.ti.com/lit/ds/symlink/tps61088.pdf'),
 ('S03','TPS61175','TI electrical characteristics: 1.229 V feedback','https://www.ti.com/lit/ds/symlink/tps61175.pdf'),
 ('S04','TPS62162','TI fixed 3.3 V option; converter rating','https://www.ti.com/lit/ds/symlink/tps62162.pdf'),
 ('S05','TPS2116','TI power multiplexer; rating is not load current','https://www.ti.com/lit/ds/symlink/tps2116.pdf'),
 ('S06','TPS7A02','TI fixed 3.3 V option; ground current depends on load','https://www.ti.com/lit/ds/symlink/tps7a02.pdf'),
 ('S07','ADS1256','TI electrical characteristics, 7.68 MHz clock','https://www.ti.com/lit/ds/symlink/ads1256.pdf'),
 ('S08','OPA320','TI supply-current table, no output load','https://www.ti.com/lit/ds/symlink/opa320.pdf'),
 ('S09','ADR03','Analog Devices Rev. S, Table 4','https://www.analog.com/media/en/technical-documentation/data-sheets/ADR01_02_03_06.pdf'),
 ('S10','ESP32-S3-WROOM-1','Espressif v1.8, Tables 6-4 and 6-6','https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf'),
 ('S11','E22-900MM22S','Ebyte electrical-parameter table','https://www.cdebyte.com/products/E22-900MM22S/1'),
 ('S12','SHT40','Sensirion SHT4x current and heater tables','https://sensirion.com/resource/datasheet/sht4x'),
 ('S13','TCA9548A','TI electrical characteristics, 100/400 kHz','https://www.ti.com/lit/ds/symlink/tca9548a.pdf'),
 ('S14','PCF8574','NXP reference only; fitted vendor not established','https://www.nxp.com/docs/en/data-sheet/PCF8574_PCF8574A.pdf'),
 ('S15','THVD1410','TI quiescent current; excludes bus load','https://www.ti.com/lit/ds/symlink/thvd1410.pdf'),
 ('S16','TPL5010','TI supply current and timing conversion','https://www.ti.com/lit/ds/symlink/tpl5010.pdf'),
 ('S17','SN74AUP1G74','TI static ICC at valid logic levels','https://www.ti.com/lit/ds/symlink/sn74aup1g74.pdf'),
 ('S18','SN74LVC1G06','TI static ICC; excludes pull-up load','https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf'),
 ('S19','TPS3839','TI supply current, output unloaded','https://www.ti.com/lit/ds/symlink/tps3839.pdf'),
 ('S20','MQ8','Winsen MQ-8 heater resistance at room temperature','https://www.winsen-sensor.com/product/mq-8.html'),
 ('S21','MQ135','Winsen MQ135 heater resistance at room temperature','https://www.winsen-sensor.com/manual/mq135.html'),
 ('S22','MQ3','Hanwei original datasheet, hosted by Olimex','https://www.olimex.com/Products/Components/Sensors/Gas/SNS-MQ3/resources/SNS-MQ3.pdf'),
 ('S23','MQ5','Winsen MQ-5 heater resistance at room temperature','https://www.winsen-sensor.com/product/mq-5.html'),
 ('S24','MQ4','Winsen MQ-4 heater resistance at room temperature','https://www.winsen-sensor.com/product/mq-4.html'),
 ('S25','MQ7','Hanwei original datasheet, hosted by SparkFun','https://www.sparkfun.com/datasheets/Sensors/Biometric/MQ-7.pdf'),
 ('S26','MQ6','Winsen MQ-6 heater resistance at room temperature','https://www.winsen-sensor.com/product/mq-6.html'),
 ('S27','MQ2','Winsen MQ-2 heater resistance at room temperature','https://www.winsen-sensor.com/product/mq-2.html'),
 ('S28','INA333','TI quiescent current, output unloaded','https://www.ti.com/lit/ds/symlink/ina333.pdf'),
 ('S29','MCP4725','Microchip supply current, DS20002039E p3','https://ww1.microchip.com/downloads/aemDocuments/documents/MSLD/ProductDocuments/DataSheets/MCP4725-Data-Sheet-20002039E.pdf'),
 ('S30','TPS22919','TI switch supply current and on-resistance','https://www.ti.com/lit/ds/symlink/tps22919.pdf'),
 ('S31','LM321DTR (XBLW)','XBLW original datasheet v1.0 p2; distributor mirror','https://xonstorage.z8.web.core.windows.net/pdf/xblw_lm321dtrxblw_xonlink.pdf'),
 ('S32','CH340C','WCH original datasheet v3D, section 6.3; distributor mirror','https://www.hestore.eu/en/prod_getfile.php?id=21171'),
]
SENSORS=[('MQ8',30,3,'Winsen','S20'),('MQ135',30,3,'Winsen','S21'),
 ('MQ3',33,1.65,'Hanwei','S22'),('MQ5',30,3,'Winsen','S23'),
 ('MQ4',28,3,'Winsen','S24'),('MQ7',33,1.65,'Hanwei','S25'),
 ('MQ6',30,3,'Winsen','S26'),('MQ2',30,3,'Winsen','S27')]

# Each case is independent. Different supply voltages and modes must not be
# summed into a purported measured board load. None is a whole-device maximum.
IC_CASES=[
 ('ESP32 dual-core 128-bit access 240MHz, peripheral clocks off',3.3,.0917,None,'S10'),
 ('ESP32 802.11b TX 20.5dBm peak reference',3.3,.355,None,'S10'),
 ('E22 TX typical',3.3,.119,None,'S11'),
 ('E22 RX typical',3.3,.0068,None,'S11'),
 ('E22 sleep typical',3.3,.000002,None,'S11'),
 ('SHT40 measurement heater off',3.3,.000320,.000500,'S12'),
 ('SHT40 heater 200mW setting active',3.3,.060,.100,'S12'),
 ('THVD1410 RX only unloaded',3.3,.000700,.000960,'S15'),
 ('THVD1410 TX only unloaded',3.3,.002,.0025,'S15'),
 ('PCF8574 NXP reference 100kHz unloaded',6,.000040,.000100,'S14'),
 ('CH340C active 25C USB pins excluded',3.3,.004,.012,'S32'),
 ('CH340C suspended 25C USB pins excluded',3.3,.000040,.000150,'S32'),
 ('TCA9548A 100kHz unloaded',5.5,.000009,.000030,'S13'),
 ('ADS AVDD PGA1 buffer off 7.68MHz',5,.007,.010,'S07'),
 ('ADS DVDD CLKOUT off 7.68MHz',3.3,.0009,.002,'S07'),
 ('OPA320 25C no output load',5.5,.0015,.00175,'S08'),
 ('ADR03 no output load',5,.00065,.001,'S09'),
 ('TPL5010 operation, excludes timing conversion',3.3,35e-9,50e-9,'S16'),
 ('SN74AUP1G74 static to85C valid levels',3.3,None,.5e-6,'S17'),
 ('SN74LVC1G06 static valid levels',3.3,None,10e-6,'S18'),
 ('TPS3839 unloaded',3.3,150e-9,500e-9,'S19'),
 ('TPS22919 unloaded supply, excludes conduction loss',3.6,8e-6,15e-6,'S30'),
]

def calculate():
 sensors=[dict(model=n,ohms=r,tolerance_ohms=t,reference_vendor=v,source=s,
   current_A_at_5V=5/r,power_W_at_5V=25/r,
   current_A_at_5V_min_R=5/(r-t)) for n,r,t,v,s in SENSORS]
 heater=sum(x['power_W_at_5V'] for x in sensors)
 return dict(basis='Room-temperature resistance model at exactly 5.000 V; reference vendors, not fitted-maker confirmation.',
   sensors=sensors,heater_power_W=heater,heater_current_A=heater/5,
   ic_reference_cases=[dict(case=n,Vtest=v,Ireference_A=i,Imax_A=m,
      Preference_W=None if i is None else v*i,Pmax_W=None if m is None else v*m,source=s)
      for n,v,i,m,s in IC_CASES],
   heater_current_A_min_R=sum(x['current_A_at_5V_min_R'] for x in sensors),
   heater_only_ideal_battery_A_at_4_2V=heater/4.2,
   buck_V=.8*(1+100/19.1),boost_PWM_V=1.204*(1+189/56),boost_PFM_V=1.212*(1+189/56),
   alarm_boost_pre_diode_V=1.229*(1+187/10),battery_monitor_V=4.2/3,
   battery_divider_A=4.2/300000,vmid_divider_A_at_5V=5/20000,
   ads_typ_W=5*.007+3.3*.0009,ads_table_max_W=5*.010+3.3*.002,
   lora_tx_W=3.3*.119,lora_rx_W=3.3*.0068,
   mq7_cycle_reference_W=(25/33*60+1.4**2/33*90)/150)

B=calculate()
assert abs(B['boost_PWM_V']-5.2675)<1e-9
assert abs(B['heater_power_W']-6.574675324675325)<1e-9

def export():
 (HERE/'power-calculations.json').write_text(json.dumps(B,indent=2)+'\n',encoding='utf8')
 (HERE/'power-sources.json').write_text(json.dumps([dict(id=i,part=p,location=l,url=u,accessed='2026-09-22') for i,p,l,u in SOURCES],indent=2)+'\n',encoding='utf8')

if __name__=='__main__':
 export()
 print(json.dumps(B,indent=2))
