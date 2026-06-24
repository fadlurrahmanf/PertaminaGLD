#pragma once

#include <cstddef>
#include <cstdint>

namespace pgl::radio {

enum class RadioStatus : uint8_t {
    Ok = 0,
    NotReady,
    Timeout,
    Busy,
    TxFailed,
    RxFailed,
    BufferTooSmall,
    InvalidInput,
};

struct RadioRxPacket {
    const uint8_t* bytes;
    size_t size;
    int16_t rssiDbm;
    int8_t snrDb;
};

struct RadioTxPacket {
    const uint8_t* bytes;
    size_t size;
};

using RadioSendFn = RadioStatus (*)(const RadioTxPacket& packet, void* context);
using RadioReceiveFn = RadioStatus (*)(RadioRxPacket& packet, uint32_t timeoutMs, void* context);

struct RadioTransport {
    RadioSendFn send;
    RadioReceiveFn receive;
    void* context;
};

inline bool isRadioTransportConfigured(const RadioTransport& transport) {
    return transport.send != nullptr && transport.receive != nullptr;
}

}  // namespace pgl::radio
