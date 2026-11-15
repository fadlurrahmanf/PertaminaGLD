"""Host round-trip coverage for the actual shared command codec and AppFrame."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SHARED=ROOT/'firmware/shared'
TEST=ROOT/'firmware/tests/node_command_route_test.cpp'

def old_namespace(text):
    # Bundled legacy MinGW does not understand C++17 nested namespace syntax.
    text=re.sub(r'namespace ([\w]+(?:::\w+)+) \{ (namespace \w+ = [\w:]+;) \}', lambda m:' '.join('namespace '+part+' {' for part in m[1].split('::'))+' '+m[2]+' '+'}'*len(m[1].split('::')),text)
    text=re.sub(r'namespace ([\w]+(?:::\w+)+) \{', lambda m:' '.join('namespace '+part+' {' for part in m[1].split('::')),text)
    return re.sub(r'\}  // namespace ([\w]+(?:::\w+)+)',lambda m:'}'*len(m[1].split('::'))+' // namespace '+m[1],text)

def compiler():
    fallback=Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe'
    return os.environ.get('CXX') or shutil.which('g++') or (str(fallback) if fallback.is_file() else None)

@unittest.skipUnless(compiler(),'C++ compiler required for route codec host test')
class RouteCodecHostTest(unittest.TestCase):
    def test_round_trip_and_mutation_controls(self):
        cxx=compiler();env=os.environ.copy();env['PATH']=str(Path(cxx).parent)+os.pathsep+env.get('PATH','')
        header=(SHARED/'include/ServerNodeCommandRoute.h').read_text(encoding='utf8')
        ttl='writeServerNodeCommandU16Be(&out[4], ttlSec);'
        duplicate='if (hopList[j] == hopList[i]) return false;'
        self.assertEqual(header.count(ttl),1);self.assertEqual(header.count(duplicate),1)
        with tempfile.TemporaryDirectory(prefix='gld-route-host-') as d:
            d=Path(d)
            for name in ('ProtocolConstants.h','AppFrame.h'):
                (d/name).write_text(old_namespace((SHARED/'include'/name).read_text(encoding='utf8')),encoding='utf8')
            (d/'AppFrame.cpp').write_text(old_namespace((SHARED/'src/AppFrame.cpp').read_text(encoding='utf8')),encoding='utf8')
            (d/'test.cpp').write_text(old_namespace(TEST.read_text(encoding='utf8')),encoding='utf8')
            for label,body in [('original',header),('ttl_mutant',header.replace(ttl,'writeServerNodeCommandU16Be(&out[4], 0);')),('duplicate_hop_mutant',header.replace(duplicate,'if (hopList[j] == hopList[i]) return true;'))]:
                with self.subTest(case=label):
                    (d/'ServerNodeCommandRoute.h').write_text(old_namespace(body),encoding='utf8')
                    exe=d/('test.exe' if os.name=='nt' else 'test')
                    cmd=[cxx,'-std=c++17','-I'+str(d),str(d/'test.cpp'),str(d/'AppFrame.cpp'),'-o',str(exe)]
                    if os.name=='nt':cmd.insert(1,'-static')
                    compiled=subprocess.run(cmd,env=env,capture_output=True,timeout=60)
                    self.assertEqual(compiled.returncode,0,compiled.stderr.decode(errors='replace')[:2000])
                    result=subprocess.run([str(exe)],env=env,capture_output=True,timeout=30)
                    if label=='original':
                        self.assertEqual(result.returncode,0,result.stdout.decode(errors='replace'))
                    else:
                        self.assertNotEqual(result.returncode,0,'route codec mutation was not detected')

if __name__=='__main__':unittest.main()
