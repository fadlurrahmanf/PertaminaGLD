"""Prove checkout attributes preserve factory checksums on either Git setting."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import unittest


class HandoverGitBytes(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'),'Git fixture requires Git')
    def test_factory_manifest_and_snapshot_survive_both_autocrlf_choices(self):
        root=Path(__file__).resolve().parents[2]
        relative='apps/operator-hub/firmware-packages/gld_model_1_dataset_workflow_wifi/latest/manifest.json'
        raw=(root/relative).read_bytes()
        expected=(root/relative).with_name('manifest.sha256').read_text().split()[0]
        for autocrlf in ('true','false'):
            with self.subTest(autocrlf=autocrlf),tempfile.TemporaryDirectory() as directory:
                temp=Path(directory)
                def git(*args):return subprocess.run(['git','-C',str(temp),*args],check=True,capture_output=True)
                git('init');git('config','core.autocrlf',autocrlf)
                (temp/'.gitattributes').write_bytes((root/'.gitattributes').read_bytes())
                path=temp/relative;path.parent.mkdir(parents=True);path.write_bytes(raw)
                snapshot=temp/'handover/state/history/csv/sample.csv';snapshot.parent.mkdir(parents=True)
                exact=b'header1,header2\r\n"clear,air",1\r\n'
                snapshot.write_bytes(exact)
                git('add','.gitattributes',relative,'handover/state/history/csv/sample.csv')
                out=temp/'checkout';out.mkdir()
                git('checkout-index','--all','--force','--prefix='+out.as_posix()+'/')
                self.assertEqual(hashlib.sha256((out/relative).read_bytes()).hexdigest(),expected)
                self.assertEqual((out/'handover/state/history/csv/sample.csv').read_bytes(),exact)


if __name__=='__main__':unittest.main()
