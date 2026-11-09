"""Parsing, temporary files and inert Win32 mocks; never invokes native WLAN/dialog."""
import ctypes
from ctypes import wintypes
import importlib.util
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from xml.etree import ElementTree

APP=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inert_workflow_platform',APP/'workflow_platform.py')
platform=importlib.util.module_from_spec(spec);spec.loader.exec_module(platform)


class PlatformBoundaries(unittest.TestCase):
    def test_route_probe_matches_windows_adapter_guid_string_with_braces(self):
        calls=[]
        def runner(arguments, **_kwargs):
            calls.append(arguments)
            return type('Result', (), {'returncode':0,'stdout':'READY\n'})()
        identifier=uuid.UUID('f93d7bbf-ba5f-403f-af23-497eb98816f7')
        guid=platform._GUID.from_buffer_copy(identifier.bytes_le)
        self.assertTrue(platform.WindowsWorkflowPlatform(runner=runner)._route_ready(guid))
        self.assertIn("$g='{f93d7bbf-ba5f-403f-af23-497eb98816f7}'", calls[0][-1])

    def test_scan_candidates_are_not_verified_devices_and_never_include_bssid(self):
        text='SSID 1 : ITB Guest\nSSID 2 : GLD-DATASET-1002\n BSSID 1 : 00:11:22\nSSID 3 : GLD-DATASET-10af\nSSID 4 : GLD-DATASET-1002\nSSID 5 : GLD-DATASET-1002;cmd\n'
        self.assertEqual(platform.parse_scan(text),[
            {'ssid':'GLD-DATASET-1002','device_id':'1002','name':'GLD-1002'},
            {'ssid':'GLD-DATASET-10af','device_id':'10AF','name':'GLD-10AF'}])
        for value in ('ITB Guest','GLD-DATASET-12345','GLD-DATASET-1002\nother','GLD-DATASET-1002;cmd',None):
            with self.subTest(value=value),self.assertRaises(ValueError):platform.validate_ssid(value)

    def test_profile_uses_exact_ssid_and_escapes_password_without_temp_files(self):
        xml=platform.profile_xml('GLD-DATASET-1002','fake<&12345')
        tree=ElementTree.fromstring(xml);ns={'w':'http://www.microsoft.com/networking/WLAN/profile/v1'}
        self.assertEqual(tree.find('w:name',ns).text,'GLD-DATASET-1002')
        self.assertEqual(tree.find('.//w:keyMaterial',ns).text,'fake<&12345')
        self.assertEqual(tree.find('w:connectionMode',ns).text,'manual')
        for value in ('short', 'A'*64,'bad\nvalue','bad\x00value'):
            with self.subTest(length=len(value)),self.assertRaises(ValueError):platform.profile_xml('GLD-DATASET-1002',value)

    def test_file_selection_rejects_overwrite_relative_and_wrong_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder);old=parent/'old.csv';old.write_bytes(b'keep this CSV')
            for value in (str(old),'relative.csv',str(parent/'bad.txt'),str(parent/'missing'/'data.csv')):
                with self.subTest(value=value),self.assertRaises(ValueError):platform.WindowsWorkflowPlatform.validate_file(value)
            self.assertEqual(old.read_bytes(),b'keep this CSV')
            target=parent/'new.csv'
            self.assertEqual(platform.WindowsWorkflowPlatform.validate_file(str(target)),str(target.resolve()))
            self.assertFalse(target.exists())
            self.assertEqual([n.name for n in parent.iterdir()],['old.csv'])

    def test_ambiguous_multi_adapter_ssid_is_not_reported_as_one_connection(self):
        result=type('Result',(),{'returncode':0,'stdout':'Name : A\nSSID : OTHER\nName : B\nSSID : GLD-DATASET-1002\n'})()
        self.assertEqual(platform.WindowsWorkflowPlatform(runner=lambda *a,**k:result).current_ssid(),'')


class NativeFunction:
    def __init__(self, callback):self.callback=callback
    def __call__(self,*arguments):return self.callback(*arguments)


class InertWlan:
    """Allocates real ctypes layouts but never loads/calls an operating-system DLL."""
    def __init__(self, interfaces, networks=None, queries=None):
        self.interfaces=interfaces;self.networks=networks or {};self.queries=queries or {}
        self.calls=[];self.memory={};self.freed=[];self.closed=0
        self.enum_error=0;self.profile_error=0;self.connect_error=0
        self.scan_errors={};self.refresh_errors={};self.query_error=None;self.short_query=False
        self.profile_info={};self.profile_list_error=0;self.profile_writes=[]
        for name,callback in [('WlanOpenHandle',self.open),('WlanEnumInterfaces',self.enum),('WlanScan',self.refresh),
            ('WlanGetAvailableNetworkList',self.available),('WlanQueryInterface',self.query),
            ('WlanGetProfileList',self.profiles),
            ('WlanSetProfile',self.profile),('WlanConnect',self.connect),
            ('WlanFreeMemory',self.free),('WlanCloseHandle',self.close)]:
            setattr(self,name,NativeFunction(callback))

    @staticmethod
    def guid(value):return ctypes.cast(value,ctypes.POINTER(platform._GUID)).contents.a

    def allocation(self,size,out):
        memory=ctypes.create_string_buffer(size);address=ctypes.addressof(memory)
        self.memory[address]=memory
        ctypes.cast(out,ctypes.POINTER(ctypes.c_void_p))[0]=ctypes.c_void_p(address)
        return address

    def open(self,version,reserved,actual,handle):
        ctypes.cast(handle,ctypes.POINTER(wintypes.HANDLE))[0]=wintypes.HANDLE(9);return 0

    def enum(self,handle,reserved,out):
        address=self.allocation(8+len(self.interfaces)*ctypes.sizeof(platform._Interface),out)
        ctypes.c_uint32.from_address(address).value=len(self.interfaces)
        for index,(guid,state) in enumerate(self.interfaces):
            value=platform._Interface.from_address(address+8+index*ctypes.sizeof(platform._Interface))
            value.guid.a=guid;value.state=state
        return self.enum_error

    @staticmethod
    def set_ssid(value,ssid):
        raw=ssid.encode('ascii');value.length=len(raw)
        for index,character in enumerate(raw):value.value[index]=character

    def available(self,handle,guid,flags,reserved,out):
        identifier=self.guid(guid);self.calls.append(('visible',identifier))
        networks=self.networks.get(identifier,[])
        address=self.allocation(8+len(networks)*ctypes.sizeof(platform._AvailableNetwork),out)
        ctypes.c_uint32.from_address(address).value=len(networks)
        for index,(ssid,quality,connectable) in enumerate(networks):
            value=platform._AvailableNetwork.from_address(address+8+index*ctypes.sizeof(platform._AvailableNetwork))
            self.set_ssid(value.ssid,ssid);value.bss=1;value.quality=quality;value.connectable=connectable
        return self.scan_errors.get(identifier,0)

    def refresh(self,handle,guid,ssid,ie,reserved):
        identifier=self.guid(guid);self.calls.append(('scan',identifier))
        assert ssid is None and ie is None and reserved is None
        return self.refresh_errors.get(identifier,0)

    def query(self,handle,guid,opcode,reserved,size,out,kind):
        identifier=self.guid(guid);self.calls.append(('query',identifier));assert opcode==7
        sequence=self.queries.get(identifier,['GLD-DATASET-1002'])
        ssid=sequence.pop(0) if len(sequence)>1 else sequence[0]
        if ssid is None:return 5023
        address=self.allocation(ctypes.sizeof(platform._Connection),out)
        value=platform._Connection.from_address(address);value.state=1
        self.set_ssid(value.association.ssid,ssid)
        ctypes.cast(size,ctypes.POINTER(wintypes.DWORD))[0]=4 if self.short_query else ctypes.sizeof(value)
        return self.query_error or 0

    def profiles(self,handle,guid,reserved,out):
        identifier=self.guid(guid);self.calls.append(('profiles',identifier))
        profiles=self.profile_info.get(identifier,[])
        address=self.allocation(8+len(profiles)*ctypes.sizeof(platform._ProfileInfo),out)
        ctypes.c_uint32.from_address(address).value=len(profiles)
        for index,(name,flags) in enumerate(profiles):
            value=platform._ProfileInfo.from_address(address+8+index*ctypes.sizeof(platform._ProfileInfo))
            value.name=name;value.flags=flags
        return self.profile_list_error

    def profile(self,handle,guid,flags,xml,security,overwrite,reserved,reason):
        identifier=self.guid(guid);self.calls.append(('profile',identifier))
        self.profile_writes.append((identifier,flags,security,overwrite))
        # Model the real ERROR_ALREADY_EXISTS failure for a type mismatch,
        # even when overwrite is enabled. Never store/log profile XML or key.
        existing=[scope for name,scope in self.profile_info.get(identifier,[]) if name=='GLD-DATASET-1002']
        if existing and existing[0]!=flags:return 183
        return self.profile_error

    def connect(self,handle,guid,parameters,reserved):
        self.calls.append(('connect',self.guid(guid)))
        value=ctypes.cast(parameters,ctypes.POINTER(platform._Parameters)).contents
        assert value.profile=='GLD-DATASET-1002' and value.mode==0 and value.bss==1
        return self.connect_error

    def free(self,pointer):
        address=pointer.value;assert address in self.memory and address not in self.freed
        self.freed.append(address)

    def close(self,*arguments):self.closed+=1;return 0


class NativeAdapterSelection(unittest.TestCase):
    target='GLD-DATASET-1002'

    def run_join(self,api,password='DUMMY_ONLY_123',route_probe=lambda _guid: True):
        now=[0.0]
        def sleep(seconds):now[0]+=seconds
        with patch('ctypes.WinDLL',return_value=api):
            try:
                return platform.WindowsWorkflowPlatform(clock=lambda:now[0],sleep=sleep,
                    route_probe=route_probe).join(self.target,password)
            finally:
                self.assertEqual(api.closed,1)
                self.assertEqual(set(api.memory),set(api.freed),'all API allocations freed on every branch')

    def test_win64_abi(self):
        self.assertEqual(ctypes.sizeof(ctypes.c_void_p),8)
        for layout,size in [(platform._GUID,16),(platform._Interface,532),(platform._SSID,36),
            (platform._AvailableNetwork,628),(platform._Association,68),(platform._Connection,604),
            (platform._Parameters,40),(platform._ProfileInfo,516)]:
            with self.subTest(layout=layout.__name__):self.assertEqual(ctypes.sizeof(layout),size)
        self.assertEqual(platform._AvailableNetwork.ssid.offset,512)
        self.assertEqual(platform._Connection.association.offset,520)
        self.assertEqual(platform._Association.phy.offset,48)

    def test_skips_disabled_first_adapter_and_checks_only_selected_guid(self):
        api=InertWlan([(0x1111,0),(0x2222,4)],{0x2222:[(self.target,80,True)]},
                     {0x2222:[None,self.target]})
        self.assertEqual(self.run_join(api),{'ssid':self.target,'associated':True})
        self.assertEqual(api.calls,[('visible',0x2222),('profiles',0x2222),('profile',0x2222),('connect',0x2222),
                                   ('query',0x2222),('query',0x2222),('query',0x2222)])

    def test_does_not_choose_adapter_that_cannot_see_target(self):
        api=InertWlan([(1,4),(2,4)],{1:[('OTHER',99,True)],2:[(self.target,30,True)]})
        self.run_join(api)
        self.assertIn(('connect',2),api.calls);self.assertNotIn(('connect',1),api.calls)

    def test_prefers_disconnected_adapter_preserving_other_network(self):
        api=InertWlan([(1,1),(2,4)],{1:[(self.target,100,True)],2:[(self.target,20,True)]},
                     {1:['OTHER'],2:[self.target]})
        self.run_join(api)
        self.assertEqual([entry for entry in api.calls if entry[0]=='connect'],[('connect',2)])

    def test_existing_target_connection_does_not_rewrite_profile_or_reconnect(self):
        api=InertWlan([(1,1)],queries={1:[self.target]})
        self.run_join(api);self.assertEqual(api.calls,[('query',1),('query',1)])

    def test_associated_hotspot_waits_for_delayed_dhcp_route(self):
        api=InertWlan([(1,1)],queries={1:[self.target]})
        probes=[]
        def route(guid):
            probes.append(InertWlan.guid(ctypes.byref(guid)))
            return len(probes)==3
        self.assertEqual(self.run_join(api,route_probe=route),{'ssid':self.target,'associated':True})
        self.assertEqual(probes,[1,1,1])
        self.assertFalse(any(call[0] in ('profile','connect') for call in api.calls))

    def test_association_without_route_fails_before_websocket(self):
        api=InertWlan([(1,1)],queries={1:[self.target]})
        with self.assertRaises(platform.WorkflowNetworkNotReady) as failure:
            self.run_join(api,route_probe=lambda _guid: False)
        self.assertEqual(failure.exception.workflow_code,'wifi_route_not_ready')
        self.assertFalse(any(call[0] in ('profile','connect') for call in api.calls))

    def test_changed_association_during_route_wait_fails_closed(self):
        api=InertWlan([(1,1)],queries={1:[self.target,self.target,None]})
        with self.assertRaises(platform.WorkflowNetworkNotReady):
            self.run_join(api,route_probe=lambda _guid: False)

    def test_wrong_adapter_association_cannot_confirm_selected_connection(self):
        api=InertWlan([(1,4),(2,4)],{1:[(self.target,90,True)],2:[(self.target,20,True)]},
                     {1:['OTHER'],2:[self.target]})
        with self.assertRaisesRegex(RuntimeError,'belum terhubung'):self.run_join(api)
        self.assertEqual([entry for entry in api.calls if entry[0]=='connect'],[('connect',1)])
        self.assertNotIn(('query',2),api.calls)

    def test_no_connect_for_unavailable_transitional_or_unconnectable_target(self):
        for interfaces,networks in [([],{}),([(1,0)],{}),([(1,5)],{}),
            ([(1,4)],{1:[(self.target,90,False)]})]:
            with self.subTest(interfaces=interfaces):
                api=InertWlan(interfaces,networks)
                with self.assertRaises(RuntimeError):self.run_join(api)
                self.assertFalse(any(entry[0] in ('profile','connect') for entry in api.calls))

    def test_native_failures_release_memory_and_never_retry_connect(self):
        for attribute,error in [('enum_error',5),('profile_list_error',5),('profile_error',5),('connect_error',5023),
                                ('query_error',5),('short_query',True)]:
            with self.subTest(failure=attribute):
                api=InertWlan([(1,4),(2,4)],{1:[(self.target,90,True)],2:[(self.target,80,True)]})
                setattr(api,attribute,error)
                with self.assertRaises(RuntimeError):self.run_join(api)
                self.assertLessEqual(len([entry for entry in api.calls if entry[0]=='connect']),1)

    def test_failed_network_query_does_not_select_that_adapter(self):
        api=InertWlan([(1,4),(2,4)],{1:[(self.target,90,True)],2:[(self.target,80,True)]})
        api.scan_errors[1]=5;self.run_join(api)
        self.assertEqual([entry for entry in api.calls if entry[0]=='connect'],[('connect',2)])

    def test_existing_profile_path_omits_secret_profile_write(self):
        api=InertWlan([(1,4)],{1:[(self.target,90,True)]})
        self.run_join(api,password='')
        self.assertNotIn(('profile',1),api.calls)
        self.assertNotIn(('profiles',1),api.calls)

    def test_existing_exact_all_user_profile_preserves_scope_avoiding_error183(self):
        api=InertWlan([(1,4)],{1:[(self.target,90,True)]})
        api.profile_info[1]=[('UNRELATED',2),(self.target,0)]
        self.run_join(api)
        self.assertEqual(api.profile_writes,[(1,0,None,True)])
        self.assertEqual([entry for entry in api.calls if entry[0]=='connect'],[('connect',1)])

    def test_new_and_existing_per_user_profiles_remain_per_user(self):
        for profiles in [[],[('UNRELATED',0)],[(self.target,2)]]:
            with self.subTest(profiles=profiles):
                api=InertWlan([(1,4)],{1:[(self.target,90,True)]});api.profile_info[1]=profiles
                self.run_join(api);self.assertEqual(api.profile_writes,[(1,2,None,True)])

    def test_policy_unknown_or_ambiguous_profile_cannot_be_overwritten(self):
        for profiles,message in [([(self.target,1)],'Group Policy'),([(self.target,3)],'Group Policy'),
            ([(self.target,4)],'Jenis profil'),([(self.target,0),(self.target,2)],'Jenis profil')]:
            with self.subTest(profiles=profiles):
                api=InertWlan([(1,4)],{1:[(self.target,90,True)]});api.profile_info[1]=profiles
                with self.assertRaisesRegex(RuntimeError,message):self.run_join(api)
                self.assertFalse(api.profile_writes)
                self.assertFalse(any(entry[0]=='connect' for entry in api.calls))

    def test_profile_race_error183_stops_without_scope_retry_or_connect(self):
        api=InertWlan([(1,4)],{1:[(self.target,90,True)]});api.profile_error=183
        with self.assertRaisesRegex(RuntimeError,'berubah atau bertabrakan'):self.run_join(api)
        self.assertEqual(len(api.profile_writes),1)
        self.assertFalse(any(entry[0]=='connect' for entry in api.calls))

    def test_scan_requests_usable_guids_and_waits_before_reading_cache(self):
        api=InertWlan([(1,0),(2,1),(3,4),(4,5)]);events=[]
        def runner(arguments,**kwargs):
            self.assertEqual(arguments,['netsh','wlan','show','networks','mode=bssid'])
            self.assertEqual(events,[('wait',4.0)])
            self.assertEqual(api.calls,[('scan',2),('scan',3)])
            self.assertEqual(api.closed,1)
            return type('Result',(),{'returncode':0,'stdout':'SSID 1 : GLD-DATASET-1002\n'})()
        with patch('ctypes.WinDLL',return_value=api):
            result=platform.WindowsWorkflowPlatform(runner=runner,sleep=lambda seconds:events.append(('wait',seconds))).scan()
        self.assertEqual(result,[{'ssid':self.target,'device_id':'1002','name':'GLD-1002'}])
        self.assertEqual(set(api.memory),set(api.freed))
        self.assertFalse(any(item[0] in ('profile','connect') for item in api.calls))

    def test_scan_failure_closes_handle_without_reading_stale_cache(self):
        api=InertWlan([(1,4)]);api.refresh_errors[1]=5
        def unexpected(*args,**kwargs):self.fail('failure must not read stale cache or wait')
        with patch('ctypes.WinDLL',return_value=api),self.assertRaisesRegex(RuntimeError,'izin lokasi'):
            platform.WindowsWorkflowPlatform(runner=unexpected,sleep=unexpected).scan()
        self.assertEqual(api.closed,1);self.assertEqual(set(api.memory),set(api.freed))

    def test_scan_can_use_second_adapter_when_first_refresh_fails(self):
        api=InertWlan([(1,4),(2,4)]);api.refresh_errors[1]=5
        result=type('Result',(),{'returncode':0,'stdout':'SSID 1 : GLD-DATASET-1002\n'})()
        with patch('ctypes.WinDLL',return_value=api):
            found=platform.WindowsWorkflowPlatform(runner=lambda *a,**k:result,sleep=lambda _:None).scan()
        self.assertEqual(len(found),1);self.assertEqual(api.calls,[('scan',1),('scan',2)])


if __name__=='__main__':unittest.main()
