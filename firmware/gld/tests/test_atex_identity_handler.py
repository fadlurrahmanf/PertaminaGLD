from pathlib import Path
import os, re, subprocess, tempfile, unittest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'firmware/gld/src/GldUnifiedMain.cpp'
CXX = os.environ.get('CXX', r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
def body(source, signature):
    start=source.index(signature); brace=source.index('{', start); depth=0
    for i in range(brace,len(source)):
        if source[i]=='{': depth+=1
        elif source[i]=='}':
            depth-=1
            if depth==0: return source[start:i+1]
    raise AssertionError('missing closing brace')

class IdentityHandler(unittest.TestCase):
    def test_handler_dispatch_and_readonly(self):
        src=SRC.read_text(encoding='utf-8')
        readonly=body(src, 'bool workflowReadOnlyCommand(')
        self.assertIn('case Type::GetAtexIdentityJson:', readonly)
        self.assertIn('#if PGL_GLD_BOARD_PROFILE_GLD_ATEX', readonly)
        dispatch=body(src, 'void handleSerialCommand(')
        self.assertIn('emitInfoJson();', dispatch)
        self.assertIn('emitStatusJson();', dispatch)
        self.assertIn('emitAtexIdentityJson(command.payload);', dispatch)
        self.assertIn('#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW && PGL_GLD_BOARD_PROFILE_GLD_ATEX',dispatch)
        handler=body(src,'void emitAtexIdentityJson(')
        prefix=r'''
#include <cassert>
#include <cstring>
#include <string>
#define ARDUINOJSON_ENABLE_STD_STRING 1
#include <ArduinoJson.h>
using namespace std;
const char* BOARD_PROFILE="GLD ATEX MotherBoardGLDVer2";
const char* GLD_RUNTIME_FIRMWARE_VERSION="1.2.3";
struct { char deviceId[17]="1001"; } runtimeConfig;
namespace pgl { namespace gld { namespace model { const char* PROFILE_ID="model_1"; } } }
int outputs=0; string tag, captured;
template<class T> void rawJsonLine(const char* p, const T& d) { ++outputs; tag=p; captured.clear(); serializeJson(d,captured); }
'''
        suffix=r'''
int main() {
 const char* good="{\"nonce\":\"0123456789abcdef0123456789ABCDEF\"}";
 emitAtexIdentityJson(good); assert(outputs==1 && tag=="GLD_ATEX_IDENTITY_JSON");
 StaticJsonDocument<512> parsed; assert(!deserializeJson(parsed,captured));
 assert(parsed.size()==5 && string(parsed["nonce"].as<const char*>())=="0123456789abcdef0123456789ABCDEF");
 assert(string(parsed["firmwareVersion"].as<const char*>())=="1.2.3");
 assert(string(parsed["boardProfile"].as<const char*>())==BOARD_PROFILE && string(parsed["deviceId"].as<const char*>())=="1001" && string(parsed["modelProfileId"].as<const char*>())=="model_1");
 strcpy(runtimeConfig.deviceId, "12\\\"x"); emitAtexIdentityJson(good);
 parsed.clear(); assert(!deserializeJson(parsed,captured));
 assert(string(parsed["deviceId"].as<const char*>()) == runtimeConfig.deviceId);
 emitAtexIdentityJson(nullptr); emitAtexIdentityJson("{}");
 emitAtexIdentityJson("{\"nonce\":\"0123456789abcdef0123456789abcdeg\"}");
 emitAtexIdentityJson("{\"nonce\":\"0123456789abcdef0123456789abcdef\",\"x\":1}");
 assert(outputs==2);
}
'''
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'test.cpp'; exe=Path(d)/'test.exe'
            f.write_text(prefix+handler+suffix, encoding='utf-8')
            env=dict(os.environ); env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
            subprocess.run([CXX,'-std=c++17','-static','-Wall','-Wextra','-Werror','-I'+str(ROOT/'firmware/lib/ArduinoJson/src'),str(f),'-o',str(exe)],check=True,env=env)
            subprocess.run([str(exe)],check=True,env=env)
if __name__ == '__main__': unittest.main()
