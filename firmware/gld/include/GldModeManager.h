#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

#include "ProtocolConstants.h"

namespace pgl::gld {

enum class GldMode : uint8_t {
    INFERENCE = 0,
    DATASET   = 1,
    NULLING   = 2,
};

// readGldMode consumes a one-shot boot intent. Dataset/nulling can be requested
// by SET_MODE, but the stored default is immediately returned to INFERENCE so
// the next normal boot always starts in running mode.
GldMode     readGldMode();
bool        writeGldMode(GldMode mode);
bool        switchGldMode(GldMode mode);   // restart only after the intent is durable
const char* gldModeName(GldMode mode);
GldMode     gldModeFromString(const char* str);  // unknown -> INFERENCE

// Persists whether the last inference cycle latched an alarm. Survives the
// ESP.restart() that a mode switch triggers, so Dataset/Nulling boot can
// refuse to run while a previous alarm condition is still unacknowledged.
bool readGldAlarmLatched();
bool writeGldAlarmLatched(bool active);

// Service hold is toggled by one debounced CFG-button press/release while the
// GLD is on battery power. It is persisted so an ESP reset during firmware
// upload cannot unexpectedly re-enable the power-latch CLR output.
bool readGldServiceHold();
bool writeGldServiceHold(bool active);

constexpr size_t GLD_PENDING_ALARM_FRAME_CAPACITY =
    pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD;

struct GldPendingAlarm {
    // The first three fields retain the legacy semantic-alarm API. A legacy
    // record has frameLen == 0 and can be rebuilt once, then saved as a frozen
    // frame for byte-identical retries across power cycles.
    bool active = false;
    uint8_t gasClass = 0;
    uint8_t confidence = 0;
    uint8_t sequence = 0;
    uint8_t frameLen = 0;
    uint8_t frame[GLD_PENDING_ALARM_FRAME_CAPACITY] = {};
};

// Alarm delivery is retried for a bounded number of attempts per wake. If no
// matching ACK arrives, retain the exact encoded frame in NVS for the following
// wake cycle. Existing three-key records remain readable with frameLen == 0.
GldPendingAlarm readGldPendingAlarm();
bool            writeGldPendingAlarm(const GldPendingAlarm& pending);
bool            gldPendingAlarmHasFrozenFrame(const GldPendingAlarm& pending);

// Reserves an on-air sequence before returning it. Reservations are committed
// ahead in a small block so an unexpected reset skips unused values instead of
// reusing a sequence from the preceding power cycle. The 8-bit on-air value
// still wraps as required by the existing protocol. On failure, sequence is
// left unchanged and must not be transmitted.
bool reserveGldTxSequence(uint8_t& sequence);

}  // namespace pgl::gld
