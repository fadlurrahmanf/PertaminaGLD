"""Host integration check. Crypto and nonce are fakes; no hardware proof.

Run: python firmware/gld/tests/run_atex_alarm_consistency.py
Set MINGW_CXX to a host g++ if it is not on PATH.
"""
from pathlib import Path
import os, re, shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[3]
s=(root/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8')
def body(signature):
 i=s.index(signature);o=s.index('{',i);d=0
 for n in range(o,len(s)):
  if s[n]=='{':d+=1
  elif s[n]=='}':
   d-=1
   if not d:return s[i:n+1]
 raise ValueError(signature)
m=re.search(r'const bool classifierAlarm = lastInferenceValid &&\s*lastResult\.gasClass != pgl::protocol::GLD_GAS_CLEAR;',s)
assert m, 'classifier expression not found'
pre=r'''
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include "GldFrameBuilder.h"
#include "ChUplink.h"
#include "NodeCache.h"
namespace pgl { namespace gld {
struct GldClassifyResult {uint8_t gasClass;uint8_t confidence;};
struct GldPowerReading {bool batteryValid=false;uint16_t batteryMv=0;bool externalPower=true;};
uint8_t nextSeq=0; bool externalPower=true; bool reserveGldTxSequence(uint8_t& seq){seq=++nextSeq;return true;} GldPowerReading readGldPower(){GldPowerReading p; p.externalPower=externalPower;return p;}
const char* gldGasClassName(uint8_t){return "fixture";}
} namespace protocol {
GldCryptoStatus encryptGldPayload(const uint8_t*,uint8_t,const uint8_t*,const GldPlainPayload&,uint16_t,uint8_t,uint8_t,GldEncryptedPayload& out){std::memset(out.bytes,0,sizeof(out.bytes));return GldCryptoStatus::Ok;}
} }
struct { bool aesKeyPresent=true;uint8_t aesKeyId=1,aesKey[16]{};uint16_t nodeId=0x1001,chId=0x10; } runtimeConfig;
struct GldTxSnapshot {bool valid=false,alarm=false;uint8_t sequence=0,frameLen=0;uint8_t frame[255]{};};
int16_t lastLoraTxState=0;bool lastLoraTxOk=false;uint8_t txSeq=0;uint32_t txCounter=0;constexpr bool TFBG_CONTINUOUS_BATTERY=false;
struct NonceCtx{uint32_t counter;};bool nonceProvider(uint8_t*,void* ctx){++static_cast<NonceCtx*>(ctx)->counter;return true;}
void logPrintf(const char*,...){} void logPrintln(const char*){}
bool lastInferenceValid=true;pgl::gld::GldClassifyResult lastResult{};
'''
post=r'''
int main(){using namespace pgl::protocol;using namespace pgl::ch;
#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW && PGL_GLD_BOARD_PROFILE_GLD_ATEX
 constexpr bool at = true;
#else
 constexpr bool at = false;
#endif
 for(bool ext : {false,true}) { pgl::gld::externalPower=ext;
 for(uint8_t gas : {uint8_t(GLD_GAS_CLEAR),uint8_t(GLD_GAS_LPG)}) {
 for(uint8_t confidence : {uint8_t(0),uint8_t(1),uint8_t(29),uint8_t(30)}) {
 lastResult={gas,confidence};lastInferenceValid=true;bool physical=physicalClassifier();GldTxSnapshot snap;assert(buildTxSnapshot(lastResult,snap) && snap.valid);
 ChGldUplinkView uplink{}; assert(parseGldUplinkFrame(snap.frame,snap.frameLen,uplink)==ChUplinkStatus::Ok);
 bool expected=gas!=GLD_GAS_CLEAR && (at || confidence>=1);assert(physical==(gas!=GLD_GAS_CLEAR));assert(snap.alarm==expected && uplink.alarm==expected && uplink.externalPower==ext);
 NodeCacheEntry cache[1]{};NodeCacheUpdateResult result{};assert(updateNodeCacheFromUplink(cache,1,uplink,1,result)==NodeCacheStatus::Inserted);assert(result.shouldAckAlarm==expected);assert(isNodeCacheEntryAlarm(cache[0])==expected);
 }
 }
 NodeCacheEntry cache[1]{}; NodeCacheUpdateResult result{};
 for(uint8_t confidence : {uint8_t(1),uint8_t(0)}) { lastResult={GLD_GAS_LPG,confidence};GldTxSnapshot snap;assert(buildTxSnapshot(lastResult,snap));ChGldUplinkView uplink{};assert(parseGldUplinkFrame(snap.frame,snap.frameLen,uplink)==ChUplinkStatus::Ok); updateNodeCacheFromUplink(cache,1,uplink,confidence+2,result); if(confidence==0){assert(result.isRecoveryClear==!at);assert(result.shouldAckAlarm==at);} }
 }
 printf("ATEX workflow=%d: 16 input combinations and recovery transition passed\n",int(at));
}
'''
# Extract the classifier expression from production; run real buildTxSnapshot and GldFrameBuilder.
program=pre+'bool physicalClassifier(){'+m.group(0)+' return classifierAlarm;}\n'+body('bool buildTxSnapshot(')+post
compiler=os.environ.get("MINGW_CXX") or shutil.which("g++") or str(Path.home()/".platformio/packages/toolchain-gccmingw32/bin/g++.exe")
if not Path(compiler).is_file():
 raise SystemExit("Host C++ compiler not found; set MINGW_CXX")
env=dict(os.environ); env["PATH"]=str(Path(compiler).resolve().parent)+os.pathsep+env.get("PATH","")
files=['firmware/gld/src/GldFrameBuilder.cpp','firmware/shared/src/GldPayload.cpp','firmware/shared/src/GldRecord.cpp','firmware/shared/src/AppFrame.cpp','firmware/ch/src/ChUplink.cpp','firmware/ch/src/NodeCache.cpp']
temp=tempfile.TemporaryDirectory(prefix="gld-alarm-host-")
folder=Path(temp.name)
fixture=folder/"compat"; fixture.mkdir()
p=folder/"case.cpp"; p.write_text(program,encoding="utf8")
exe=folder/("case.exe" if os.name=="nt" else "case")
headers=['firmware/gld/include/GldFrameBuilder.h','firmware/shared/include/GldPayload.h','firmware/shared/include/GldRecord.h','firmware/shared/include/AppFrame.h','firmware/shared/include/GldCrypto.h','firmware/shared/include/ProtocolConstants.h','firmware/ch/include/ChUplink.h','firmware/ch/include/NodeCache.h']
for f in headers+files:
 text=(root/f).read_text(encoding='utf8'); count=text.count('namespace pgl::protocol {')+text.count('namespace pgl::gld {')+text.count('namespace pgl::ch {'); assert count==1
 text=text.replace('namespace pgl::protocol {','namespace pgl { namespace protocol {').replace('namespace pgl::gld {','namespace pgl { namespace gld {').replace('namespace pgl::ch {','namespace pgl { namespace ch {')+'\n}\n'
 (fixture/Path(f).name).write_text(text,encoding='utf8')
cmd=[str(compiler),'-std=c++17','-static','-include','initializer_list','-I'+str(fixture),str(p)]+[str(fixture/Path(f).name) for f in files]+['-o',str(exe)]
for workflow,atex in [(1,1),(1,0),(0,1),(0,0)]:
 subprocess.run(cmd[:-2]+['-DPGL_GLD_DATASET_WORKFLOW='+str(workflow),'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX='+str(atex)]+cmd[-2:],check=True,env=env,timeout=60)
 print('workflow=',workflow,'atex=',atex,flush=True);subprocess.run([str(exe)],check=True,env=env,timeout=30)
