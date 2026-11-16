#include <cstdio>
#include <cstring>
#include <vector>
#include <cstdint>
#include "../src/tester_monitor.h"
#include "../src/UiTiming.h"
#include "../src/SampleEvents.h"
#include "../src/BatteryText.h"
#include "../src/DebouncedButton.h"
#include "../src/SampleAge.h"
#include "../src/DirtyFrame.h"
#include "../src/FrameStats.h"
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
 statusReceivedAt=0;hasStatusReceipt=false;
 healthCh1=HealthCache{};healthCh2Relay=HealthCache{};healthCh2Direct=HealthCache{};ch2Pinned=false;ch2BootNonce=0;lastCh2ReportSeq=0;hasCh2ReportSeq=false;retiredCh2BootIndex=0;std::memset(retiredCh2BootNonces,0,sizeof(retiredCh2BootNonces));std::memset(ch2Mac,0,sizeof(ch2Mac));
}
static NowMessage msg(uint8_t type, uint32_t boot, uint32_t session=0, uint32_t seq=0, uint8_t state=0) {
 NowMessage m{};m.magic=kNowMagic;m.version=kNowVersion;m.expected=100;m.type=type;m.bootNonce=boot;m.session=session;m.reportSeq=seq;m.state=state;m.ch1Health=unknownHealth();m.ch2Health=unknownHealth();return m;
}
static void receive(const uint8_t* mac,const NowMessage& m) { onReceive(mac,reinterpret_cast<const uint8_t*>(&m),sizeof(m)); }
static void advance(uint32_t ms) { fakeMillis+=ms; poll(); }
int main() {
 std::vector<uint8_t> previous(dirtyframe::kWidth*dirtyframe::kHeight,0), current=previous;
 auto plan=dirtyframe::compare(current.data(),previous.data(),false,false);check(plan.tiles==225,"invalid frame forces full repaint");
 plan=dirtyframe::compare(current.data(),previous.data(),true,false);check(plan.tiles==0,"identical sprite sends no pixels");
 current[17*240+33]=1;plan=dirtyframe::compare(current.data(),previous.data(),true,false);check(plan.tiles==1 && plan.rows[1]==(1U<<2),"one changed pixel marks exact tile");
 current=previous;current[239*240+239]=1;plan=dirtyframe::compare(current.data(),previous.data(),true,false);check(plan.tiles==1 && plan.rows[14]==(1U<<14),"bottom right pixel stays within last tile");
 current=previous;plan=dirtyframe::compare(current.data(),previous.data(),true,true);check(plan.tiles==5 && plan.rows[12]==0x3e0,"direct hold overlay forces repaint of its tiles");
 current=previous;uint32_t randomPixel=1234567;for(int i=0;i<1200;++i){randomPixel=randomPixel*1664525U+1013904223U;current[randomPixel%current.size()]=uint8_t(i%255+1);}
 plan=dirtyframe::compare(current.data(),previous.data(),true,false);auto reconstructed=previous;
 for(int y=0;y<dirtyframe::kRows;++y)for(int x=0;x<dirtyframe::kColumns;++x)if(plan.rows[y]&(1U<<x))for(int line=0;line<dirtyframe::kTile;++line){const size_t offset=(y*dirtyframe::kTile+line)*dirtyframe::kWidth+x*dirtyframe::kTile;std::memcpy(reconstructed.data()+offset,current.data()+offset,dirtyframe::kTile);}
 check(reconstructed==current,"dirty tiles reconstruct deterministic changed full image");
 FrameStats fps;fps.tick(100);fps.loop(1200);fps.frame(3000,2000,256,false);fps.frame(4000,0,0,false);fps.hold(900);fps.tick(1000100);
 check(fps.lastWindowUs==1000000 && fps.lastRenders==2 && fps.lastBlits==1 && fps.lastPixels==256 && fps.lastMaxFrameUs==4000 && fps.lastMaxLoopUs==1200 && fps.lastHoldUpdates==1 && fps.lastMaxHoldUs==900,"FPS counters distinguish renders, blits, hold, and worst times");
 check(sampleage::effective(4000,100,1100,true)==5000 && sampleage::effective(4000,100,1101,true)==5001,"sample age crosses 5 seconds since STATUS receipt");
 check(sampleage::effective(65530,100,110,true)==65534 && sampleage::effective(1,100,0xfffffff0U,true)==65534,"known sample age saturates without sentinel collision");
 check(sampleage::effective(sampleage::kUnknown,100,110,true)==sampleage::kUnknown && sampleage::effective(100,0,50,false)==sampleage::kUnknown,"unknown sample or absent STATUS remains unknown");
 check(sampleage::effective(10,0xfffffff0U,0x10U,true)==42,"sample age survives millis wrap");
 using ButtonEvent=DebouncedButton::Event;
 DebouncedButton shortPress;shortPress.update(true,100);shortPress.update(true,130);shortPress.update(false,899);check(shortPress.update(false,900)==ButtonEvent::None && shortPress.update(false,929)==ButtonEvent::Short,"release before 800 ms remains short during release debounce");
 DebouncedButton boundary;boundary.update(true,100);boundary.update(true,130);boundary.update(false,900);check(boundary.update(false,930)==ButtonEvent::Long && boundary.update(false,1000)==ButtonEvent::None,"release at threshold becomes one long after debounce");
 DebouncedButton after;after.update(true,100);after.update(true,130);after.update(false,901);check(after.update(false,931)==ButtonEvent::Long,"release after threshold becomes long even if hold tick was missed");
 DebouncedButton held;held.update(true,100);held.update(true,130);check(held.update(true,900)==ButtonEvent::Long && held.update(true,930)==ButtonEvent::None,"held long fires exactly once");held.update(false,1000);check(held.update(false,1030)==ButtonEvent::None,"release after fired long does not repeat");
 DebouncedButton bounce;bounce.update(true,100);bounce.update(false,110);bounce.update(true,115);bounce.update(true,145);bounce.update(false,914);check(bounce.update(false,944)==ButtonEvent::Short,"press bounce resets debounced press edge");
 auto battery=formatBattery(true,3999,50);check(!std::strcmp(battery.voltage,"4.00V") && !std::strcmp(battery.percent,"50%"),"battery shows rounded voltage and percentage");
 battery=formatBattery(false,3800,50);check(!std::strcmp(battery.voltage,"--") && !std::strcmp(battery.percent,"--"),"unavailable battery shows unknown voltage and percentage");
 battery=formatBattery(true,5001,50);check(!std::strcmp(battery.voltage,"--") && !std::strcmp(battery.percent,"--"),"invalid battery voltage not displayed");
 reset(); fakeRandom=kHealthSession-1; check(start() && sessionId==kHealthSession+1,"test session excludes reserved health session");
 check(uitiming::holdBarPixels(0)==0 && uitiming::holdBarPixels(400)==31 && uitiming::holdBarPixels(799)==61 && uitiming::holdBarPixels(800)==62 && uitiming::holdBarPixels(0xffffffff)==62,"hold bar tracks threshold and saturates safely");
 bool moving=true;
 for(int count=2;count<=100;++count) for(uint32_t step=0;step<static_cast<uint32_t>(count);++step) {
   bool changed=false;int highlighted=0;
   for(int n=0;n<count;++n) { const bool a=uitiming::ringHighlight(count,step,n),b=uitiming::ringHighlight(count,step+1,n);changed|=a!=b;highlighted+=a; }
   if(!changed || highlighted!=(count>3?3:1)) moving=false;
 }
 check(moving && !uitiming::ringHighlight(0,1,0) && uitiming::ringHighlight(1,0,0)==uitiming::ringHighlight(1,1,0),"ring highlight moves every rendered frame when progress has at least two points");
 SampleEvents events;check(events.update(7,0,0,0)==0 && events.update(7,3,0,255)==3 && events.update(7,3,0,255)==0 && events.update(7,3,1,0)==3 && events.update(8,1,1,0)==1,"sample events require new sequence and reset per session, including wrap");
 PdrPacketEvents pdr;check(pdr.update(7,10,5)==3 && pdr.update(0,0,0)==0 && pdr.update(7,10,5)==0,"PDR stale snapshot and unchanged counts do not replay packets");
 check(pdr.update(7,11,5)==1 && pdr.update(7,11,6)==2,"PDR packet arrow follows only the direction whose count increases");
 check(pdr.update(8,1,1)==3 && pdr.update(8,1,1)==0,"PDR new session resets per-direction event counts");
 reset();auto direct=msg(kNowCh2Presence,22);direct.expected=0;direct.received=kCh2NodeId;direct.ch2Health.nodeBootNonce=22;direct.ch2Health.ageSeconds=0;direct.ch2Health.flags=kHealthRadioReady;receive(peerB,direct);poll();auto health=healthSnapshot();check(health.ch2Fresh && !health.ch1Fresh && !pinned,"direct CH2 ready independent of CH1 session binding");
 reset();auto ordered=direct;ordered.reportSeq=100;receive(peerB,ordered);poll();advance(4000);receive(peerB,ordered);poll();advance(26001);check(!healthSnapshot().ch2Fresh,"duplicate direct sequence cannot refresh freshness");
 reset();ordered.reportSeq=0xfffffffe;receive(peerB,ordered);ordered.reportSeq=1;receive(peerB,ordered);check(lastCh2ReportSeq==1,"direct sequence wraps forward");ordered.reportSeq=0xffffffff;receive(peerB,ordered);check(lastCh2ReportSeq==1,"older direct sequence rejected after wrap");
 advance(30001);check(!healthSnapshot().ch2Fresh,"direct CH2 health expires");
 reset();auto badDirect=direct;badDirect.ch2Health.nodeBootNonce=23;receive(peerB,badDirect);check(!healthSnapshot().ch2Fresh,"CH2 direct nonce mismatch rejected");
 reset();badDirect=direct;badDirect.ch2Health.flags=kHealthBatteryValid|kHealthAdcCalibrated;badDirect.ch2Health.batteryPct=50;badDirect.ch2Health.batteryMv=0;receive(peerB,badDirect);check(!ch2Pinned,"zero battery voltage rejected for direct health");
 reset();badDirect.ch2Health.batteryMv=5001;receive(peerB,badDirect);check(!ch2Pinned,"overrange battery voltage rejected for direct health");
 reset();badDirect.ch2Health.flags=0;badDirect.ch2Health.batteryMv=3800;badDirect.ch2Health.batteryPct=50;receive(peerB,badDirect);check(!ch2Pinned,"battery unknown requires sentinel values");
 reset();badDirect=direct;badDirect.ch2Health.ageSeconds=0xffff;receive(peerB,badDirect);check(!ch2Pinned && !healthSnapshot().ch2Fresh,"unknown-age direct cannot pin CH2");
 reset();auto relayPresence=msg(kNowPresence,11);relayPresence.ch1Health.nodeBootNonce=11;relayPresence.ch1Health.ageSeconds=0;relayPresence.ch1Health.flags=kHealthRadioReady;relayPresence.ch2Health.nodeBootNonce=22;relayPresence.ch2Health.ageSeconds=0;relayPresence.ch2Health.flags=kHealthRadioReady;receive(peerA,relayPresence);poll();receive(peerB,direct);poll();health=healthSnapshot();check(health.ch1Fresh && health.ch2Fresh && !health.conflict,"matching direct and relay health coexist");
 auto invalidRelay=relayPresence;invalidRelay.ch2Health.flags=kHealthBatteryValid|kHealthAdcCalibrated;invalidRelay.ch2Health.batteryMv=0;invalidRelay.ch2Health.batteryPct=50;receive(peerA,invalidRelay);poll();check(!healthCh2Relay.seen,"invalid relay battery health is discarded");receive(peerA,relayPresence);poll();
 direct.bootNonce=23;direct.ch2Health.nodeBootNonce=23;receive(peerB,direct);poll();health=healthSnapshot();check(health.conflict && !health.ch2Fresh,"conflicting CH2 identity not merged");direct.bootNonce=22;direct.ch2Health.nodeBootNonce=22;receive(peerB,direct);check(ch2BootNonce==23,"late direct packet from retired CH2 boot rejected");
 reset();receive(peerA,relayPresence);poll();advance(5000);health=healthSnapshot();check(!health.ch1Fresh && !health.ch2Fresh,"offline CH1 cannot refresh relay health");
 reset();receive(peerA,relayPresence);receive(peerB,direct);poll();advance(30001);check(!rediscoverStaleCh2(false,false,false,false),"stale CH2 cannot rebind when CH1 offline and session uncertain");receive(peerA,relayPresence);poll();
 check(!rediscoverStaleCh2(true,false,false,false) && !rediscoverStaleCh2(false,true,false,false) && !rediscoverStaleCh2(false,false,true,false) && !rediscoverStaleCh2(false,false,false,true),"stale CH2 cannot rebind during active pending uncertain or recovery");
 check(rediscoverStaleCh2(false,false,false,false) && !ch2Pinned && pinned && !std::memcmp(peerMac,peerA,6),"explicit stale CH2 rebind preserves CH1 pin");
 const uint8_t peerC[6]={7,7,7,7,7,7};auto replacement=direct;replacement.bootNonce=33;replacement.ch2Health.nodeBootNonce=33;receive(peerC,replacement);poll();health=healthSnapshot();check(ch2Pinned && !std::memcmp(ch2Mac,peerC,6) && health.conflict && !health.ch2Fresh,"replacement CH2 conflicts with old relay instead of merging");
 reset();receive(peerA,relayPresence);receive(peerB,direct);poll();start();advance(30001);receive(peerA,relayPresence);poll();check(!rediscoverStaleCh2(false,false,false,false),"stale CH2 cannot rebind while START awaits status");
 reset(); auto a=msg(kNowPresence,11); receive(peerA,a);poll();check(pinned && peerBootNonce==11,"valid presence pins peer");
 auto b=msg(kNowPresence,22);receive(peerB,b);poll();check(peerBootNonce==11 && std::memcmp(peerMac,peerA,6)==0,"foreign peer cannot replace pin");
 auto bad=msg(kNowPresence,0);receive(peerA,bad);check(peerBootNonce==11,"zero boot nonce rejected");
 auto first=msg(kNowStatus,11,31,10,2);receive(peerA,first);poll();check(sessionId==31 && latest.reportSeq==10 && latest.state==2,"resume accepted from pinned peer");
 uint32_t capturedAt=0;bool captured=false;NowMessage capturedStatus{};snapshot(capturedStatus,&capturedAt,&captured);check(captured && capturedAt==fakeMillis && capturedStatus.session==31,"STATUS receipt time captured with snapshot");
 fakeMillis+=1250;receive(peerA,first); // duplicate: must not change accepted receipt time
 snapshot(capturedStatus,&capturedAt,&captured);check(captured && capturedAt==100,"duplicate STATUS does not refresh receipt timestamp");
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
