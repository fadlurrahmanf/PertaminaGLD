from pathlib import Path
import os, subprocess, tempfile, unittest, re, shutil

ROOT = Path(__file__).resolve().parents[3]
CXX = os.environ.get('CXX', r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
SRC = ROOT / 'firmware/gld/src/GldCommandParser.cpp'
INC = ROOT / 'firmware/gld/include'
SHARED = ROOT / 'firmware/shared/include'
ARDUINO = r'''
#pragma once
#include <deque>
#include <string>
class Stream { std::deque<char> q; public:
 int available() {return (int)q.size();} int read(){if(q.empty()) return -1; unsigned char c=q.front(); q.pop_front(); return c;}
 void feed(const std::string& s){for(char c:s) q.push_back(c);}
};
extern Stream Serial, Serial0;

'''
HARNESS = r'''
#include <Arduino.h>
#include "GldCommandParser.h"
#include "AppFrame.h"
#include "GldCrypto.h"
#include <cassert>
#include <string>
using namespace pgl::gld;
Stream Serial, Serial0;
namespace pgl { namespace protocol {
FrameStatus decodeAppFrame(const uint8_t*, size_t, FrameView&, uint8_t) { return static_cast<FrameStatus>(1); }
GldCryptoStatus computeAesCmac128(const uint8_t*, const uint8_t*, size_t, uint8_t*) { return static_cast<GldCryptoStatus>(1); }
} }
namespace pgl::gld { GldMode gldModeFromString(const char*) { return GldMode::DATASET; } }
int main() {
 GldSerialCommand c;
 const std::string prefix="GET_ATEX_IDENTITY_JSON ";
 const std::string json="{\"nonce\":\"0123456789abcdef0123456789ABCDEF\"}";
 Serial.feed("GET_INFO\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetInfo);
 Serial.feed("GET_STATUS\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetStatus);
 // Backspace edits the input on GLD1 and ATEX; Stream deliberately has no
 // output API, so accidentally restoring secret echo fails compilation.
 Serial.feed("GET_INFX\bO\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetInfo);
 Serial.feed("SET_MODE dataset\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::SetMode && c.mode==GldMode::DATASET);
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 Serial.feed(prefix+json.substr(0,20)); assert(!parseSerialCommand(c));
 Serial.feed(json.substr(20)+"\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetAtexIdentityJson && std::string(c.payload)==json);
 Serial0.feed(prefix+json+"\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetAtexIdentityJson);
 const std::string bad[]={"", "{}", "{\"nonce\":\"0123456789abcdef0123456789abcde\"}", "{\"nonce\":\"0123456789abcdef0123456789abcdeg\"}", json.substr(0,43), json+" ", "{\"nonce\": \"0123456789abcdef0123456789abcdef\"}", json.substr(0,43)+",\"x\":1}"};
 for(const auto& b:bad){Serial.feed(prefix+b+"\n"); assert(!parseSerialCommand(c));}
 Serial.feed("GET_ATEX_IDENTITY_JSON\n"); assert(!parseSerialCommand(c));
 Serial.feed(prefix+json+std::string(512,'x')+"\n"); assert(!parseSerialCommand(c));
 Serial.feed(prefix+json+std::string(1,'\0')+"\n"); assert(!parseSerialCommand(c));
 Serial.feed(std::string(512,'x')); assert(!parseSerialCommand(c));
 Serial0.feed(prefix+json+"\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetAtexIdentityJson);
 Serial.feed("\b\n"+prefix+json+"\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::GetAtexIdentityJson);
#else
 Serial.feed(prefix+json+"\n"); assert(parseSerialCommand(c) && c.type==GldSerialCommandType::Unknown);
#endif
}
'''

class ParserTests(unittest.TestCase):
 def test_profiles(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); (d/'Arduino.h').write_text(ARDUINO); (d/'main.cpp').write_text(HARNESS)
   # MinGW 5 implements the runtime subset but predates C++17 nested-namespace syntax.
   # Rewrite only namespace spelling in temporary copies, keeping parser logic intact.
   def compat(text):
    text = re.sub(r'namespace pgl::(\w+) \{', r'namespace pgl { namespace \1 {', text)
    return re.sub(r'}  // namespace pgl::(\w+)', r'}}  // namespace pgl::\1', text)
   for path in list(INC.glob('*.h')) + list(SHARED.glob('*.h')):
    (d/path.name).write_text(compat(path.read_text(encoding='utf-8')), encoding='utf-8')
   (d/'parser.cpp').write_text(compat(SRC.read_text(encoding='utf-8')))
   harness=HARNESS.replace('namespace pgl::gld { GldMode gldModeFromString(const char*) { return GldMode::DATASET; } }', 'namespace pgl { namespace gld { GldMode gldModeFromString(const char*) { return GldMode::DATASET; } } }')
   (d/'main.cpp').write_text(harness)
   for a,w in [(1,1),(0,1),(1,0)]:
    exe=d/f't{a}{w}.exe'
    cmd=[CXX,'-std=c++17','-static','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={a}',f'-DPGL_GLD_DATASET_WORKFLOW={w}','-DARDUINO_ARCH_ESP32=1',f'-I{d}',f'-I{INC}',f'-I{SHARED}',str(d/'parser.cpp'),str(d/'main.cpp'),'-o',str(exe)]
    env=dict(os.environ); env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
    subprocess.run(cmd,check=True,env=env); subprocess.run([str(exe)],check=True,env=env)

if __name__=='__main__': unittest.main()

