#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include "../../CH/include/LoRaTesterWire.h"

// Bench-only unencrypted ESP-NOW; session and source filter accidental crosstalk.
namespace monitorlink {
using loratester::NowMessage;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static NowMessage latest{};
static bool pending = false, pendingStatus = false, pinned = false, ready = false, awaitStatus = false, idlePresence = false, interrupted = false;
static volatile uint32_t txCallbacks = 0, txDelivered = 0;
static volatile uint32_t rxRaw = 0, rxBadLength = 0, rxBadFormat = 0, rxBadBoot = 0, rxBadSource = 0, rxOldStatus = 0, rxAccepted = 0;
static int lastSendResult = -999;
static uint8_t peerMac[6] = {};
static uint32_t sessionId = 0, lastRx = 0, lastStatusRx = 0, lastTx = 0, lastDiscover = 0, startedAt = 0;
static uint32_t ignoredSession = 0;
static uint32_t lastReportSeq = 0;
static bool hasReportSeq = false;
static bool realtimeStart = false;
static uint32_t peerBootNonce = 0, retiredBootNonces[8] = {};
static uint8_t retiredBootIndex = 0;
static bool bootKnown = false;
static uint8_t lastPresenceState = 255;
static const uint8_t broadcast[6] = {255,255,255,255,255,255};
static void onSend(const uint8_t*, esp_now_send_status_t result) {
  ++txCallbacks; if (result == ESP_NOW_SEND_SUCCESS) ++txDelivered;
}
static void onReceive(const uint8_t *mac, const uint8_t *data, int len) {
  ++rxRaw;
  if (len != sizeof(NowMessage)) { ++rxBadLength; return; }
  NowMessage msg; memcpy(&msg, data, sizeof(msg));
  bool realtime = msg.phase == 5;
  if (msg.magic != loratester::kNowMagic || msg.version != loratester::kNowVersion || (realtime ? (msg.expected != 0 || msg.received > 1) : (msg.expected != 100 || msg.received > msg.expected)) || msg.state > 7) { ++rxBadFormat; return; }
  portENTER_CRITICAL(&mux);
  bool presence = msg.type == loratester::kNowPresence && msg.session == 0;
  bool samePeer = pinned && memcmp(peerMac, mac, 6) == 0;
  if (presence && (!pinned || samePeer)) {
    if (!msg.bootNonce) { ++rxBadBoot; portEXIT_CRITICAL(&mux); return; }
    for (uint32_t oldNonce : retiredBootNonces) if (oldNonce && oldNonce == msg.bootNonce) { ++rxBadBoot; portEXIT_CRITICAL(&mux); return; }
    if (bootKnown && msg.bootNonce != peerBootNonce) {
      bool hadSession = awaitStatus || (sessionId != 0 && latest.state != 3 && latest.state != 4 && latest.state != 5 && latest.state != 7);
      retiredBootNonces[retiredBootIndex] = peerBootNonce; retiredBootIndex=(retiredBootIndex+1)%8; sessionId=0; ignoredSession=0; hasReportSeq=false; awaitStatus=false;
      memset(&latest,0,sizeof(latest)); if (hadSession) interrupted=true;
    }
    peerBootNonce=msg.bootNonce; bootKnown=true;
  }
  if (msg.type == loratester::kNowStatus && (!bootKnown || msg.bootNonce != peerBootNonce)) { ++rxBadBoot; portEXIT_CRITICAL(&mux); return; }
  bool resume = msg.type == loratester::kNowStatus && !sessionId && msg.session && msg.session != ignoredSession && samePeer;
  if (resume) { sessionId = msg.session; hasReportSeq = false; }
  bool status = samePeer && msg.type == loratester::kNowStatus && sessionId && msg.session == sessionId;
  if (status && hasReportSeq && static_cast<int32_t>(msg.reportSeq - lastReportSeq) <= 0) { ++rxOldStatus; portEXIT_CRITICAL(&mux); return; }
  if (status) { lastReportSeq = msg.reportSeq; hasReportSeq = true; }
  if (!presence && !status) { ++rxBadSource; portEXIT_CRITICAL(&mux); return; }
  if (!pinned) { memcpy(peerMac, mac, 6); pinned = true; }
  if (memcmp(peerMac, mac, 6) == 0) { ++rxAccepted; if(presence) { idlePresence = msg.state == 0; lastPresenceState=msg.state; } if(status) { latest = msg; awaitStatus=false; pendingStatus=true; idlePresence=false; } pending = true; } else { ++rxBadSource; }
  portEXIT_CRITICAL(&mux);
}
static bool begin() {
  WiFi.mode(WIFI_STA); WiFi.disconnect();
  if (esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE) != ESP_OK || esp_now_init() != ESP_OK) return false;
  esp_now_register_recv_cb(onReceive);
  esp_now_register_send_cb(onSend);
  esp_now_peer_info_t p{}; memcpy(p.peer_addr,broadcast,6); p.channel=1; p.encrypt=false;
  ready = esp_now_add_peer(&p) == ESP_OK;
  return ready;
}
static bool start(bool realtime = false) {
  if (!ready) return false;
  portENTER_CRITICAL(&mux);
  do { sessionId = esp_random(); } while (!sessionId);
  awaitStatus=true; realtimeStart=realtime; ignoredSession=0; hasReportSeq=false; memset(&latest,0,sizeof(latest));
  portEXIT_CRITICAL(&mux);
  startedAt=millis(); lastTx=0; lastStatusRx=0;
  return true;
}
static bool stop() {
  uint8_t target[6]; uint32_t sid;
  portENTER_CRITICAL(&mux); bool valid=pinned; memcpy(target,peerMac,6); sid=sessionId; portEXIT_CRITICAL(&mux);
  if (!valid || !sid || !ready) return false;
  if (!esp_now_is_peer_exist(target)) {
    esp_now_peer_info_t p{}; memcpy(p.peer_addr,target,6); p.channel=1; p.encrypt=false;
    if (esp_now_add_peer(&p) != ESP_OK) return false;
  }
  NowMessage msg{}; msg.magic=loratester::kNowMagic; msg.version=loratester::kNowVersion; msg.type=loratester::kNowStop; msg.session=sid;
  return esp_now_send(target,reinterpret_cast<const uint8_t*>(&msg),sizeof(msg)) == ESP_OK;
}
static void cancelPending() {
  portENTER_CRITICAL(&mux); sessionId=0; awaitStatus=false; hasReportSeq=false; portEXIT_CRITICAL(&mux);
}
// Do not replace a physical session with simulated data, even before its
// first STATUS has reached the UI. Terminal sessions are safe to leave.
static bool simulationAllowed(bool running, bool stopPending, bool stopUnconfirmed) {
  portENTER_CRITICAL(&mux);
  const bool terminal = latest.state==3 || latest.state==4 || latest.state==5 || latest.state==7;
  const bool presenceSafe = lastPresenceState==0 || lastPresenceState==3 || lastPresenceState==4 || lastPresenceState==5 || lastPresenceState==7;
  const bool peerOnline = pinned && lastRx && millis()-lastRx < 5000;
  const bool safe = !running && !stopPending && !stopUnconfirmed && !awaitStatus && peerOnline && presenceSafe && (!sessionId || terminal);
  portEXIT_CRITICAL(&mux);
  return safe;
}
static void stopStartRetries() {
  portENTER_CRITICAL(&mux); awaitStatus=false; portEXIT_CRITICAL(&mux);
}
// User re-enters a test mode: release only an offline peer last seen idle or
// terminal. Never switch an active or unacknowledged session automatically.
static bool rediscoverOfflineIdle() {
  uint8_t oldPeer[6]; bool released=false;
  portENTER_CRITICAL(&mux);
  const bool presenceSafe = lastPresenceState==0 || lastPresenceState==3 || lastPresenceState==4 || lastPresenceState==5 || lastPresenceState==7;
  const bool sessionSafe = !sessionId || latest.state==3 || latest.state==4 || latest.state==5 || latest.state==7;
  if (pinned && lastRx && millis()-lastRx>=15000 && !pending && !pendingStatus && !awaitStatus && presenceSafe && sessionSafe) {
    memcpy(oldPeer,peerMac,6); pinned=false; sessionId=0; ignoredSession=0;
    hasReportSeq=false; lastReportSeq=0; bootKnown=false; peerBootNonce=0;
    memset(retiredBootNonces,0,sizeof(retiredBootNonces)); retiredBootIndex=0;
    memset(peerMac,0,sizeof(peerMac)); memset(&latest,0,sizeof(latest));
    idlePresence=false; lastPresenceState=255; lastStatusRx=lastRx=0; released=true;
  }
  portEXIT_CRITICAL(&mux);
  if (released && esp_now_is_peer_exist(oldPeer)) esp_now_del_peer(oldPeer);
  return released;
}
static void forgetSession() {
  portENTER_CRITICAL(&mux);
  ignoredSession=sessionId; sessionId=0; awaitStatus=false; hasReportSeq=false; memset(&latest,0,sizeof(latest));
  portEXIT_CRITICAL(&mux);
  lastStatusRx=0;
}
static bool takeInterrupted() {
  portENTER_CRITICAL(&mux); bool value=interrupted; interrupted=false; portEXIT_CRITICAL(&mux); return value;
}
static void poll() {
  if (!ready) return;
  bool waiting;
  portENTER_CRITICAL(&mux); waiting=awaitStatus; if(pending){lastRx=millis();pending=false;} if(pendingStatus){lastStatusRx=millis();pendingStatus=false;} portEXIT_CRITICAL(&mux);
  portENTER_CRITICAL(&mux);
  if (sessionId && !awaitStatus && idlePresence && lastStatusRx && millis()-lastStatusRx >= 5000) {
    sessionId=0; hasReportSeq=false; memset(&latest,0,sizeof(latest)); interrupted=true; idlePresence=false;
  }
  if (awaitStatus && startedAt && millis()-startedAt >= 60000) { sessionId=0; awaitStatus=false; interrupted=true; }
  portEXIT_CRITICAL(&mux);
  if (!lastDiscover || millis()-lastDiscover >= 2000) {
    NowMessage msg{}; msg.magic=loratester::kNowMagic; msg.version=loratester::kNowVersion; msg.type=loratester::kNowDiscover;
    esp_now_send(broadcast,reinterpret_cast<const uint8_t*>(&msg),sizeof(msg)); lastDiscover=millis();
  }
  if (waiting && sessionId && millis()-startedAt < 60000 && (!lastTx || millis()-lastTx >= 2000)) {
    uint8_t target[6]; bool peerOnline;
    portENTER_CRITICAL(&mux);
    peerOnline = pinned && lastRx && millis()-lastRx < 5000;
    memcpy(target,peerMac,sizeof(target));
    portEXIT_CRITICAL(&mux);
    if (peerOnline) {
      if (!esp_now_is_peer_exist(target)) {
        esp_now_peer_info_t p{}; memcpy(p.peer_addr,target,6); p.channel=1; p.encrypt=false;
        lastSendResult=esp_now_add_peer(&p);
      } else lastSendResult=ESP_OK;
      if (lastSendResult==ESP_OK) {
        NowMessage msg{}; msg.magic=loratester::kNowMagic; msg.version=loratester::kNowVersion; msg.type=realtimeStart ? loratester::kNowStartRealtime : loratester::kNowStart; msg.session=sessionId;
        lastSendResult=esp_now_send(target,reinterpret_cast<const uint8_t*>(&msg),sizeof(msg));
      }
      lastTx=millis();
    }
  }
}
static bool snapshot(NowMessage &out) {
  bool ok; portENTER_CRITICAL(&mux); ok=pinned; out=latest; portEXIT_CRITICAL(&mux);
  if (!lastStatusRx || millis()-lastStatusRx >= 5000) memset(&out,0,sizeof(out));
  return ok && lastRx && millis()-lastRx < 5000;
}
}
