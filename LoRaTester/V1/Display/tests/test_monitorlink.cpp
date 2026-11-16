#include <cstdio>
#include <cstring>
#include <vector>
#include <cstdint>
#include "../src/tester_monitor.h"
uint32_t fakeMillis = 1, fakeRandom = 100;
FakeWiFi WiFi;
FakeSerial Serial0;
std::vector<std::vector<uint8_t>> fakeNowTx;
std::vector<std::vector<uint8_t>> fakeNowTargets;
using namespace monitorlink;
using namespace loratester;
static const uint8_t peerA[6] = {1,2,3,4,5,6};
static const uint8_t peerB[6] = {6,5,4,3,2,1};
static int failures = 0;
static void check(bool ok, const char* name) { std::printf("%s %s\n",ok?"PASS":"FAIL",name); if(!ok) ++failures; }
static void reset() {
 latest = NowMessage{}; pending=pendingStatus=pinned=awaitStatus=idlePresence=interrupted=false;ready=true;
 std::memset(peerMac,0,sizeof(peerMac));sessionId=lastRx=lastStatusRx=lastTx=lastDiscover=startedAt=0;
 lastReportSeq=0;hasReportSeq=false;peerBootNonce=0;ignoredSession=0;realtimeStart=false;lastPresenceState=255;std::memset(retiredBootNonces,0,sizeof(retiredBootNonces));retiredBootIndex=0;bootKnown=false;fakeMillis=100;fakeNowTx.clear();fakeNowTargets.clear();
}
static NowMessage msg(uint8_t type, uint32_t boot, uint32_t session=0, uint32_t seq=0, uint8_t state=0) {
 NowMessage m{};m.magic=kNowMagic;m.version=kNowVersion;m.expected=100;m.type=type;m.bootNonce=boot;m.session=session;m.reportSeq=seq;m.state=state;return m;
}
static void receive(const uint8_t* mac,const NowMessage& m) { onReceive(mac,reinterpret_cast<const uint8_t*>(&m),sizeof(m)); }
static void advance(uint32_t ms) { fakeMillis+=ms; poll(); }
int main() {
 reset(); auto a=msg(kNowPresence,11); receive(peerA,a);poll();check(pinned && peerBootNonce==11,"valid presence pins peer");
 auto b=msg(kNowPresence,22);receive(peerB,b);poll();check(peerBootNonce==11 && std::memcmp(peerMac,peerA,6)==0,"foreign peer cannot replace pin");
 auto bad=msg(kNowPresence,0);receive(peerA,bad);check(peerBootNonce==11,"zero boot nonce rejected");
 auto first=msg(kNowStatus,11,31,10,2);receive(peerA,first);poll();check(sessionId==31 && latest.reportSeq==10 && latest.state==2,"resume accepted from pinned peer");
 auto older=msg(kNowStatus,11,31,9,3);receive(peerA,older);check(latest.reportSeq==10 && latest.state==2,"out of order status rejected");
 auto duplicate=msg(kNowStatus,11,31,10,3);receive(peerA,duplicate);check(latest.state==2,"duplicate status rejected");
 auto newest=msg(kNowStatus,11,31,11,3);receive(peerA,newest);poll();check(latest.state==3,"newer terminal status accepted");
 auto reboot=msg(kNowPresence,12);receive(peerA,reboot);check(peerBootNonce==12 && sessionId==0 && !takeInterrupted(),"reboot after completed session not interrupted");
 receive(peerA,a);check(peerBootNonce==12,"immediately retired boot rejected");
 receive(peerA,first);check(peerBootNonce==12 && sessionId==0,"status from retired boot rejected");
 reset();receive(peerA,a);poll();receive(peerA,first);poll();receive(peerA,reboot);check(peerBootNonce==12 && takeInterrupted(),"active session restart interrupts");
 reset();receive(peerA,a);poll();auto wrap0=msg(kNowStatus,11,31,0xfffffffe,2);receive(peerA,wrap0);poll();auto wrap1=msg(kNowStatus,11,31,1,2);receive(peerA,wrap1);check(lastReportSeq==1,"report sequence wraps forward");
 reset();receive(peerA,a);poll();receive(peerA,first);poll();NowMessage out{};advance(4999);snapshot(out);check(out.state==2,"snapshot fresh before timeout");advance(1);snapshot(out);check(out.state==0,"snapshot expires at 5 seconds");
 reset();receive(peerA,a);poll();receive(peerA,first);poll();advance(4900);receive(peerA,a);poll();advance(100);bool stillOnline=snapshot(out);check(stillOnline && out.state==0,"presence keeps link online without refreshing stale status");
 reset();receive(peerA,a);poll();receive(peerA,first);poll();auto bootB=msg(kNowPresence,12);auto bootC=msg(kNowPresence,13);receive(peerA,bootB);receive(peerA,bootC);receive(peerA,a);check(peerBootNonce==13,"old boot rejected after two restarts");
 reset();receive(peerA,a);poll();advance(14999);check(!rediscoverOfflineIdle(),"online peer remains pinned before offline threshold");advance(1);check(rediscoverOfflineIdle(),"explicit rediscovery releases offline idle peer");receive(peerB,b);poll();check(pinned && std::memcmp(peerMac,peerB,6)==0 && peerBootNonce==22,"new peer discovered with fresh boot context");
 receive(peerA,a);check(std::memcmp(peerMac,peerB,6)==0,"former peer cannot replace newly pinned peer");
 reset();receive(peerA,a);poll();receive(peerA,first);poll();advance(16000);check(!rediscoverOfflineIdle() && sessionId==31,"offline active session cannot switch peer");
 reset();receive(peerA,a);poll();start();advance(16000);check(!rediscoverOfflineIdle(),"unacknowledged START cannot switch peer");
 reset();receive(peerA,a);poll();auto activePresence=msg(kNowPresence,11,0,0,2);receive(peerA,activePresence);poll();advance(16000);check(!rediscoverOfflineIdle(),"active presence without session cannot switch peer");
 reset();receive(peerA,a);poll();receive(peerA,newest);poll();advance(16000);check(rediscoverOfflineIdle(),"offline terminal session can rediscover");
 reset();check(!simulationAllowed(false,false,false),"simulation blocked before peer discovery");receive(peerA,a);poll();check(simulationAllowed(false,false,false),"simulation allowed when peer online and idle");
 check(!simulationAllowed(true,false,false) && !simulationAllowed(false,true,false) && !simulationAllowed(false,false,true),"simulation blocked during test or uncertain STOP");
 start();check(!simulationAllowed(false,false,false),"simulation blocked while START awaiting status");
 stopStartRetries();check(!simulationAllowed(false,false,false),"simulation blocked when START outcome unknown");
 reset();receive(peerA,a);poll();receive(peerA,first);poll();check(!simulationAllowed(false,false,false),"simulation blocked for physical active session before UI refresh");
 receive(peerA,newest);poll();check(simulationAllowed(false,false,false),"simulation allowed for confirmed terminal session");
 reset();auto livePresence=msg(kNowPresence,11,0,0,2);receive(peerA,livePresence);poll();check(!simulationAllowed(false,false,false),"simulation blocked by active presence before session status");
 reset();receive(peerA,a);poll();advance(5000);check(!simulationAllowed(false,false,false),"simulation blocked when peer is offline");
 reset();receive(peerA,a);receive(peerB,b);poll();start();poll();
 bool onlyPeerA=true,sawStart=false;for(size_t i=0;i<fakeNowTx.size();++i){NowMessage m{};if(fakeNowTx[i].size()==sizeof(m)){std::memcpy(&m,fakeNowTx[i].data(),sizeof(m));if(m.type==kNowStart){sawStart=true;if(std::memcmp(fakeNowTargets[i].data(),peerA,6))onlyPeerA=false;}}}
 check(sawStart && onlyPeerA,"START unicast only to selected peer with two CH1 present");
 reset();start();poll();bool noStart=true;for(const auto& tx:fakeNowTx){NowMessage m{};if(tx.size()==sizeof(m)){std::memcpy(&m,tx.data(),sizeof(m));if(m.type==kNowStart)noStart=false;}}
 check(noStart && awaitStatus,"START waits without a pinned peer");receive(peerA,a);poll();bool startedAfterDiscovery=false;for(size_t i=0;i<fakeNowTx.size();++i){NowMessage m{};if(fakeNowTx[i].size()==sizeof(m)){std::memcpy(&m,fakeNowTx[i].data(),sizeof(m));if(m.type==kNowStart && !std::memcmp(fakeNowTargets[i].data(),peerA,6))startedAfterDiscovery=true;}}
 check(startedAfterDiscovery,"START resumes unicast when selected peer is discovered");
 reset();receive(peerA,a);poll();advance(5000);start();poll();bool absentNoStart=true;for(const auto& tx:fakeNowTx){NowMessage m{};if(tx.size()==sizeof(m)){std::memcpy(&m,tx.data(),sizeof(m));if(m.type==kNowStart)absentNoStart=false;}}
 check(absentNoStart,"START waits for stale pinned peer to reconnect");receive(peerA,a);poll();bool startedOnReconnect=false;for(size_t i=0;i<fakeNowTx.size();++i){NowMessage m{};if(fakeNowTx[i].size()==sizeof(m)){std::memcpy(&m,fakeNowTx[i].data(),sizeof(m));if(m.type==kNowStart && !std::memcmp(fakeNowTargets[i].data(),peerA,6))startedOnReconnect=true;}}
 check(startedOnReconnect,"START resumes to pinned peer on reconnect");
 for (bool realtime : {false,true}) {
  reset();receive(peerA,a);poll();check(start(realtime),"start accepted");const uint32_t sid=sessionId;poll();
  const uint8_t startType=realtime?kNowStartRealtime:kNowStart;
  size_t starts=0;for(const auto& tx:fakeNowTx) { NowMessage m{};if(tx.size()==sizeof(m)){std::memcpy(&m,tx.data(),sizeof(m));if(m.type==startType && m.session==sid) ++starts;} }
  check(starts==1,realtime?"realtime START transmitted":"PDR START transmitted");
  stopStartRetries();check(!awaitStatus && sessionId==sid && pinned && std::memcmp(peerMac,peerA,6)==0,"stopping START retries keeps session and peer");
  size_t before=fakeNowTx.size();advance(2500);advance(2500);
  bool retry=false;for(size_t i=before;i<fakeNowTx.size();++i){NowMessage m{};if(fakeNowTx[i].size()==sizeof(m)){std::memcpy(&m,fakeNowTx[i].data(),sizeof(m));if(m.type==kNowStart || m.type==kNowStartRealtime)retry=true;}}
  check(!retry,"no START retries after stop request");
  check(stop(),"STOP can still be sent");NowMessage sent{};std::memcpy(&sent,fakeNowTx.back().data(),sizeof(sent));
  check(sent.type==kNowStop && sent.session==sid && std::memcmp(fakeNowTargets.back().data(),peerA,6)==0,"STOP uses original session and peer");
 }
 std::printf("%d failure(s)\n",failures);return failures?1:0;
}
