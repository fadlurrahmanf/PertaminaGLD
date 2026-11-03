"""Actual product bridge; only native file chooser is replaced for unattended QA.

Radio, authenticated WebSocket, controls, device data, persistence, HTTP/SSE and
UI are real. CSV destinations are unique under this run's isolated QA folder.
"""
from pathlib import Path
import sys, json, uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'apps/gld-operator'))
import bridge
from workflow_platform import WindowsWorkflowPlatform
from dataset_workflow import DatasetWorkflowService
OUT=HERE/'real-device';OUT.mkdir(exist_ok=True)
class QaFilePlatform(WindowsWorkflowPlatform):
    def choose_file(self):
        return str(OUT/('gld1002-'+uuid.uuid4().hex[:10]+'.csv'))
bridge.DATASET_OUTPUT_DIR=OUT/'private'
bridge.SESSION_LOG_DIR=OUT/'logs'
bridge.dataset_workflow_service=DatasetWorkflowService(OUT/'private',QaFilePlatform(),
    lambda event:bridge.events.emit('dataset_workflow',event))
if __name__=='__main__':sys.exit(bridge.main())
