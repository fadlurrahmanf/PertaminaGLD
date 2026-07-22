#include <cstddef>
#include <cstdint>
#include <cstdio>

#include "AppFrame.h"
#include "ProtocolConstants.h"
#include "ServerNodeCommandRoute.h"

namespace {

int failures = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::printf("FAIL line=%d condition=%s\n", __LINE__, #condition); \
            ++failures;                                                        \
        }                                                                       \
    } while (false)

void testLegacyRoundTripAndEightByteLimit() {
    const uint8_t command[8] = {0x81, 0x02, 0x12, 0x34, 0xAA, 0xBB, 0xCC, 0xDD};
    uint8_t payload[pgl::protocol::MESH_MAX_PAYLOAD]{};
    size_t payloadLen = 0;

    CHECK(pgl::protocol::encodeLegacyServerNodeCommandPayload(
              0xF001, 0x1234, 600, command, sizeof(command),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    CHECK(payloadLen == pgl::protocol::SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE +
                            sizeof(command));

    pgl::protocol::ServerNodeCommandView decoded{};
    CHECK(pgl::protocol::decodeServerNodeCommandPayload(payload, payloadLen, decoded) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    CHECK(!decoded.routed);
    CHECK(decoded.targetNodeId == 0xF001);
    CHECK(decoded.commandId == 0x1234);
    CHECK(decoded.ttlSec == 600);
    CHECK(decoded.commandLen == sizeof(command));

    uint8_t oversized[9]{};
    CHECK(pgl::protocol::encodeLegacyServerNodeCommandPayload(
              0xF001, 1, 600, oversized, sizeof(oversized),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::CommandTooLong);
}

void testTwoHopRouteAndRelayFrame() {
    const uint16_t hops[2] = {0x0064, 0x0065};
    const uint8_t command[8] = {0x81, 0x01, 0x00, 0x07, 1, 2, 3, 4};
    uint8_t payload[pgl::protocol::MESH_MAX_PAYLOAD]{};
    size_t payloadLen = 0;
    CHECK(pgl::protocol::encodeRoutedServerNodeCommandPayloadV1(
              hops, 2, 0xF001, 7, 900, command, sizeof(command),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    CHECK(payload[6] == pgl::protocol::SERVER_NODE_COMMAND_ROUTE_LEGACY_GUARD);
    CHECK(payload[6] > pgl::protocol::NODE_DOWNLINK_COMMAND_MAX_SIZE);

    pgl::protocol::ServerNodeCommandView routed{};
    CHECK(pgl::protocol::decodeServerNodeCommandPayload(payload, payloadLen, routed) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    CHECK(routed.routed);
    CHECK(routed.hopCount == 2);
    CHECK(pgl::protocol::findServerNodeCommandHopIndex(routed, 0x0064) == 0);
    CHECK(pgl::protocol::findServerNodeCommandHopIndex(routed, 0x0065) == 1);
    CHECK(pgl::protocol::serverNodeCommandHopAt(routed, 1) == 0x0065);

    uint8_t gatewayFrame[pgl::protocol::APPFRAME_OVERHEAD +
                         pgl::protocol::MESH_MAX_PAYLOAD]{};
    const auto gatewayEncoded = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_SERVER_NODE_COMMAND, 0x006F, hops[0], 0x42,
        payload, static_cast<uint8_t>(payloadLen), gatewayFrame,
        sizeof(gatewayFrame), pgl::protocol::MESH_MAX_PAYLOAD);
    CHECK(gatewayEncoded.status == pgl::protocol::FrameStatus::Ok);

    pgl::protocol::FrameView atA{};
    CHECK(pgl::protocol::decodeAppFrame(gatewayFrame, gatewayEncoded.size, atA,
                                        pgl::protocol::MESH_MAX_PAYLOAD) ==
          pgl::protocol::FrameStatus::Ok);
    CHECK(atA.dstId == 0x0064);

    uint8_t relayFrame[pgl::protocol::APPFRAME_OVERHEAD +
                       pgl::protocol::MESH_MAX_PAYLOAD]{};
    const auto relayEncoded = pgl::protocol::encodeAppFrame(
        atA.typeFlags, 0x0064, hops[1], atA.seq, atA.payload, atA.payloadLen,
        relayFrame, sizeof(relayFrame), pgl::protocol::MESH_MAX_PAYLOAD);
    CHECK(relayEncoded.status == pgl::protocol::FrameStatus::Ok);

    pgl::protocol::FrameView atB{};
    CHECK(pgl::protocol::decodeAppFrame(relayFrame, relayEncoded.size, atB,
                                        pgl::protocol::MESH_MAX_PAYLOAD) ==
          pgl::protocol::FrameStatus::Ok);
    CHECK(atB.srcId == 0x0064);
    CHECK(atB.dstId == 0x0065);
    CHECK(atB.seq == 0x42);
    pgl::protocol::ServerNodeCommandView atBCommand{};
    CHECK(pgl::protocol::decodeServerNodeCommandPayload(
              atB.payload, atB.payloadLen, atBCommand) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    CHECK(pgl::protocol::findServerNodeCommandHopIndex(atBCommand, 0x0065) == 1);
    CHECK(atBCommand.targetNodeId == 0xF001);
    CHECK(atBCommand.commandLen == 8);
}

void testMalformedAndOversizedRoutesRejected() {
    const uint8_t command[8]{};
    uint8_t payload[pgl::protocol::MESH_MAX_PAYLOAD + 2]{};
    size_t payloadLen = 0;

    const uint16_t duplicateHops[2] = {0x0064, 0x0064};
    CHECK(pgl::protocol::encodeRoutedServerNodeCommandPayloadV1(
              duplicateHops, 2, 0xF001, 1, 600, command, sizeof(command),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::InvalidRoute);

    uint16_t maxHops[29]{};
    for (size_t i = 0; i < 29; ++i) maxHops[i] = static_cast<uint16_t>(0x0100 + i);
    CHECK(pgl::protocol::encodeRoutedServerNodeCommandPayloadV1(
              maxHops, 29, 0xF001, 1, 600, command, sizeof(command),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    CHECK(payloadLen == pgl::protocol::MESH_MAX_PAYLOAD);

    uint16_t tooManyHops[30]{};
    for (size_t i = 0; i < 30; ++i) tooManyHops[i] = static_cast<uint16_t>(0x0200 + i);
    CHECK(pgl::protocol::encodeRoutedServerNodeCommandPayloadV1(
              tooManyHops, 30, 0xF001, 1, 600, command, sizeof(command),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::BufferTooSmall);

    const uint16_t hops[2] = {0x0064, 0x0065};
    CHECK(pgl::protocol::encodeRoutedServerNodeCommandPayloadV1(
              hops, 2, 0xF001, 1, 600, command, sizeof(command),
              payload, sizeof(payload), payloadLen) ==
          pgl::protocol::ServerNodeCommandStatus::Ok);
    payload[1] = 2;
    pgl::protocol::ServerNodeCommandView decoded{};
    CHECK(pgl::protocol::decodeServerNodeCommandPayload(payload, payloadLen, decoded) ==
          pgl::protocol::ServerNodeCommandStatus::UnsupportedVersion);
}

}  // namespace

int main() {
    testLegacyRoundTripAndEightByteLimit();
    testTwoHopRouteAndRelayFrame();
    testMalformedAndOversizedRoutesRejected();
    std::printf("node-command-route tests: %s (%d failure(s))\n",
                failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
