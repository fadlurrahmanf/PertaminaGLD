"""Host NVS journal checks. Uses synthetic ciphertext and fake Preferences.
Run: python firmware/gld/tests/run_atex_pending_zero.py
A host g++ is required; set MINGW_CXX if not on PATH.
"""
from pathlib import Path
import os, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[3]
ARDUINO = '#pragma once\n#include <cstdint>\nstruct ESPClass {void restart(){}}; extern ESPClass ESP;\n'
PREFERENCES = '#pragma once\n#include <cstdint>\n#include <cstddef>\n#include <cstring>\n#include <map>\n#include <string>\n#include <vector>\nenum PreferenceType {PT_INVALID,PT_BLOB,PT_U64};\nextern std::map<std::string,std::vector<uint8_t>> fake;\nextern bool failWrite;\nclass Preferences {\npublic:\n bool begin(const char*,bool){return true;} void end(){}\n bool isKey(const char*k){return fake.count(k);}\n PreferenceType getType(const char*k){return isKey(k)?PT_BLOB:PT_INVALID;}\n size_t getBytesLength(const char*k){return fake[k].size();}\n size_t getBytes(const char*k,void*b,size_t n){if(!isKey(k)||fake[k].size()!=n)return 0;memcpy(b,fake[k].data(),n);return n;}\n size_t putBytes(const char*k,const void*b,size_t n){if(failWrite)return 0;fake[k]=std::vector<uint8_t>((const uint8_t*)b,(const uint8_t*)b+n);return n;}\n uint8_t getUChar(const char*k,uint8_t d){return isKey(k)?fake[k][0]:d;}\n bool getBool(const char*k,bool d){return getUChar(k,d)!=0;}\n uint64_t getULong64(const char*,uint64_t d){return d;}\n size_t putUChar(const char*k,uint8_t v){return putBytes(k,&v,1);}\n size_t putBool(const char*k,bool v){return putUChar(k,v);}\n size_t putULong64(const char*k,uint64_t v){return putBytes(k,&v,sizeof(v));}\n bool remove(const char*k){fake.erase(k);return true;}\n};\n'
CASE = '#include <cassert>\n#include <cstdio>\n#include <map>\n#include <string>\n#include <vector>\n#include "Arduino.h"\n#include "Preferences.h"\n#include "GldModeManager.h"\n#include "AppFrame.h"\nESPClass ESP;\nstd::map<std::string,std::vector<uint8_t>> fake;bool failWrite=false;\nusing namespace pgl::gld;using namespace pgl::protocol;\nGldPendingAlarm makePending(uint8_t conf,uint8_t gas,uint8_t flags=TYPE_GLD_ALARM_BATTERY,uint8_t payloadLen=GLD_ENCRYPTED_PAYLOAD_SIZE){\n GldPendingAlarm p{};p.active=true;p.gasClass=gas;p.confidence=conf;p.sequence=17;\n uint8_t bytes[GLD_ENCRYPTED_PAYLOAD_SIZE]{};auto r=encodeAppFrame(flags,0x1001,0x10,p.sequence,bytes,payloadLen,p.frame,sizeof(p.frame),STAR_MAX_PAYLOAD);assert(r.status==FrameStatus::Ok);p.frameLen=r.size;return p;\n}\nint main(){\n#if PGL_GLD_DATASET_WORKFLOW && PGL_GLD_BOARD_PROFILE_GLD_ATEX\n bool at=true;\n#else\n bool at=false;\n#endif\n auto zero=makePending(0,GLD_GAS_LPG);assert(writeGldPendingAlarm(zero)==at);\n if(at){auto r=readGldPendingAlarm();assert(r.active&&r.confidence==0&&gldPendingAlarmHasFrozenFrame(r));assert(r.frameLen==zero.frameLen && memcmp(r.frame,zero.frame,r.frameLen)==0);\n auto damaged=zero;damaged.frame[2]^=1;assert(!writeGldPendingAlarm(damaged));damaged=zero;damaged.sequence++;assert(!writeGldPendingAlarm(damaged));damaged=zero;damaged.frameLen=0;assert(!writeGldPendingAlarm(damaged));damaged=makePending(0,GLD_GAS_CLEAR);assert(!writeGldPendingAlarm(damaged));damaged=makePending(0,GLD_GAS_LPG,TYPE_GLD_NORMAL_BATTERY);assert(!writeGldPendingAlarm(damaged));damaged=makePending(0,GLD_GAS_LPG,TYPE_GLD_ALARM_BATTERY,1);assert(!writeGldPendingAlarm(damaged));\n fake["pending_v1_a"][5]^=1;assert(!readGldPendingAlarm().active);fake.clear();\n }\n auto normal=makePending(1,GLD_GAS_LPG);assert(writeGldPendingAlarm(normal));auto got=readGldPendingAlarm();assert(got.active&&got.confidence==1);\n failWrite=true;assert(!writeGldPendingAlarm(normal));failWrite=false;assert(readGldPendingAlarm().active);\n fake.clear();uint8_t yes=1,gas=GLD_GAS_LPG,conf=0;fake["pending_alarm"]={yes};fake["pending_gas"]={gas};fake["pending_conf"]={conf};assert(!readGldPendingAlarm().active);\n printf("ATEX workflow=%d passed NVS save/load/corruption controls\\n",int(at));\n}\n'

def main():
    compiler = os.environ.get("MINGW_CXX") or shutil.which("g++") or str(
        Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")
    if not Path(compiler).is_file():
        raise SystemExit("Host C++ compiler not found; set MINGW_CXX")
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).resolve().parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="gld-pending-host-") as temp:
        folder = Path(temp)
        for name, content in (("Arduino.h", ARDUINO), ("Preferences.h", PREFERENCES),
                              ("test.cpp", CASE)):
            (folder / name).write_text(content, encoding="utf8")
        for source, dest in (
            ("firmware/gld/src/GldModeManager.cpp", "GldModeManager.cpp"),
            ("firmware/shared/src/AppFrame.cpp", "AppFrame.cpp"),
            ("firmware/gld/include/GldModeManager.h", "GldModeManager.h"),
            ("firmware/shared/include/ProtocolConstants.h", "ProtocolConstants.h"),
            ("firmware/shared/include/AppFrame.h", "AppFrame.h"),
        ):
            text = (ROOT / source).read_text(encoding="utf8")
            count = text.count("namespace pgl::protocol {") + text.count("namespace pgl::gld {")
            if count != 1:
                raise AssertionError("Unexpected namespace layout: " + source)
            text = text.replace("namespace pgl::protocol {", "namespace pgl { namespace protocol {")
            text = text.replace("namespace pgl::gld {", "namespace pgl { namespace gld {")
            (folder / dest).write_text(text + "\n}\n", encoding="utf8")
        executable = folder / ("test.exe" if os.name == "nt" else "test")
        for label, workflow, atex, gld2 in (
            ("ATEX workflow", 1, 1, 1),
            ("GLD1 workflow", 1, 0, 0),
            ("GLD2 workflow", 1, 0, 1),
            ("ATEX nonworkflow", 0, 1, 1),
            ("GLD1 nonworkflow", 0, 0, 0),
        ):
            command = [str(compiler), "-std=c++17", "-static", "-I" + str(folder),
                       "-DPGL_GLD_DATASET_WORKFLOW=" + str(workflow),
                       "-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=" + str(atex),
                       "-DPGL_GLD_BOARD_PROFILE_GLD2=" + str(gld2),
                       str(folder / "GldModeManager.cpp"), str(folder / "AppFrame.cpp"),
                       str(folder / "test.cpp"), "-o", str(executable)]
            print(label, flush=True)
            subprocess.run(command, check=True, env=env, timeout=60)
            subprocess.run([str(executable)], check=True, env=env, timeout=30)


if __name__ == "__main__":
    main()
