"""Native tests for isolated QC scheduling policy; no runtime integration."""
from pathlib import Path
import os, shutil, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[3]
CXX=os.environ.get('CXX') or shutil.which('g++') or str(Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe')
TEST=r'''
#include "GldAtexQcSchedule.h"
#include <cassert>
using Q=pgl::gld::GldAtexQcSchedule;using A=Q::Action;using S=Q::State;
int main(){
 Q q; Q::Input in{100,true,true,false};
 assert(!q.begin(false,false,true,true,true,true,10,20));
 assert(!q.begin(true,true,true,true,true,true,10,20));
 assert(!q.begin(true,false,false,true,true,true,10,20));
 assert(!q.begin(true,false,true,true,false,true,10,20));
 assert(q.state()==S::Idle&&!q.admissionHeld()); // No hardware or fault for precondition failures.
 assert(q.begin(true,false,true,true,true,true,10,20));assert(q.admissionHeld());
 assert(!q.begin(true,false,true,true,true,true,10,20)); // Dataset/second TX excluded.
 assert(q.next(in)==A::StartTx);assert(q.next(in)==A::None);assert(q.resolve(A::StartTx,true,100));
 in.now=110;in.irq=true;assert(q.next(in)==A::FinishTx);assert(q.resolve(A::FinishTx,true,110));
 in.irq=false;assert(q.next(in)==A::StartRx);assert(q.resolve(A::StartRx,true,111));
 in.now=131;in.irq=true;assert(q.next(in)==A::FinishRx);assert(q.resolve(A::FinishRx,true,131));
 assert(q.state()==S::Idle&&!q.admissionHeld());
 // Focus/test TX must not invent an RX window.
 assert(q.begin(true,false,true,true,true,false,10,0));assert(q.next(in)==A::StartTx);assert(q.resolve(A::StartTx,true,0xfffffff8U));
 in.now=2;in.irq=false;assert(q.next(in)==A::TimeoutTx);assert(q.resolve(A::TimeoutTx,true,2));
 assert(q.state()==S::Fault&&q.admissionHeld());assert(!q.begin(true,false,true,true,true,false,10,0));
 Q focus; assert(focus.begin(true,false,true,true,true,false,10,0));assert(focus.next(in)==A::StartTx);
 assert(focus.resolve(A::StartTx,true,2));in.irq=true;assert(focus.next(in)==A::FinishTx);
 assert(focus.resolve(A::FinishTx,true,3));assert(focus.state()==S::Idle);
 Q power;assert(power.begin(true,false,true,true,true,true,10,20));in.irq=false;assert(power.next(in)==A::StartTx);
 assert(power.resolve(A::StartTx,true,3));in.safePower=false;assert(power.next(in)==A::Abort);
 assert(power.resolve(A::Abort,true,4));assert(power.state()==S::Fault&&power.admissionHeld());
 Q fault;in.safePower=true;assert(fault.begin(true,false,true,true,true,true,10,20));assert(fault.next(in)==A::StartTx);
 assert(fault.resolve(A::StartTx,false,5));assert(fault.state()==S::Fault&&fault.admissionHeld());
}
'''
class Tests(unittest.TestCase):
 def test_schedule(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'test.cpp').write_text(TEST);exe=d/'test.exe';env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env.get('PATH','')
   subprocess.run([CXX,'-std=c++17','-static','-I'+str(ROOT/'firmware/gld/include'),str(d/'test.cpp'),'-o',str(exe)],check=True,env=env)
   subprocess.run([str(exe)],check=True,env=env)
if __name__=='__main__': unittest.main()
