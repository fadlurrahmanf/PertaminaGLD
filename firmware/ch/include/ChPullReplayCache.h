#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace pgl { namespace ch {

// Retain immutable wire responses briefly so a lost radio frame can be sent
// again without pretending that previously transmitted sensor data is unsent.
template <size_t FrameCapacity, size_t EntryCount>
class ChPullReplayCache {
public:
    bool remember(uint16_t origin, uint16_t requestId, uint8_t sequence, uint32_t now,
                  const uint8_t* frame, size_t size) {
        if (frame == nullptr || size == 0 || size > FrameCapacity) return false;
        Entry& entry = entries_[next_];
        entry.used = true;
        entry.origin = origin;
        entry.requestId = requestId;
        entry.sequence = sequence;
        entry.storedAt = now;
        entry.size = size;
        std::memcpy(entry.frame, frame, size);
        next_ = (next_ + 1) % EntryCount;
        return true;
    }

    const uint8_t* find(uint16_t origin, uint16_t requestId, uint8_t sequence, uint32_t now,
                        uint32_t ttlMs, size_t& size) const {
        size = 0;
        for (size_t i = 0; i < EntryCount; ++i) {
            const Entry& entry = entries_[i];
            if (entry.used && entry.origin == origin && entry.requestId == requestId && entry.sequence == sequence &&
                static_cast<uint32_t>(now - entry.storedAt) <= ttlMs) {
                size = entry.size;
                return entry.frame;
            }
        }
        return nullptr;
    }

private:
    static_assert(EntryCount > 0, "replay cache needs at least one entry");
    struct Entry {
        bool used{};
        uint16_t origin{};
        uint16_t requestId{};
        uint8_t sequence{};
        uint32_t storedAt{};
        size_t size{};
        uint8_t frame[FrameCapacity]{};
    };
    Entry entries_[EntryCount]{};
    size_t next_{};
};

}}  // namespace pgl::ch
