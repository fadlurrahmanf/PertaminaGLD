"""Compile and run actual CH loop with fake time/radio; never opens hardware."""
from pathlib import Path
import os, subprocess, tempfile, shutil
here = Path(__file__).resolve().parent
repo = here.parents[3]
compiler_dir = Path.home() / '.platformio/packages/toolchain-gccmingw32/bin'
compiler = compiler_dir / 'g++.exe'
env = dict(os.environ, PATH=str(compiler_dir) + os.pathsep + os.environ.get('PATH', ''))
def compatible(text):
    # GCC 5 does not parse C++17 nested namespace syntax. This mechanical
    # transformation leaves code and wire behavior unchanged.
    return text.replace('namespace pgl::protocol {', 'namespace pgl { namespace protocol {').replace(
        '}  // namespace pgl::protocol', '} }  // namespace pgl::protocol').replace(
        'namespace pgl::ch::board {', 'namespace pgl { namespace ch { namespace board {').replace(
        '}  // namespace pgl::ch::board', '} } }  // namespace pgl::ch::board')
with tempfile.TemporaryDirectory(prefix='lt_fault_') as temp:
    tmp=Path(temp)
    files={
        here.parent/'src/main.cpp':'dut.cpp',
        repo/'firmware/ch/include/ChBoardPinsRectangle.h':'ChBoardPinsRectangle.h',
        repo/'firmware/shared/include/AppFrame.h':'AppFrame.h',
        repo/'firmware/shared/include/ProtocolConstants.h':'ProtocolConstants.h',
        repo/'firmware/shared/src/AppFrame.cpp':'AppFrame.cpp',
    }
    for src,name in files.items():
        (tmp/name).write_text(compatible(src.read_text(encoding='utf-8')), encoding='utf-8')
    for role,altmac,calibrated in ((1,0,0),(2,0,0),(1,1,0),(1,0,1)):
        exe=tmp/f'fault{role}_{altmac}_{calibrated}.exe'
        cmd=[str(compiler),'-std=c++17','-mno-ms-bitfields',f'-DLT_ROLE={role}',f'-DLT_TEMP_ALT_MAC={altmac}',
             f'-DLT_BATTERY_CALIBRATED={calibrated}',
             '-DLT_BATTERY_EMPTY_MV=3000','-DLT_BATTERY_FULL_MV=4200','-DLT_BATTERY_OFFSET_MV=0',
             '-I'+str(here/'fakes'),'-I'+str(tmp),'-I'+str(here.parent/'include'),
             str(here/'test_fault_loop.cpp'),str(tmp/'AppFrame.cpp'),'-o',str(exe)]
        subprocess.run(cmd,check=True,env=env)
        subprocess.run([str(exe)],check=True,env=env)
