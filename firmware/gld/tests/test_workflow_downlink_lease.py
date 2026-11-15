"""Real workflow downlink + protocol parsing, with deterministic fake CMAC; no device."""
from pathlib import Path
import os, re, shutil, subprocess, tempfile, unittest

ROOT = Path(__file__).resolve().parents[3]
CXX = os.environ.get('CXX') or shutil.which('g++') or str(Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe')
ARDUINO = '''#pragma once\nclass Stream {public: int available(){return 0;} int read(){return -1;}};\nextern Stream Serial;\n'''
CPP = r'''
#include <Arduino.h>
#include "GldCommandParser.h"
#include "AppFrame.h"
#include "GldCrypto.h"
#include <cassert>
#include <cstring>
#include <cstdarg>
#include <cstdio>
using namespace pgl::gld;
using namespace pgl::protocol;
Stream Serial;
namespace pgl { namespace gld { GldMode gldModeFromString(const char*) {return GldMode::INFERENCE;} } }
// Deterministic stand-in isolates parser control flow, not AES security.
namespace pgl { namespace protocol {
GldCryptoStatus computeAesCmac128(const uint8_t* key,const uint8_t* input,size_t n,uint8_t* out) {
 memset(out,0,16); for(size_t i=0;i<n;i++) out[i%4] ^= input[i];
 for(int i=0;i<4;i++) out[i] ^= key[i]; return GldCryptoStatus::Ok;
}
} }
struct Config { uint16_t lastDownlinkCommandId, nodeId; uint8_t aesKey[16]; bool aesKeyPresent; } runtimeConfig;
unsigned busyLogs=0;
void logPrintf(const char* fmt, ...) { if(strstr(fmt,"rejected=dataset_busy")) ++busyLogs; }
#include "actual_workflow_downlink.inc"
static size_t encodeCommand(uint8_t* out, uint16_t dst, uint16_t cmd, bool validTag=true) {
 uint8_t key[16]={}; uint8_t payload[8]={0x81, 0, uint8_t(cmd>>8), uint8_t(cmd),0,0,0,0};
 uint8_t input[9]={0x00,0x10,uint8_t(dst>>8),uint8_t(dst),0x2a,payload[0],payload[1],payload[2],payload[3]};
 uint8_t mac[16]; computeAesCmac128(key,input,sizeof(input),mac); memcpy(payload+4,mac,4); if(!validTag) payload[4]^=1;
 FrameEncodeResult r=encodeAppFrame(MSG_NODE_DOWNLINK,0x0010,dst,0x2a,payload,8,out,64); assert(r.status==FrameStatus::Ok);return r.size;
}
static void unchanged(uint16_t last, unsigned logs) {
 assert(runtimeConfig.lastDownlinkCommandId==last); assert(busyLogs==logs);
}
int main() {
 runtimeConfig.nodeId=0x1001; runtimeConfig.lastDownlinkCommandId=5; runtimeConfig.aesKeyPresent=true;
 uint8_t frame[64]={}; size_t n=encodeCommand(frame,0x1001,6); uint16_t candidate=5; GldMode mode=GldMode::NULLING;
 // Positive control proves the real parser authenticates and would advance the caller's copy.
 assert(parseLoRaDownlinkCmd(frame,n,0x1001,runtimeConfig.aesKey,true,candidate,mode)); assert(candidate==6);
 reportWorkflowDownlink(frame,n); unchanged(5,1);
 n=encodeCommand(frame,0x1001,6,false); reportWorkflowDownlink(frame,n); unchanged(5,1);
 n=encodeCommand(frame,0x1002,6); reportWorkflowDownlink(frame,n); unchanged(5,1);
 n=encodeCommand(frame,0x1001,5); reportWorkflowDownlink(frame,n); unchanged(5,1);
 n=encodeCommand(frame,0x1001,6); frame[n-1]^=1; reportWorkflowDownlink(frame,n); unchanged(5,1);
 n=encodeCommand(frame,0x1001,6); runtimeConfig.aesKeyPresent=false; reportWorkflowDownlink(frame,n); unchanged(5,1);
 runtimeConfig.aesKeyPresent=true;
 // Compact ACKs have their own real parser; workflow handler does not claim to handle them.
 FrameEncodeResult r=encodeAppFrame(TYPE_ALARM_ACK_COMPACT,0x0010,0x1001,0x2a,nullptr,0,frame,sizeof(frame));assert(r.status==FrameStatus::Ok);
 assert(parseCompactAlarmAck(frame,r.size,0x0010,0x1001,0x2a));
 assert(!parseCompactAlarmAck(frame,r.size,0x0010,0x1001,0x2b));
 assert(!parseCompactAlarmAck(frame,r.size,0x0011,0x1001,0x2a));
 assert(!parseCompactAlarmAck(frame,r.size,0x0010,0x1002,0x2a));
 reportWorkflowDownlink(frame,r.size); unchanged(5,1);
}
'''

def compat(text):
    text=re.sub(r'namespace pgl::(\w+) \{',r'namespace pgl { namespace \1 {',text)
    return re.sub(r'}  // namespace pgl::(\w+)',r'}}  // namespace pgl::\1',text)

def function(source, signature):
    start=source.index(signature); opening=source.index('{',start); depth=1; end=opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}'); end+=1
    return source[start:end]

class WorkflowDownlinkTests(unittest.TestCase):
 def test_lease_and_ack_use_real_parser(self):
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp); (d/'Arduino.h').write_text(ARDUINO)
        for folder in ('firmware/gld/include','firmware/shared/include'):
            for f in (ROOT/folder).glob('*.h'): (d/f.name).write_text(compat(f.read_text(encoding='utf8')),encoding='utf8')
        for src,name in (('firmware/gld/src/GldCommandParser.cpp','parser.cpp'),('firmware/shared/src/AppFrame.cpp','appframe.cpp')):
            (d/name).write_text(compat((ROOT/src).read_text(encoding='utf8')),encoding='utf8')
        actual=function((ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8'),'void reportWorkflowDownlink(')
        (d/'actual_workflow_downlink.inc').write_text(actual,encoding='utf8'); (d/'main.cpp').write_text(CPP,encoding='utf8')
        env=dict(os.environ); env['PATH']=str(Path(CXX).parent)+os.pathsep+env.get('PATH','')
        exe=d/'test.exe'; cmd=[CXX,'-std=c++17','-static','-I'+str(d),str(d/'parser.cpp'),str(d/'appframe.cpp'),str(d/'main.cpp'),'-o',str(exe)]
        subprocess.run(cmd,check=True,env=env); subprocess.run([str(exe)],check=True,env=env)
        # Negative control: mutating the local candidate into a reference must
        # expose the replay-state change and make the harness fail.
        marker='uint16_t candidateCommandId = runtimeConfig.lastDownlinkCommandId;'
        self.assertEqual(actual.count(marker), 1)
        (d/'actual_workflow_downlink.inc').write_text(actual.replace(marker,'uint16_t& candidateCommandId = runtimeConfig.lastDownlinkCommandId;'),encoding='utf8')
        subprocess.run(cmd,check=True,env=env)
        mutant=subprocess.run([str(exe)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertNotEqual(mutant.returncode,0,'unsafe replay-state mutation escaped detection')
if __name__=='__main__': unittest.main()
