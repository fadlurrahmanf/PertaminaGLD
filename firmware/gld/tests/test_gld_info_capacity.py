"""Check GLD1 GET_INFO JSON capacity using actual capability source and max strings."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
MAIN=(ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf-8')
COMPILER=Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe'

class InfoCapacity(unittest.TestCase):
    def test_full_gld1_info_with_long_network_fields(self):
        caps=MAIN.split('void addCapabilities(JsonObject caps) {',1)[1].split('\n}',1)[0]
        size=re.search(r'void emitInfoJson\(\)\s*\{.*?StaticJsonDocument<(\d+)> doc;',MAIN,re.S).group(1)
        source=r'''#include <ArduinoJson.h>
#include <cstring>
#define PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 1
#define PGL_GLD_BOARD_PROFILE_GLD2 0
void addCapabilities(JsonObject caps) {CAPS
}
int main(){ StaticJsonDocument<CAPACITY> d; char id[17],ssid[33],host[65],user[33],root[65],ch[5];
memset(id,'i',16);id[16]=0;memset(ssid,'s',32);ssid[32]=0;memset(host,'h',64);host[64]=0;memset(user,'u',32);user[32]=0;memset(root,'r',64);root[64]=0;memset(ch,'c',4);ch[4]=0;
d["deviceId"]=id;d["nodeId"]=1;d["targetChId"]=ch;d["firmwareName"]="GLD";d["firmwareVersion"]="0.8.36";d["protocolVersion"]=1;d["boardProfile"]="GLD1";d["mode"]="inference";d["batteryServiceHold"]=false;d["baud"]=115200;d["sensorCount"]=8;
JsonObject m=d.createNestedObject("modbus");m["available"]=false;m["ready"]=false;JsonObject p=d.createNestedObject("pcf8574");p["available"]=false;p["ready"]=false;p["allLoadSwitchesOn"]=false;JsonObject s=d.createNestedObject("sensorPower");s["available"]=false;s["ready"]=false;s["commanded"]=true;d["mqttTopicRoot"]=root;
JsonObject l=d.createNestedObject("starLora");l["freqMHz"]=921;l["bwKHz"]=125;l["sf"]=7;l["cr"]=5;l["syncWord"]=52;l["txPowerDbm"]=10;l["preamble"]=8;l["tcxoVoltage"]=1.8;l["xtalVoltage"]=1.8;l["txIntervalMs"]=10000;l["transmitFocus"]=false;l["txTarget"]="ch";l["autoTransmit"]=true;l["manualBeginSupported"]=true;l["runtime"]=true;d["radioReady"]=true;
JsonObject c=d.createNestedObject("appConfig");c["wifiSsid"]=ssid;c["mqttHost"]=host;c["mqttPort"]=1883;c["mqttUser"]=user;c["topicRoot"]=root;c["configValid"]=true;JsonObject sec=d.createNestedObject("security");sec["aesKeyProvisioned"]=true;sec["aesKeyPresent"]=true;sec["aesKeySource"]="nvs";sec["keyId"]=1;sec["selfTestFallbackAllowed"]=false;sec["lastDownlinkCommandId"]=1;
JsonObject capabilities=d.createNestedObject("capabilities");addCapabilities(capabilities);
return d.overflowed() || !capabilities["scanDuringLoRaRx"].is<bool>() || !capabilities["authenticatedDownlink"].is<bool>();}
'''.replace('CAPS',caps).replace('CAPACITY',size)
        env=os.environ.copy(); env['PATH']=str(COMPILER.parent)+os.pathsep+env.get('PATH','')
        with tempfile.TemporaryDirectory(prefix='gld-info-capacity-') as directory:
            cpp=Path(directory)/'main.cpp'; exe=Path(directory)/'test.exe'; cpp.write_text(source,encoding='utf-8')
            subprocess.run([str(COMPILER),'-std=c++11',f'-I{ROOT / "firmware/lib/ArduinoJson/src"}',str(cpp),'-o',str(exe)],check=True,env=env,capture_output=True)
            subprocess.run([str(exe)],check=True,env=env,capture_output=True)

if __name__=='__main__': unittest.main()
