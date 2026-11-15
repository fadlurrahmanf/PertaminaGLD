"""Build and run the actual monitorlink against fake ESP-NOW, without hardware."""
from pathlib import Path
import os
import subprocess
import tempfile
here = Path(__file__).resolve().parent
compiler_dir = Path.home() / '.platformio/packages/toolchain-gccmingw32/bin'
compiler = compiler_dir / 'g++.exe'
env = dict(os.environ, PATH=str(compiler_dir) + os.pathsep + os.environ.get('PATH', ''))
with tempfile.TemporaryDirectory(prefix='lt_monitor_test_') as tmp:
    exe = Path(tmp) / 'monitorlink.exe'
    command = [str(compiler), '-std=c++17', '-mno-ms-bitfields',
               '-I' + str(here / 'fakes'), '-I' + str(here.parents[1] / 'CH/tests/fakes'),
               str(here / 'test_monitorlink.cpp'), '-o', str(exe)]
    subprocess.run(command, check=True, env=env)
    subprocess.run([str(exe)], check=True, env=env)
