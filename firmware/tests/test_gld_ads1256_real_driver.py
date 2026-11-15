"""Host tests for the real ADS1256 reader with SPI/DRDY simulated, no hardware."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'firmware/gld/src/GldAds1256Reader.cpp'
INC = ROOT / 'firmware/gld/include'
def old_namespace(text):
    text = re.sub(r"namespace ([\w]+(?:::\w+)+) \{ (namespace \w+ = [\w:]+;) \}", lambda m: " ".join(f"namespace {part} {{" for part in m[1].split("::")) + " " + m[2] + " " + "}" * len(m[1].split("::")), text)
    text = re.sub(r"namespace ([\w]+(?:::\w+)+) \{", lambda m: " ".join(f"namespace {part} {{" for part in m[1].split("::")), text)
    return re.sub(r"\}  // namespace ([\w]+(?:::\w+)+)", lambda m: "}" * len(m[1].split("::")) + " // namespace " + m[1], text)

ARDUINO = r'''
#pragma once
#include <cstdint>
#include <cmath>
constexpr int LOW=0,HIGH=1,INPUT=0,OUTPUT=1;
extern unsigned long fakeTime;
extern bool drdyStuckHigh, drdyStuckLow, calibrationHighPending;
extern int pinState[128], chipSelectViolations;
extern int transactionCount, forceDrdyHighAtTransaction;
unsigned long millis();
void delay(unsigned long ms);
void delayMicroseconds(unsigned int);
void pinMode(int,int);
void digitalWrite(int,int);
int digitalRead(int);
'''
SPI = r'''
#pragma once
#include <cstdint>
#include <vector>
constexpr int MSBFIRST=1,SPI_MODE1=1;
struct SPISettings { unsigned long clock; int order,mode; SPISettings(unsigned long c,int o,int m):clock(c),order(o),mode(m){} };
extern bool calibrationHighPending;
extern int transactionCount;
struct SPIClass {
 std::vector<std::vector<uint8_t>> transactions;
 std::vector<uint8_t> tx;
 uint8_t registers[16]{};
 int32_t nextRaw=0;
 bool begun=false; int sck=-1,miso=-1,mosi=-1,settingsErrors=0;
 void begin(int a,int b,int c){begun=true;sck=a;miso=b;mosi=c;}
 void beginTransaction(SPISettings v){if(v.clock!=1920000 || v.order!=MSBFIRST || v.mode!=SPI_MODE1) ++settingsErrors;tx.clear();}
 uint8_t transfer(uint8_t value){
   tx.push_back(value); const uint8_t cmd=tx[0];
   if(cmd==0xF0 && tx.size()==1) calibrationHighPending=true;
   if((cmd & 0xF0)==0x50 && tx.size()==3) registers[cmd & 0x0F]=value;
   if((cmd & 0xF0)==0x10 && tx.size()==3) return registers[cmd & 0x0F];
   if(cmd==0x01 && tx.size()>=2 && tx.size()<=4) {
     uint32_t bits=static_cast<uint32_t>(nextRaw)&0xFFFFFF;
     return static_cast<uint8_t>(bits >> (8*(4-tx.size())));
   }
   return 0;
 }
 void endTransaction(){transactions.push_back(tx);++transactionCount;}
};
'''
HARNESS = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include "Arduino.h"
#include "SPI.h"
#include "GldAds1256Reader.h"
#include "BoardPins.h"
using namespace pgl::gld;
namespace b=pgl::gld::board;
unsigned long fakeTime=0; bool drdyStuckHigh=false, drdyStuckLow=false, calibrationHighPending=false;
int pinState[128]{}; int chipSelectViolations=0; int transactionCount=0,forceDrdyHighAtTransaction=-1;
unsigned long millis(){return fakeTime;}
void delay(unsigned long ms){fakeTime+=ms;}
void delayMicroseconds(unsigned int){}
void pinMode(int,int){}
void digitalWrite(int pin,int value){if(pin>=0 && pin<128){if(pin==b::PIN_ADS1256_CS && value==LOW && pinState[b::PIN_LORA_CS]!=HIGH) ++chipSelectViolations;pinState[pin]=value;}}
int digitalRead(int pin){ assert(pin==b::PIN_ADS1256_DRDY); if(drdyStuckHigh || (forceDrdyHighAtTransaction>=0 && transactionCount>=forceDrdyHighAtTransaction))return HIGH;if(drdyStuckLow)return LOW;if(calibrationHighPending){calibrationHighPending=false;return HIGH;}return LOW; }
int main(){
  SPIClass spi; GldAds1256Reader adc;
  assert(adc.readChannel(0).status==GldAds1256Status::NotReady);
  drdyStuckHigh=true;const unsigned long bootStart=fakeTime;
  assert(!adc.begin(spi));assert(fakeTime-bootStart>=1500);assert(!adc.ready());
  assert(pinState[b::PIN_ADS1256_CS]==HIGH && pinState[b::PIN_LORA_CS]==HIGH);
  drdyStuckHigh=false; drdyStuckLow=true;const unsigned long calibrationStart=fakeTime;
  assert(!adc.begin(spi));assert(fakeTime-calibrationStart>=1500);assert(!adc.ready());
  drdyStuckLow=false;calibrationHighPending=false;spi.nextRaw=0;assert(adc.begin(spi));assert(adc.ready()&&spi.begun);assert(spi.sck==b::PIN_SPI_SCK && spi.miso==b::PIN_SPI_MISO && spi.mosi==b::PIN_SPI_MOSI && spi.settingsErrors==0);
  assert(spi.registers[0]==0x36 && spi.registers[3]==0xF0 && spi.registers[2]==6);
  assert(adc.readStatusRegister()==0x36 && adc.readDrateRegister()==0xF0);
  assert(adc.readChannel(8).status==GldAds1256Status::InvalidChannel);
  spi.nextRaw=0x400000;
  for(uint8_t i=0;i<8;i++) {auto r=adc.readChannel(i);assert(r.status==GldAds1256Status::Ok && r.raw==0x400000 && r.gain==64 && !r.saturated);assert(std::fabs(r.voltage-(2.497f/64.0f))<0.00001f);assert(spi.registers[1]==static_cast<uint8_t>(0x0F | (i<<4)));}
  spi.nextRaw=-0x400000;auto neg=adc.readChannel(1);assert(neg.status==GldAds1256Status::Ok && neg.raw==-0x400000 && neg.voltage<0);
  spi.nextRaw=0x780000;auto high=adc.readChannel(0);assert(high.status==GldAds1256Status::Ok && high.gain==32 && spi.registers[2]==5);
  spi.nextRaw=0x400000;auto other=adc.readChannel(1);assert(other.status==GldAds1256Status::Ok && other.gain==64 && spi.registers[2]==6);
  spi.nextRaw=0;for(int i=0;i<4;i++)assert(adc.readChannel(0).gain==32);assert(adc.readChannel(0).gain==64);
  // The MUX write succeeds; DRDY then stalls before first RDATA read.
  forceDrdyHighAtTransaction=transactionCount+1;const auto readTxns=spi.transactions.size();const auto readBefore=fakeTime;auto readBad=adc.readChannel(0);
  assert(readBad.status==GldAds1256Status::DrdyTimeout && fakeTime-readBefore>=15);
  assert(spi.transactions.size()==readTxns+1 && pinState[b::PIN_ADS1256_CS]==HIGH);forceDrdyHighAtTransaction=-1;
  const auto transactions=spi.transactions.size();drdyStuckHigh=true;const auto before=fakeTime;auto bad=adc.readChannel(0);
  assert(bad.status==GldAds1256Status::DrdyTimeout && fakeTime-before>=25);
  assert(spi.transactions.size()==transactions && pinState[b::PIN_ADS1256_CS]==HIGH && chipSelectViolations==0);
}
'''

@unittest.skipUnless(os.environ.get('CXX') or shutil.which('g++') or (Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe').exists(), 'C++ compiler not available')
class AdsReaderHostTests(unittest.TestCase):
    def test_real_reader_profiles_and_negative_control(self):
        cxx=os.environ.get('CXX') or shutil.which('g++') or str(Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe')
        source=old_namespace(SRC.read_text(encoding='utf8'))
        marker='if (!waitDrdyLow(timeoutMs)) {'
        self.assertGreater(source.count(marker),0)
        with tempfile.TemporaryDirectory(prefix='gld-ads-fake-') as temp:
            temp=Path(temp);(temp/'Arduino.h').write_text(ARDUINO,encoding='utf8');(temp/'SPI.h').write_text(SPI,encoding='utf8');(temp/'harness.cpp').write_text(HARNESS,encoding='utf8');
            for name in ('BoardPins.h','BoardPinsGLD2.h','BoardPinsGLD3.h','BoardPinsGLDATEX.h','GldAds1256Reader.h'):
                (temp/name).write_text(old_namespace((INC/name).read_text(encoding='utf8')),encoding='utf8')
            reader=temp/'reader.cpp';exe=temp/('case.exe' if os.name=='nt' else 'case')
            env=os.environ.copy();env['PATH']=str(Path(cxx).parent)+os.pathsep+env.get('PATH','')
            for label,board2,atex,mutate in [('GLD1',0,0,''),('GLD2',1,0,''),('ATEX',1,1,''),('ATEX_DRDY_MUTANT',1,1,'drdy'),('ATEX_GAIN_MUTANT',1,1,'gain'),('ATEX_MUX_MUTANT',1,1,'mux')]:
                with self.subTest(profile=label):
                    mutant=source.replace(marker,'if (false && !waitDrdyLow(timeoutMs)) {') if mutate=='drdy' else source.replace('constexpr uint8_t ADS1256_AGC_GAIN_DOWN_CONFIRM = 1;', 'constexpr uint8_t ADS1256_AGC_GAIN_DOWN_CONFIRM = 2;') if mutate=='gain' else source.replace('muxSingleEnded(adsInputForSensor(channel))', 'muxSingleEnded(7 - adsInputForSensor(channel))') if mutate=='mux' else source
                    if mutate:self.assertNotEqual(mutant,source)
                    reader.write_text(mutant,encoding='utf8')
                    cmd=[cxx,'-std=c++17','-I'+str(temp),'-I'+str(INC),f'-DPGL_GLD_BOARD_PROFILE_GLD2={board2}',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={atex}',f'-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={1-board2}',str(reader),str(temp/'harness.cpp'),'-o',str(exe)]
                    if os.name=='nt':cmd.insert(1,'-static')
                    build=subprocess.run(cmd,check=False,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
                    if build.returncode: raise RuntimeError(build.stderr.decode(errors="replace")[:3000])
                    result=subprocess.run([str(exe)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                    if mutate:self.assertNotEqual(result.returncode,0,'driver mutation unexpectedly passed')
                    else:self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

if __name__=='__main__': unittest.main()
