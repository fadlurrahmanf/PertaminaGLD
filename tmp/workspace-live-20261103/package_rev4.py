"""Use unchanged strict packager on versioned rev4 artifacts/receipts."""
from pathlib import Path
import importlib.util,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('strict_workflow_rev4',ROOT/'firmware/tools/package_dataset_workflow.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ARTIFACT_ROOT=ROOT/'firmware/.pio/artifacts/gld-dataset-workflow-wifi-20261103-inference'
module.RECEIPT_ROOT=HERE
module.RECEIPTS={m:f'model{m}-build-receipt.json' for m in (1,2,3)}
if __name__=='__main__':raise SystemExit(module.main())
