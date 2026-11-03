"""Characterization audit: no real Windows API, network, dialog or device call."""
from pathlib import Path
import sys,ctypes,tempfile,json
from ctypes import wintypes
from unittest.mock import patch
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'apps/gld-operator'))
from workflow_platform import WindowsWorkflowPlatform
class Native:
 def __init__(self,fn):self.fn=fn
 def __call__(self,*a):return self.fn(*a)
class GUID(ctypes.Structure):
 _fields_=[('a',wintypes.DWORD),('b',wintypes.WORD),('c',wintypes.WORD),('d',ctypes.c_ubyte*8)]
class Interface(ctypes.Structure):
 _fields_=[('guid',GUID),('description',wintypes.WCHAR*256),('state',wintypes.DWORD)]
class Wlan:
 def __init__(self):
  self.memory=ctypes.create_string_buffer(8+ctypes.sizeof(Interface)*2);base=ctypes.addressof(self.memory)
  ctypes.c_uint32.from_address(base).value=2
  first=Interface.from_address(base+8);first.guid.a=0x1111;first.state=0;first.description='Not ready adapter'
  second=Interface.from_address(base+8+ctypes.sizeof(Interface));second.guid.a=0x2222;second.state=4;second.description='Available disconnected adapter'
  self.calls=[]
  self.WlanOpenHandle=Native(self.open);self.WlanEnumInterfaces=Native(self.enum)
  self.WlanSetProfile=Native(lambda h,g,*a:self.calls.append(('profile',ctypes.cast(g,ctypes.POINTER(GUID)).contents.a)) or 0)
  self.WlanConnect=Native(lambda h,g,*a:self.calls.append(('connect',ctypes.cast(g,ctypes.POINTER(GUID)).contents.a)) or 5023)
  self.WlanFreeMemory=Native(lambda *a:None);self.WlanCloseHandle=Native(lambda *a:0)
 def open(self,v,p,version,handle):ctypes.cast(handle,ctypes.POINTER(wintypes.HANDLE))[0]=wintypes.HANDLE(9);return 0
 def enum(self,h,p,out):ctypes.cast(out,ctypes.POINTER(ctypes.c_void_p))[0]=ctypes.c_void_p(ctypes.addressof(self.memory));return 0
api=Wlan();error=None
with patch('ctypes.WinDLL',return_value=api):
 try:WindowsWorkflowPlatform().join('GLD-DATASET-1002','AUDIT_DUMMY_ONLY')
 except RuntimeError as e:error=str(e)
assert api.calls==[('profile',0x1111),('connect',0x1111)] and error
# CurrentSSID parser chooses first adapter's value even when second is target.
platform=WindowsWorkflowPlatform(runner=lambda *a,**k:type('Result',(),{'returncode':0,'stdout':'Name : First\nSSID : OTHER\nName : Second\nSSID : GLD-DATASET-1002\n'})())
assert platform.current_ssid()=='OTHER'
# Verify the actual nested OPENFILENAME layout and buffer handling with an inert DLL.
abi={}
class Dialog:
 def __init__(self,target):self.target=target;self.GetSaveFileNameW=Native(self.save);self.CommDlgExtendedError=Native(lambda:0)
 def save(self,pointer):
  q=pointer._obj;abi.update(size=q.size,actual=ctypes.sizeof(q),file_offset=q.__class__.file.offset,flags=q.flags,maxfile=q.maxfile)
  assert q.size==152 and q.__class__.file.offset==48 and q.maxfile==32768
  address=ctypes.c_void_p.from_address(ctypes.addressof(q)+q.__class__.file.offset).value
  value=ctypes.create_unicode_buffer(str(self.target));ctypes.memmove(address,ctypes.addressof(value),ctypes.sizeof(value));return 1
with tempfile.TemporaryDirectory() as folder:
 target=Path(folder)/'audit.csv';dialog=Dialog(target)
 with patch('ctypes.WinDLL',return_value=dialog):picked=WindowsWorkflowPlatform().choose_file()
 assert picked==str(target.resolve()) and not target.exists()
report={'native_calls_executed':False,'multi_adapter_defect_reproduced':True,'first_guid':api.calls[1][1],'expected_usable_guid':0x2222,'current_ssid_first_only_reproduced':True,'openfilename_win64_abi':abi,'file_picker_mock_success':True}
(ROOT/'tmp/workspace-live-20261103/connection-native-characterization.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
