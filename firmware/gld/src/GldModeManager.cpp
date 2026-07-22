#include "GldModeManager.h"

#include "AppFrame.h"
#include <Arduino.h>
#include <limits>
#include <Preferences.h>

namespace pgl::gld {

namespace {

constexpr const char* NVS_NS = "gld";
constexpr const char* NVS_MODE_KEY = "mode";
constexpr const char* NVS_ALARM_KEY = "alarm";
constexpr const char* NVS_SERVICE_HOLD_KEY = "svc_hold";

// Legacy pending-alarm keys remain read-only migration inputs.
constexpr const char* NVS_PENDING_ALARM_KEY = "pending_alarm";
constexpr const char* NVS_PENDING_GAS_KEY = "pending_gas";
constexpr const char* NVS_PENDING_CONFIDENCE_KEY = "pending_conf";

// Versioned pending records use a two-slot journal. A new record is committed
// to the slot other than the latest valid one, so the previous record survives
// a reset or NVS failure during the update.
constexpr const char* NVS_PENDING_SLOT_A_KEY = "pending_v1_a";
constexpr const char* NVS_PENDING_SLOT_B_KEY = "pending_v1_b";
constexpr uint32_t PENDING_RECORD_MAGIC = 0x50444C47UL;  // "GLDP" little-endian
constexpr uint8_t PENDING_RECORD_VERSION = 1;
constexpr uint8_t PENDING_RECORD_FLAG_ACTIVE = 0x01;

constexpr size_t PENDING_MAGIC_OFFSET = 0;
constexpr size_t PENDING_VERSION_OFFSET = 4;
constexpr size_t PENDING_FLAGS_OFFSET = 5;
constexpr size_t PENDING_GENERATION_OFFSET = 6;
constexpr size_t PENDING_GAS_OFFSET = 10;
constexpr size_t PENDING_CONFIDENCE_OFFSET = 11;
constexpr size_t PENDING_SEQUENCE_OFFSET = 12;
constexpr size_t PENDING_FRAME_LENGTH_OFFSET = 13;
constexpr size_t PENDING_FRAME_OFFSET = 14;
constexpr size_t PENDING_CHECKSUM_OFFSET =
    PENDING_FRAME_OFFSET + GLD_PENDING_ALARM_FRAME_CAPACITY;
constexpr size_t PENDING_RECORD_SIZE = PENDING_CHECKSUM_OFFSET + sizeof(uint32_t);

constexpr const char* NVS_TX_SEQUENCE_HIGH_WATER_KEY = "tx_seq_hi";
constexpr uint64_t TX_SEQUENCE_RESERVATION_SIZE = 16;
// Legacy battery firmware started every boot at sequence zero. Starting a new
// journal at one avoids immediately repeating the common last legacy value.
constexpr uint64_t TX_SEQUENCE_INITIAL_TICKET = 1;

uint64_t txSequenceNext = 0;
uint64_t txSequenceEnd = 0;
bool txSequenceReservationActive = false;

struct StoredPendingAlarm {
    bool valid = false;
    uint32_t generation = 0;
    GldPendingAlarm pending{};
};

bool validMode(GldMode mode) {
    return static_cast<uint8_t>(mode) <= static_cast<uint8_t>(GldMode::NULLING);
}

bool validPendingAlarmSemantics(const GldPendingAlarm& pending) {
    return pending.gasClass != pgl::protocol::GLD_GAS_CLEAR &&
           pending.gasClass <= pgl::protocol::GLD_GAS_ANOMALY &&
           pending.confidence > 0 &&
           pending.confidence <= 100;
}

bool validFrozenFrame(const GldPendingAlarm& pending) {
    if (!pending.active ||
        pending.frameLen < pgl::protocol::APPFRAME_OVERHEAD ||
        pending.frameLen > GLD_PENDING_ALARM_FRAME_CAPACITY) {
        return false;
    }

    pgl::protocol::FrameView decoded{};
    if (pgl::protocol::decodeAppFrame(
            pending.frame, pending.frameLen, decoded,
            static_cast<uint8_t>(pgl::protocol::STAR_MAX_PAYLOAD)) !=
        pgl::protocol::FrameStatus::Ok) {
        return false;
    }

    return decoded.seq == pending.sequence &&
           decoded.srcId != 0 && decoded.dstId != 0 && decoded.srcId != decoded.dstId &&
           (decoded.typeFlags & pgl::protocol::MSG_TYPE_MASK) ==
               pgl::protocol::MSG_SENSOR_DATA &&
           (decoded.typeFlags & pgl::protocol::FLAG_ALARM_ACK) != 0 &&
           decoded.payloadLen != 0;
}

bool validPendingAlarmForWrite(const GldPendingAlarm& pending) {
    if (!pending.active) {
        return true;
    }
    if (!validPendingAlarmSemantics(pending)) {
        return false;
    }
    return pending.frameLen == 0 || validFrozenFrame(pending);
}

bool putUCharChecked(Preferences& prefs, const char* key, uint8_t value) {
    return prefs.putUChar(key, value) == sizeof(value);
}

bool putBoolChecked(Preferences& prefs, const char* key, bool value) {
    return prefs.putBool(key, value) == sizeof(uint8_t);
}

bool removeIfPresent(Preferences& prefs, const char* key) {
    return !prefs.isKey(key) || prefs.remove(key);
}

void writeU32Le(uint8_t* out, uint32_t value) {
    out[0] = static_cast<uint8_t>(value & 0xFFU);
    out[1] = static_cast<uint8_t>((value >> 8U) & 0xFFU);
    out[2] = static_cast<uint8_t>((value >> 16U) & 0xFFU);
    out[3] = static_cast<uint8_t>((value >> 24U) & 0xFFU);
}

uint32_t readU32Le(const uint8_t* in) {
    return static_cast<uint32_t>(in[0]) |
           (static_cast<uint32_t>(in[1]) << 8U) |
           (static_cast<uint32_t>(in[2]) << 16U) |
           (static_cast<uint32_t>(in[3]) << 24U);
}

uint32_t crc32Ieee(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFFUL;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; ++bit) {
            const uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (0xEDB88320UL & mask);
        }
    }
    return ~crc;
}

void encodePendingRecord(
    const GldPendingAlarm& pending,
    uint32_t generation,
    uint8_t (&record)[PENDING_RECORD_SIZE]) {
    memset(record, 0, sizeof(record));
    writeU32Le(&record[PENDING_MAGIC_OFFSET], PENDING_RECORD_MAGIC);
    record[PENDING_VERSION_OFFSET] = PENDING_RECORD_VERSION;
    record[PENDING_FLAGS_OFFSET] = pending.active ? PENDING_RECORD_FLAG_ACTIVE : 0;
    writeU32Le(&record[PENDING_GENERATION_OFFSET], generation);

    if (pending.active) {
        record[PENDING_GAS_OFFSET] = pending.gasClass;
        record[PENDING_CONFIDENCE_OFFSET] = pending.confidence;
        record[PENDING_SEQUENCE_OFFSET] = pending.sequence;
        record[PENDING_FRAME_LENGTH_OFFSET] = pending.frameLen;
        if (pending.frameLen != 0) {
            memcpy(&record[PENDING_FRAME_OFFSET], pending.frame, pending.frameLen);
        }
    }

    const uint32_t checksum = crc32Ieee(record, PENDING_CHECKSUM_OFFSET);
    writeU32Le(&record[PENDING_CHECKSUM_OFFSET], checksum);
}

StoredPendingAlarm readPendingSlot(Preferences& prefs, const char* key) {
    StoredPendingAlarm stored{};
    if (!prefs.isKey(key) || prefs.getType(key) != PT_BLOB ||
        prefs.getBytesLength(key) != PENDING_RECORD_SIZE) {
        return stored;
    }

    uint8_t record[PENDING_RECORD_SIZE] = {};
    if (prefs.getBytes(key, record, sizeof(record)) != sizeof(record) ||
        readU32Le(&record[PENDING_MAGIC_OFFSET]) != PENDING_RECORD_MAGIC ||
        record[PENDING_VERSION_OFFSET] != PENDING_RECORD_VERSION ||
        (record[PENDING_FLAGS_OFFSET] & ~PENDING_RECORD_FLAG_ACTIVE) != 0 ||
        readU32Le(&record[PENDING_CHECKSUM_OFFSET]) !=
            crc32Ieee(record, PENDING_CHECKSUM_OFFSET)) {
        return stored;
    }

    stored.generation = readU32Le(&record[PENDING_GENERATION_OFFSET]);
    stored.pending.active =
        (record[PENDING_FLAGS_OFFSET] & PENDING_RECORD_FLAG_ACTIVE) != 0;
    if (!stored.pending.active) {
        stored.valid = true;
        return stored;
    }

    stored.pending.gasClass = record[PENDING_GAS_OFFSET];
    stored.pending.confidence = record[PENDING_CONFIDENCE_OFFSET];
    stored.pending.sequence = record[PENDING_SEQUENCE_OFFSET];
    stored.pending.frameLen = record[PENDING_FRAME_LENGTH_OFFSET];
    if (stored.pending.frameLen > GLD_PENDING_ALARM_FRAME_CAPACITY) {
        return {};
    }
    if (stored.pending.frameLen != 0) {
        memcpy(
            stored.pending.frame,
            &record[PENDING_FRAME_OFFSET],
            stored.pending.frameLen);
    }
    if (!validPendingAlarmForWrite(stored.pending)) {
        return {};
    }

    stored.valid = true;
    return stored;
}

bool generationIsNewer(uint32_t candidate, uint32_t reference) {
    return candidate != reference &&
           static_cast<uint32_t>(candidate - reference) < 0x80000000UL;
}

const StoredPendingAlarm* newestPendingSlot(
    const StoredPendingAlarm& slotA,
    const StoredPendingAlarm& slotB) {
    if (!slotA.valid) {
        return slotB.valid ? &slotB : nullptr;
    }
    if (!slotB.valid) {
        return &slotA;
    }
    return generationIsNewer(slotB.generation, slotA.generation) ? &slotB : &slotA;
}

GldPendingAlarm readLegacyPendingAlarm(Preferences& prefs) {
    GldPendingAlarm pending{};
    pending.active = prefs.getBool(NVS_PENDING_ALARM_KEY, false);
    if (!pending.active) {
        return pending;
    }

    pending.gasClass = prefs.getUChar(NVS_PENDING_GAS_KEY, 0);
    pending.confidence = prefs.getUChar(NVS_PENDING_CONFIDENCE_KEY, 0);
    return validPendingAlarmSemantics(pending) ? pending : GldPendingAlarm{};
}

}  // namespace

GldMode readGldMode() {
    Preferences prefs;
    if (!prefs.begin(NVS_NS, false)) {
        return GldMode::INFERENCE;
    }

    const uint8_t val = prefs.getUChar(
        NVS_MODE_KEY, static_cast<uint8_t>(GldMode::INFERENCE));
    const GldMode mode = val <= static_cast<uint8_t>(GldMode::NULLING)
        ? static_cast<GldMode>(val)
        : GldMode::INFERENCE;
    bool consumed = true;
    if (mode != GldMode::INFERENCE || val > static_cast<uint8_t>(GldMode::NULLING)) {
        consumed = putUCharChecked(
            prefs, NVS_MODE_KEY, static_cast<uint8_t>(GldMode::INFERENCE));
    }
    prefs.end();

    // Enter a one-shot non-inference mode only after consuming its intent.
    // Otherwise the same request could replay after every reset.
    return consumed ? mode : GldMode::INFERENCE;
}

bool writeGldMode(GldMode mode) {
    if (!validMode(mode)) {
        return false;
    }

    Preferences prefs;
    if (!prefs.begin(NVS_NS, false)) {
        return false;
    }
    const bool stored = putUCharChecked(prefs, NVS_MODE_KEY, static_cast<uint8_t>(mode));
    prefs.end();
    return stored;
}

bool switchGldMode(GldMode mode) {
    if (!writeGldMode(mode)) {
        return false;
    }
    ESP.restart();
    return true;
}

bool readGldAlarmLatched() {
    Preferences prefs;
    if (!prefs.begin(NVS_NS, true)) {
        return false;
    }
    const bool active = prefs.getBool(NVS_ALARM_KEY, false);
    prefs.end();
    return active;
}

bool writeGldAlarmLatched(bool active) {
    Preferences prefs;
    if (!prefs.begin(NVS_NS, false)) {
        return false;
    }
    const bool stored = putBoolChecked(prefs, NVS_ALARM_KEY, active);
    prefs.end();
    return stored;
}

bool readGldServiceHold() {
    Preferences prefs;
    if (!prefs.begin(NVS_NS, true)) {
        return false;
    }
    const bool active = prefs.getBool(NVS_SERVICE_HOLD_KEY, false);
    prefs.end();
    return active;
}

bool writeGldServiceHold(bool active) {
    Preferences prefs;
    if (!prefs.begin(NVS_NS, false)) {
        return false;
    }
    const bool stored = putBoolChecked(prefs, NVS_SERVICE_HOLD_KEY, active);
    prefs.end();
    return stored;
}

GldPendingAlarm readGldPendingAlarm() {
    Preferences prefs;
    if (!prefs.begin(NVS_NS, true)) {
        return {};
    }

    const StoredPendingAlarm slotA = readPendingSlot(prefs, NVS_PENDING_SLOT_A_KEY);
    const StoredPendingAlarm slotB = readPendingSlot(prefs, NVS_PENDING_SLOT_B_KEY);
    const StoredPendingAlarm* newest = newestPendingSlot(slotA, slotB);
    const GldPendingAlarm pending = newest != nullptr
        ? newest->pending
        : readLegacyPendingAlarm(prefs);
    prefs.end();
    return pending;
}

bool writeGldPendingAlarm(const GldPendingAlarm& pending) {
    if (!validPendingAlarmForWrite(pending)) {
        return false;
    }

    Preferences prefs;
    if (!prefs.begin(NVS_NS, false)) {
        return false;
    }

    const StoredPendingAlarm slotA = readPendingSlot(prefs, NVS_PENDING_SLOT_A_KEY);
    const StoredPendingAlarm slotB = readPendingSlot(prefs, NVS_PENDING_SLOT_B_KEY);
    const StoredPendingAlarm* newest = newestPendingSlot(slotA, slotB);

    uint32_t generation = 1;
    const char* targetKey = NVS_PENDING_SLOT_A_KEY;
    if (newest != nullptr) {
        generation = newest->generation + 1U;
        targetKey = newest == &slotA ? NVS_PENDING_SLOT_B_KEY : NVS_PENDING_SLOT_A_KEY;
    }

    uint8_t record[PENDING_RECORD_SIZE] = {};
    encodePendingRecord(pending, generation, record);
    const bool stored = prefs.putBytes(targetKey, record, sizeof(record)) == sizeof(record);
    if (!stored) {
        prefs.end();
        return false;
    }

    // A valid journal record always wins over legacy keys. Cleanup is still
    // checked and reported so callers never mistake a partial migration for a
    // fully successful persistence operation.
    const bool legacyAlarmRemoved = removeIfPresent(prefs, NVS_PENDING_ALARM_KEY);
    const bool legacyGasRemoved = removeIfPresent(prefs, NVS_PENDING_GAS_KEY);
    const bool legacyConfidenceRemoved =
        removeIfPresent(prefs, NVS_PENDING_CONFIDENCE_KEY);
    prefs.end();
    return legacyAlarmRemoved && legacyGasRemoved && legacyConfidenceRemoved;
}

bool gldPendingAlarmHasFrozenFrame(const GldPendingAlarm& pending) {
    return validPendingAlarmSemantics(pending) && validFrozenFrame(pending);
}

bool reserveGldTxSequence(uint8_t& sequence) {
    if (!txSequenceReservationActive || txSequenceNext == txSequenceEnd) {
        Preferences prefs;
        if (!prefs.begin(NVS_NS, false)) {
            return false;
        }

        uint64_t persistedHighWater = TX_SEQUENCE_INITIAL_TICKET;
        const PreferenceType storedType = prefs.getType(NVS_TX_SEQUENCE_HIGH_WATER_KEY);
        if (storedType == PT_U64) {
            persistedHighWater = prefs.getULong64(
                NVS_TX_SEQUENCE_HIGH_WATER_KEY, TX_SEQUENCE_INITIAL_TICKET);
        } else if (storedType != PT_INVALID) {
            prefs.end();
            return false;
        }

        if (persistedHighWater >
            std::numeric_limits<uint64_t>::max() - TX_SEQUENCE_RESERVATION_SIZE) {
            prefs.end();
            return false;
        }

        const uint64_t reservationEnd =
            persistedHighWater + TX_SEQUENCE_RESERVATION_SIZE;
        const bool reserved = prefs.putULong64(
            NVS_TX_SEQUENCE_HIGH_WATER_KEY, reservationEnd) == sizeof(reservationEnd);
        prefs.end();
        if (!reserved) {
            return false;
        }

        txSequenceNext = persistedHighWater;
        txSequenceEnd = reservationEnd;
        txSequenceReservationActive = true;
    }

    sequence = static_cast<uint8_t>(txSequenceNext & 0xFFU);
    ++txSequenceNext;
    return true;
}

const char* gldModeName(GldMode mode) {
    switch (mode) {
        case GldMode::INFERENCE: return "inference";
        case GldMode::DATASET:   return "dataset";
        case GldMode::NULLING:   return "nulling";
        default:                 return "unknown";
    }
}

GldMode gldModeFromString(const char* str) {
    if (str == nullptr) return GldMode::INFERENCE;
    if (strcmp(str, "dataset")   == 0) return GldMode::DATASET;
    if (strcmp(str, "nulling")   == 0) return GldMode::NULLING;
    if (strcmp(str, "running")   == 0) return GldMode::INFERENCE;
    if (strcmp(str, "inference") == 0) return GldMode::INFERENCE;
    return GldMode::INFERENCE;
}

}  // namespace pgl::gld
