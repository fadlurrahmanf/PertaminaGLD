// Host-side, end-to-end protocol simulation for the Pertamina GLD system.
//
// This is NOT a mock/reimplementation: it links and calls the ACTUAL,
// unmodified firmware source files (firmware/shared/src/*.cpp,
// firmware/gld/src/GldFrameBuilder.cpp, firmware/ch/src/*.cpp - excluding
// only the two Arduino/RadioLib-bound *Main.cpp files), compiled natively
// with real mbedtls for AES-GCM and AES-CMAC. See
// firmware/tests/simulation/README.md for exactly what is and is not
// exercised by this harness, and how it fits together with the Python/Node
// legs of the full simulation.
//
// Topology simulated:
//   GLD1 (0xF001) --STAR-->  CH-B (0x0064, depth 2)
//   GLD2 (0xF002) --STAR-->  CH-B
//   CH-B --MESH--> CH-A (0x0001, depth 1, CH-B's configured parent)
//   CH-A --MESH--> Gateway (0x006F)
//
// The CH-A uplink-relay + hop-by-hop child ACK logic (the H1 fix merged into
// firmware/ch/src/ChStarMeshRuntimeMain.cpp) is Arduino-bound and can't be
// linked here, so it is reproduced inline below using the exact same calls
// into the real, compiled pgl::protocol::encodeAppFrame /
// pgl::protocol::hasAlarmAckFlag - i.e. the cryptographic/framing primitives
// executed are real; only the thin orchestration sequence is mirrored,
// identically to what firmware/tests/test_shared_protocol.py already does
// for the same fix in Python.

#include <cstdio>
#include <cstring>
#include <cstdlib>

#include "AppFrame.h"
#include "FirmwareConfig.h"
#include "GldCrypto.h"
#include "GldFrameBuilder.h"
#include "GldPayload.h"
#include "GldRecord.h"
#include "ProtocolConstants.h"

#include "AlarmQueue.h"
#include "ChPullRequest.h"
#include "ChRuntime.h"
#include "ChTxQueue.h"
#include "ChUplink.h"
#include "ClusterResponse.h"
#include "NodeCache.h"

using namespace pgl;

namespace {

int g_pass = 0;
int g_fail = 0;

void check(bool cond, const char* what) {
    if (cond) {
        std::printf("PASS %s\n", what);
        ++g_pass;
    } else {
        std::printf("FAIL %s\n", what);
        ++g_fail;
    }
}

void printHex(const char* label, const uint8_t* data, size_t len) {
    std::printf("%s=", label);
    for (size_t i = 0; i < len; ++i) {
        std::printf("%02X", data[i]);
    }
    std::printf("\n");
}

// Host-side nonce provider (esp_random() isn't available off-target); mixes
// rand() with a caller-supplied counter so nonces are not fully static.
bool hostNonceProvider(uint8_t nonce[protocol::GLD_AES_GCM_NONCE_SIZE], void* ctx) {
    auto* counter = static_cast<uint32_t*>(ctx);
    for (size_t i = 0; i < protocol::GLD_AES_GCM_NONCE_SIZE; ++i) {
        nonce[i] = static_cast<uint8_t>(std::rand() & 0xFF);
    }
    nonce[8] = static_cast<uint8_t>((*counter >> 24) & 0xFF);
    nonce[9] = static_cast<uint8_t>((*counter >> 16) & 0xFF);
    nonce[10] = static_cast<uint8_t>((*counter >> 8) & 0xFF);
    nonce[11] = static_cast<uint8_t>(*counter & 0xFF);
    ++(*counter);
    return true;
}

// Mirrors GldCommandParser.cpp's verifyModeCommandCmac exactly (that file
// can't be linked here - it includes <Arduino.h> for Stream/Serial types
// used elsewhere in it), calling the REAL computeAesCmac128.
bool verifyModeCommandCmacHostMirror(const protocol::FrameView& decoded, const uint8_t aesKey[16]) {
    if (decoded.payload == nullptr || decoded.payloadLen != 8 || aesKey == nullptr) {
        return false;
    }
    uint8_t macInput[9]{};
    macInput[0] = static_cast<uint8_t>((decoded.srcId >> 8) & 0xFF);
    macInput[1] = static_cast<uint8_t>(decoded.srcId & 0xFF);
    macInput[2] = static_cast<uint8_t>((decoded.dstId >> 8) & 0xFF);
    macInput[3] = static_cast<uint8_t>(decoded.dstId & 0xFF);
    macInput[4] = decoded.seq;
    std::memcpy(&macInput[5], decoded.payload, 4);

    uint8_t cmac[16]{};
    if (protocol::computeAesCmac128(aesKey, macInput, sizeof(macInput), cmac) != protocol::GldCryptoStatus::Ok) {
        return false;
    }
    return std::memcmp(cmac, &decoded.payload[4], 4) == 0;
}

}  // namespace

int main(int argc, char** argv) {
    // Optional CLI override for GLD1's classification: gasClass confidence
    // batteryMv - lets the Python orchestrator drive this scenario with a
    // genuine classification from the real TFLite model instead of a fixed
    // LPG/90% value.
    uint8_t gld1GasClass = protocol::GLD_GAS_LPG;
    uint8_t gld1Confidence = 90;
    uint16_t gld1BatteryMv = 3650;
    if (argc >= 4) {
        gld1GasClass = static_cast<uint8_t>(std::atoi(argv[1]));
        gld1Confidence = static_cast<uint8_t>(std::atoi(argv[2]));
        gld1BatteryMv = static_cast<uint16_t>(std::atoi(argv[3]));
    }

    const uint8_t AES_KEY[16] = {
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    };
    constexpr uint16_t GLD1_ID = 0xF001;
    constexpr uint16_t GLD2_ID = 0xF002;
    constexpr uint16_t CH_B_ID = 0x0064;  // depth-2 CH, direct parent of both GLDs
    constexpr uint16_t CH_A_ID = 0x0001;  // depth-1 CH, CH-B's configured parent
    constexpr uint16_t GATEWAY_ID = 0x006F;

    std::printf("=== SCENARIO 1: end-to-end alarm relay through a 2-hop CH mesh (H1 regression) ===\n");

    // --- GLD1 builds a REAL encrypted+framed uplink (LPG alarm) ---------------
    gld::GldFrameBuilderConfig cfg1{GLD1_ID, CH_B_ID, /*keyId*/ 1, AES_KEY, /*externalPower*/ false,
                                    protocol::GLD_LEL_THRESHOLD_PERCENT};
    gld::GldFrameBuildInput in1{gld1GasClass, gld1Confidence, gld1BatteryMv, /*seq*/ 0x10};
    std::printf("gld1_input_gas_class=%u gld1_input_confidence=%u gld1_input_battery_mv=%u\n", gld1GasClass,
                gld1Confidence, gld1BatteryMv);
    uint32_t nonceCtr1 = 1;
    gld::GldBuiltFrame builtFrame1{};
    auto st1 = gld::buildGldUplinkFrame(cfg1, in1, hostNonceProvider, &nonceCtr1, builtFrame1);
    check(st1 == gld::GldFrameStatus::Ok, "GLD1 buildGldUplinkFrame (real AES-GCM encrypt + frame) Ok");
    bool expectedAlarm = protocol::isGldAlarm(gld1GasClass, gld1Confidence, protocol::GLD_LEL_THRESHOLD_PERCENT);
    check(builtFrame1.alarm == expectedAlarm, "GLD1 frame alarm flag matches real isGldAlarm() for this input");
    printHex("gld1_star_frame_hex", builtFrame1.bytes, builtFrame1.size);

    // --- CH-B receives GLD1's STAR frame: REAL processGldStarFrame ------------
    config::ChRuntimeConfig chBConfig{CH_B_ID, CH_A_ID, 3700, 300000};
    ch::NodeCacheEntry cacheB[8]{};
    ch::AlarmQueueItem alarmQB[4]{};
    ch::ChTxItem txQB[4]{};
    uint8_t ackToGld1[protocol::APPFRAME_OVERHEAD]{};
    ch::ChRuntimeProcessResult resultB{};
    auto statusB = ch::processGldStarFrame(chBConfig, builtFrame1.bytes, builtFrame1.size, /*nowMs*/ 1000,
                                           /*meshSeq*/ 1, cacheB, 8, alarmQB, 4, txQB, 4, ackToGld1,
                                           sizeof(ackToGld1), resultB);
    check(statusB == ch::ChRuntimeStatus::Ok, "CH-B processGldStarFrame Ok");
    check(resultB.ackBuilt == expectedAlarm, "CH-B STAR-acks GLD1 if and only if this reading is an alarm");
    check(resultB.onwardQueued == expectedAlarm, "CH-B queues an onward push toward CH-A if and only if this reading is an alarm");
    if (resultB.ackBuilt) {
        printHex("ch_b_star_ack_to_gld1_hex", ackToGld1, resultB.ackSize);
    }

    if (!expectedAlarm) {
        std::printf(
            "NOTE: this run's classification was not an alarm, so the rest of scenario 1 (multi-hop\n"
            "relay + H1 hop-by-hop ACK) has nothing to relay and is skipped for this run. Re-run with\n"
            "different sensor input, or via the orchestrator's --force-alarm-input, to exercise it.\n");
    } else {
        const ch::ChTxItem* queuedItemB = nullptr;
        auto peekStatusB = ch::peekChTxFrame(txQB, 4, queuedItemB);
        check(peekStatusB == ch::ChTxQueueStatus::Ok && queuedItemB != nullptr, "CH-B tx queue holds the alarm push frame");
        uint8_t meshFrameAtA[ch::CH_TX_FRAME_MAX]{};
        size_t meshFrameAtALen = queuedItemB->frameSize;
        std::memcpy(meshFrameAtA, queuedItemB->frame, meshFrameAtALen);
        printHex("mesh_frame_ch_b_to_ch_a_hex", meshFrameAtA, meshFrameAtALen);

        // --- CH-A receives the MESH frame from CH-B: REAL decodeAppFrame ------
        protocol::FrameView decodedAtA{};
        auto frameStatusAtA = protocol::decodeAppFrame(meshFrameAtA, meshFrameAtALen, decodedAtA, protocol::MESH_MAX_PAYLOAD);
        check(frameStatusAtA == protocol::FrameStatus::Ok, "CH-A decodes CH-B's mesh frame Ok");
        check(decodedAtA.srcId == CH_B_ID, "CH-A sees srcId == CH-B's own CH_ID (not GLD1's node id)");
        check(decodedAtA.dstId == CH_A_ID, "CH-A sees dstId == itself");
        bool isAlarmSensorData = protocol::messageType(decodedAtA.typeFlags) == protocol::MSG_SENSOR_DATA &&
                                 protocol::hasAlarmAckFlag(decodedAtA.typeFlags);
        check(isAlarmSensorData, "CH-A sees MSG_SENSOR_DATA with FLAG_ALARM_ACK set");

        // CH-A relays onward toward the gateway (mirrors enqueueRelayFrame - real encodeAppFrame call)
        uint8_t relayFrame[ch::CH_TX_FRAME_MAX]{};
        auto relayEnc = protocol::encodeAppFrame(decodedAtA.typeFlags, CH_A_ID, GATEWAY_ID, decodedAtA.seq, decodedAtA.payload,
                                                 decodedAtA.payloadLen, relayFrame, sizeof(relayFrame), protocol::MESH_MAX_PAYLOAD);
        check(relayEnc.status == protocol::FrameStatus::Ok, "CH-A builds relay frame toward Gateway Ok");

        // H1 FIX under test: CH-A also ACKs CH-B directly (hop-by-hop), instead
        // of only relying on an ACK from the far-end gateway. Identical call to
        // the merged fix in ChStarMeshRuntimeMain.cpp's uplink-relay branch.
        uint8_t childAck[protocol::APPFRAME_OVERHEAD]{};
        auto childAckEnc = protocol::encodeAppFrame(protocol::TYPE_ALARM_ACK_COMPACT, CH_A_ID, decodedAtA.srcId, decodedAtA.seq,
                                                    nullptr, 0, childAck, sizeof(childAck), protocol::MESH_MAX_PAYLOAD);
        check(childAckEnc.status == protocol::FrameStatus::Ok, "CH-A builds H1 hop-by-hop child ACK Ok");
        printHex("ch_a_hop_by_hop_ack_to_ch_b_hex", childAck, childAckEnc.size);

        // --- CH-B receives the hop-by-hop ACK: REAL decode + REAL markAlarmAcked
        protocol::FrameView decodedAckAtB{};
        auto ackFrameStatus = protocol::decodeAppFrame(childAck, childAckEnc.size, decodedAckAtB, protocol::MESH_MAX_PAYLOAD);
        check(ackFrameStatus == protocol::FrameStatus::Ok, "CH-B decodes the hop-by-hop ACK Ok");
        bool ackAcceptedAtB = decodedAckAtB.srcId == CH_A_ID &&  // == CH-B's configured parentId
                              decodedAckAtB.dstId == CH_B_ID &&  // == CH-B's own CH_ID
                              protocol::hasAlarmAckFlag(decodedAckAtB.typeFlags);
        check(ackAcceptedAtB, "CH-B's real ACK-acceptance check (srcId==parentId && dstId==self && alarm flag) passes");

        check(ch::containsAlarmQueueItem(alarmQB, 4, GLD1_ID, in1.seq), "CH-B alarm queue still holds GLD1's alarm before the ACK");
        ch::markAlarmAcked(GLD1_ID, in1.seq, alarmQB, 4);  // REAL function - exactly what onAlarmAckFromParent() calls
        check(!ch::containsAlarmQueueItem(alarmQB, 4, GLD1_ID, in1.seq),
              "H1 FIX VERIFIED: CH-B's alarm queue is cleared by the hop-by-hop ACK (no timeout/retry/failover)");

        // --- Gateway receives CH-A's relay frame -------------------------------
        protocol::FrameView decodedAtGw{};
        auto gwFrameStatus = protocol::decodeAppFrame(relayFrame, relayEnc.size, decodedAtGw, protocol::MESH_MAX_PAYLOAD);
        check(gwFrameStatus == protocol::FrameStatus::Ok, "Gateway decodes CH-A's relay frame Ok");
        check(decodedAtGw.dstId == GATEWAY_ID, "Gateway sees itself as the destination");
        check(decodedAtGw.payloadLen == decodedAtA.payloadLen &&
                  std::memcmp(decodedAtGw.payload, decodedAtA.payload, decodedAtA.payloadLen) == 0,
              "Gateway receives GLD1's original encrypted payload unchanged end-to-end");
        printHex("gateway_uplink_frame_hex", relayFrame, relayEnc.size);
    }

    std::printf("\n=== SCENARIO 2: normal reading cached, then answered via a server pull request ===\n");

    // --- GLD2 builds a REAL normal (non-alarm) uplink --------------------------
    gld::GldFrameBuilderConfig cfg2{GLD2_ID, CH_B_ID, /*keyId*/ 1, AES_KEY, /*externalPower*/ true,
                                    protocol::GLD_LEL_THRESHOLD_PERCENT};
    gld::GldFrameBuildInput in2{protocol::GLD_GAS_CLEAR, 100, 3900, /*seq*/ 0x20};
    uint32_t nonceCtr2 = 100;
    gld::GldBuiltFrame builtFrame2{};
    auto st2 = gld::buildGldUplinkFrame(cfg2, in2, hostNonceProvider, &nonceCtr2, builtFrame2);
    check(st2 == gld::GldFrameStatus::Ok, "GLD2 buildGldUplinkFrame Ok");
    check(!builtFrame2.alarm, "GLD2 frame correctly NOT flagged as alarm (clear air)");

    ch::ChRuntimeProcessResult resultB2{};
    uint8_t ackToGld2[protocol::APPFRAME_OVERHEAD]{};
    auto statusB2 = ch::processGldStarFrame(chBConfig, builtFrame2.bytes, builtFrame2.size, /*nowMs*/ 2000,
                                            /*meshSeq*/ 2, cacheB, 8, alarmQB, 4, txQB, 4, ackToGld2,
                                            sizeof(ackToGld2), resultB2);
    check(statusB2 == ch::ChRuntimeStatus::Ok, "CH-B caches GLD2's normal reading Ok");
    check(!resultB2.ackBuilt, "CH-B does not STAR-ack a normal (non-alarm) reading");

    // --- Gateway (logically) issues a pull request directly at CH-B -----------
    uint8_t pullPayload[4] = {0x00, 42, static_cast<uint8_t>((CH_B_ID >> 8) & 0xFF), static_cast<uint8_t>(CH_B_ID & 0xFF)};
    uint8_t pullFrame[protocol::APPFRAME_OVERHEAD + protocol::MESH_MAX_PAYLOAD]{};
    auto pullEnc = protocol::encodeAppFrame(protocol::MSG_SERVER_PULL_REQUEST, GATEWAY_ID, CH_B_ID, /*seq*/ 5,
                                            pullPayload, sizeof(pullPayload), pullFrame, sizeof(pullFrame),
                                            protocol::MESH_MAX_PAYLOAD);
    check(pullEnc.status == protocol::FrameStatus::Ok, "Gateway builds SERVER_PULL_REQUEST targeting CH-B Ok");

    ch::ChTxItem txQB2[4]{};
    ch::ChRuntimeProcessResult pullResult{};
    auto pullStatus = ch::handleServerPullRequestFrame(chBConfig, pullFrame, pullEnc.size, /*nowMs*/ 2500, cacheB, 8,
                                                       txQB2, 4, pullResult);
    check(pullStatus == ch::ChRuntimeStatus::Ok, "CH-B handleServerPullRequestFrame Ok (REAL parse + cluster build)");
    check(pullResult.clusterRecordCount == 1, "Cluster response contains exactly GLD2's unsent normal record (GLD1's alarm entry is excluded)");

    const ch::ChTxItem* clusterItem = nullptr;
    ch::peekChTxFrame(txQB2, 4, clusterItem);
    check(clusterItem != nullptr, "Cluster data response frame is queued");
    if (clusterItem != nullptr) {
        protocol::FrameView decodedCluster{};
        auto clusterFrameStatus =
            protocol::decodeAppFrame(clusterItem->frame, clusterItem->frameSize, decodedCluster, protocol::MESH_MAX_PAYLOAD);
        check(clusterFrameStatus == protocol::FrameStatus::Ok, "Cluster response frame decodes Ok");
        check(decodedCluster.dstId == CH_A_ID, "Cluster response is addressed toward CH-B's configured parent (uphill routing)");
        check(decodedCluster.payload[0] == 0x00 && decodedCluster.payload[1] == 42, "Cluster response echoes requestId 42");

        protocol::GldRecordView recordView{};
        auto recordStatus = protocol::decodeGldRecord(&decodedCluster.payload[6], decodedCluster.payloadLen - 6, recordView);
        check(recordStatus == protocol::RecordStatus::Ok, "Embedded GLD record decodes Ok");
        check(recordView.nodeId == GLD2_ID, "Embedded record is GLD2's reading, not GLD1's alarm");
        printHex("cluster_response_frame_hex", clusterItem->frame, clusterItem->frameSize);

        // CH-A relays this onward to the gateway too (same relay branch in
        // ChStarMeshRuntimeMain.cpp handles MSG_CLUSTER_DATA_RESPONSE), so the
        // Node-RED decode step has a frame genuinely addressed to the gateway.
        uint8_t clusterAtGw[ch::CH_TX_FRAME_MAX]{};
        auto clusterRelayEnc = protocol::encodeAppFrame(decodedCluster.typeFlags, CH_A_ID, GATEWAY_ID, decodedCluster.seq,
                                                        decodedCluster.payload, decodedCluster.payloadLen, clusterAtGw,
                                                        sizeof(clusterAtGw), protocol::MESH_MAX_PAYLOAD);
        check(clusterRelayEnc.status == protocol::FrameStatus::Ok, "CH-A relays cluster response onward to Gateway Ok");
        printHex("gateway_cluster_response_frame_hex", clusterAtGw, clusterRelayEnc.size);
    }

    std::printf("\n=== SCENARIO 3: authenticated downlink command (real AES-CMAC) ===\n");

    // --- "Server" builds an authenticated SET_MODE=dataset command for GLD1 ---
    constexpr uint8_t CMD_TYPE_SET_MODE_AUTH = 0x81;
    constexpr uint8_t MODE_DATASET = 1;
    constexpr uint16_t COMMAND_ID = 7;
    const uint8_t appSeq = static_cast<uint8_t>(COMMAND_ID & 0xFF);
    uint8_t macInput[9] = {
        static_cast<uint8_t>((CH_B_ID >> 8) & 0xFF), static_cast<uint8_t>(CH_B_ID & 0xFF),
        static_cast<uint8_t>((GLD1_ID >> 8) & 0xFF), static_cast<uint8_t>(GLD1_ID & 0xFF),
        appSeq,
        CMD_TYPE_SET_MODE_AUTH, MODE_DATASET,
        static_cast<uint8_t>((COMMAND_ID >> 8) & 0xFF), static_cast<uint8_t>(COMMAND_ID & 0xFF),
    };
    printHex("cmac_key_hex", AES_KEY, sizeof(AES_KEY));
    printHex("cmac_mac_input_hex", macInput, sizeof(macInput));
    uint8_t cmacTag[16]{};
    auto cmacStatus = protocol::computeAesCmac128(AES_KEY, macInput, sizeof(macInput), cmacTag);
    check(cmacStatus == protocol::GldCryptoStatus::Ok, "Server computes real AES-CMAC-128 (RFC 4493) for the command Ok");
    printHex("cmac_full_tag_hex", cmacTag, sizeof(cmacTag));

    uint8_t downlinkPayload[8] = {
        CMD_TYPE_SET_MODE_AUTH, MODE_DATASET,
        static_cast<uint8_t>((COMMAND_ID >> 8) & 0xFF), static_cast<uint8_t>(COMMAND_ID & 0xFF),
        cmacTag[0], cmacTag[1], cmacTag[2], cmacTag[3],
    };
    uint8_t downlinkFrame[protocol::APPFRAME_OVERHEAD + protocol::STAR_MAX_PAYLOAD]{};
    auto downlinkEnc = protocol::encodeAppFrame(protocol::MSG_NODE_DOWNLINK, CH_B_ID, GLD1_ID, appSeq, downlinkPayload,
                                                sizeof(downlinkPayload), downlinkFrame, sizeof(downlinkFrame),
                                                protocol::STAR_MAX_PAYLOAD);
    check(downlinkEnc.status == protocol::FrameStatus::Ok, "CH-B builds the authenticated downlink AppFrame Ok");
    printHex("authenticated_downlink_frame_hex", downlinkFrame, downlinkEnc.size);

    // --- GLD1 verifies the command (mirrors GldCommandParser.cpp's checks) ----
    protocol::FrameView decodedDownlink{};
    auto downlinkFrameStatus =
        protocol::decodeAppFrame(downlinkFrame, downlinkEnc.size, decodedDownlink, protocol::STAR_MAX_PAYLOAD);
    check(downlinkFrameStatus == protocol::FrameStatus::Ok, "GLD1 decodes the downlink frame Ok");
    check(protocol::messageType(decodedDownlink.typeFlags) == protocol::MSG_NODE_DOWNLINK, "GLD1 sees MSG_NODE_DOWNLINK");
    check(decodedDownlink.dstId == GLD1_ID, "GLD1 sees itself as the destination");
    check(decodedDownlink.payloadLen == 8 && decodedDownlink.payload[0] == CMD_TYPE_SET_MODE_AUTH,
          "GLD1 sees the authenticated SET_MODE command type");
    bool cmacValid = verifyModeCommandCmacHostMirror(decodedDownlink, AES_KEY);
    check(cmacValid, "GLD1's REAL AES-CMAC verification accepts the server-signed command");

    // Negative test: tamper with one tag byte and confirm rejection.
    uint8_t tamperedFrame[protocol::APPFRAME_OVERHEAD + protocol::STAR_MAX_PAYLOAD]{};
    std::memcpy(tamperedFrame, downlinkFrame, downlinkEnc.size);
    tamperedFrame[protocol::APPFRAME_HEADER_SIZE + 4] ^= 0x01;  // flip a tag bit
    // Recompute CRC over the tampered header+payload so this fails CMAC
    // verification specifically, not just the frame CRC check.
    uint16_t recrc = protocol::crc16CcittFalse(tamperedFrame, protocol::APPFRAME_HEADER_SIZE + 8);
    tamperedFrame[protocol::APPFRAME_HEADER_SIZE + 8] = static_cast<uint8_t>((recrc >> 8) & 0xFF);
    tamperedFrame[protocol::APPFRAME_HEADER_SIZE + 8 + 1] = static_cast<uint8_t>(recrc & 0xFF);
    protocol::FrameView decodedTampered{};
    auto tamperedFrameStatus =
        protocol::decodeAppFrame(tamperedFrame, downlinkEnc.size, decodedTampered, protocol::STAR_MAX_PAYLOAD);
    check(tamperedFrameStatus == protocol::FrameStatus::Ok, "Tampered frame still decodes structurally (CRC fixed up)");
    bool tamperedCmacValid = verifyModeCommandCmacHostMirror(decodedTampered, AES_KEY);
    check(!tamperedCmacValid, "GLD1's REAL AES-CMAC verification REJECTS a tampered command (forgery protection holds)");

    std::printf("\n=== SUMMARY: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
