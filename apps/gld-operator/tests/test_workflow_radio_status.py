"""Optional ATEX radio metadata; no hardware, Wi-Fi or credentials."""
import tempfile,unittest
from pathlib import Path
from test_dataset_workflow import Device, Platform, Clock, PASSWORD
from dataset_workflow import DatasetWorkflowService

class TaggedDevice(Device):
    def __init__(self, clock, value=None, include=True):
        super().__init__(clock); self.value=value; self.include=include
    def hello(self):
        data=super().hello()
        if self.include:data["radio_auto_tx"]=self.value
        return data
    def status(self,peer):
        super().status(peer)
        if self.include:peer.messages[-1]["radio_auto_tx"]=self.value

class RadioStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.clock=Clock();self.device=TaggedDevice(self.clock,False)
        self.platform=Platform(self.tmp.name)
        self.service=DatasetWorkflowService(Path(self.tmp.name)/"out",self.platform,websocket_factory=self.device.factory,clock=self.clock,autostart_worker=False,command_timeout=2,silence_timeout=3)
    def tearDown(self):
        self.service.disconnect();self.tmp.cleanup()
    def connect(self):
        self.service.scan();self.service.select("1002");return self.service.connect("1002",PASSWORD)
    def test_hello_fresh_ttl_disconnect_and_legacy_unknown(self):
        state=self.connect();self.assertIs(state["radio_auto_tx"],False)
        self.clock.advance(30.1);self.assertIsNone(self.service.snapshot()["radio_auto_tx"])
        self.service.disconnect();self.assertIsNone(self.service.snapshot()["radio_auto_tx"])
        self.device.value=True;self.device.include=False
        self.service.scan();self.service.select("1002");self.assertIsNone(self.service.connect("1002",PASSWORD)["radio_auto_tx"])
    def test_changed_session_invalidates_old_observation(self):
        self.connect(); engine=self.service._engine
        self.assertIs(self.service.snapshot()["radio_auto_tx"], False)
        engine.session_id = "new-session"; engine._emit()
        self.assertIsNone(self.service.snapshot()["radio_auto_tx"])
    def test_malformed_optional_field_is_unknown_without_breaking_connection(self):
        self.device.value="true";state=self.connect();self.assertTrue(state["connected"]);self.assertIsNone(state["radio_auto_tx"])
    def test_identity_mismatch_never_updates_radio_state(self):
        self.connect();engine=self.service._engine
        self.clock.advance(31);self.assertIsNone(self.service.snapshot()["radio_auto_tx"])
        # Unvalidated messages cannot become a current status report.
        message=self.device.hello();message["device_id"]="1003";message["radio_auto_tx"]=True
        engine._observe_radio_auto_tx(message)
        self.assertIsNone(engine._snapshot()["radio_auto_tx_observed"])
    def test_status_refresh_after_qc_change_and_unknown_when_absent(self):
        self.connect();self.service.choose_file();self.service.configure(dict(label="fixture",mode="direct",fields=dict(prediction=False,gain=False,status=False,timing=False)));self.service.lock(True);self.service.start()
        self.device.value=True;self.device.status(self.device.peer)
        while self.device.peer.messages:self.service._engine._step()
        self.assertIs(self.service.snapshot()["radio_auto_tx"],True)
        self.device.include=False;self.device.status(self.device.peer)
        while self.device.peer.messages:self.service._engine._step()
        self.assertIsNone(self.service.snapshot()["radio_auto_tx"])
        self.service.stop()
        self.service.lock(False); self.service.disconnect(); self.device.include=True; self.device.value=True
        # Retained session from prior recording is not trusted as the new collector session.
        self.assertIsNone(self.service.connect("1002", PASSWORD)["radio_auto_tx"])
        self.service.disconnect(); self.device = TaggedDevice(self.clock, True)
        self.service._factory = self.device.factory
        self.assertIs(self.service.connect("1002", PASSWORD)["radio_auto_tx"], True)
if __name__=="__main__":unittest.main()
