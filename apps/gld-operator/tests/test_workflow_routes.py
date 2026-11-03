"""Inert bridge admission/dispatch checks; no WLAN, COM, dialogs or sockets."""
import unittest
from unittest.mock import patch
from test_wireless_replay_routes import bridge,MemoryHandler,FakeCollector,ORIGIN


class FakeWorkflow:
    def __init__(self):
        self.value={'state':'paused','connected':False,'cleanup_pending':False,'count':8}
        self.calls=[]
    def snapshot(self):return dict(self.value,history=[])
    def __getattr__(self,name):
        def op(*args):self.calls.append((name,args));return self.snapshot()
        return op


class WorkflowRoutes(unittest.TestCase):
    def setUp(self):
        self.workflow=FakeWorkflow();self.direct=FakeCollector('gld-dataset-wifi/1');self.replay=FakeCollector('gld-dataset-wifi/2')
        for collector in (self.direct,self.replay):collector.value.update(connected=False,state='disconnected',recovery_active=False)
        for item in [patch.object(bridge,'BRIDGE_ALLOWED_ORIGINS',{ORIGIN}),patch.object(bridge,'serial_bridges',{}),
                     patch.object(bridge,'dataset_workflow_service',self.workflow),
                     patch.object(bridge,'get_dataset_workflow_service',return_value=self.workflow),
                     patch.object(bridge,'wireless_dataset_collector',self.direct),patch.object(bridge,'wireless_replay_collector',self.replay)]:
            item.start();self.addCleanup(item.stop)

    def request(self,path,payload=None):return MemoryHandler(path,payload).execute()

    def test_all_wizard_actions_dispatch_only_to_workflow_service(self):
        self.assertEqual(self.request('/api/dataset-workflow/state')[0],200)
        for action,payload in [('scan',{}),('select',{'device_id':'1002'}),('connect',{'device_id':'1002','password':'fake-only-password'}),
            ('choose-file',{}),('configure',{'label':'air'}),('lock',{'locked':True}),('start',{}),('pause',{}),('resume',{}),('stop',{}),('continue',{}),('reset',{}),('disconnect',{}),('export',{})]:
            with self.subTest(action=action):self.assertEqual(self.request('/api/dataset-workflow/'+action,payload)[0],200)
        self.assertEqual([n for n,_ in self.workflow.calls],['scan','select','connect','choose_file','configure','lock','start','pause','resume','stop','continue_recording','reset','disconnect','export_csv'])
        self.assertEqual(self.direct.calls,[]);self.assertEqual(self.replay.calls,[])

    def test_paused_and_cleanup_block_other_transports_before_device_access(self):
        with patch.object(bridge,'get_serial_bridge') as serial,patch.object(bridge,'probe_port') as probe,patch.object(bridge,'firmware_upload') as upload:
            for state,cleanup in [('paused',False),('stopped',True)]:
                self.workflow.value.update(state=state,cleanup_pending=cleanup)
                for path,body in [('/api/wireless-dataset/connect',{'password':'fake-only'}),('/api/wireless-replay/connect',{'password':'fake-only'}),
                    ('/api/serial/connect',{'port':'COM-NOT-REAL'}),('/api/serial/port-status?port=COM-NOT-REAL',None),('/api/firmware/upload',{})]:
                    with self.subTest(state=state,path=path):self.assertGreaterEqual(self.request(path,body)[0],400)
            serial.assert_not_called();probe.assert_not_called();upload.assert_not_called()

    def test_workflow_connect_cannot_take_over_existing_capture_or_com(self):
        self.direct.value.update(state='recording',connected=True)
        self.assertGreaterEqual(self.request('/api/dataset-workflow/connect',{'device_id':'1002'})[0],400)
        self.direct.value.update(state='disconnected',connected=False)
        with patch.object(bridge,'serial_bridges',{1:type('Connected',(),{'status':lambda self:{'connected':True}})()}):
            self.assertGreaterEqual(self.request('/api/dataset-workflow/start',{})[0],400)
        self.assertEqual(self.workflow.calls,[])

    def test_unsettled_session_cannot_be_hidden_by_settings_only_state(self):
        self.workflow.value.update(state='idle',connected=False,cleanup_pending=True)
        self.assertTrue(bridge.workflow_in_use())
        self.workflow.value['cleanup_pending']=False
        self.assertFalse(bridge.workflow_in_use())


if __name__=='__main__':unittest.main()
