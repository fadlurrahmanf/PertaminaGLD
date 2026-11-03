#pragma once

#if defined(PGL_GLD_DATASET_WORKFLOW) && PGL_GLD_DATASET_WORKFLOW
#include <cstddef>
#include <cstdint>
#include "GldDatasetWorkflowWifi.h"

namespace pgl::gld::datasetworkflowwifi {

constexpr size_t REPLAY_CAPACITY = 640;
constexpr uint32_t REPLAY_RETENTION_MS = 300000;
constexpr uint32_t REPLAY_WINDOW = 8;

struct RetainedSample {
    Sample sample{};
    uint32_t sequence = 0;
    uint32_t overruns = 0;
};
static_assert(sizeof(RetainedSample) <= 96, "Workflow retained frame exceeds approved RAM budget");

static_assert(sizeof(RetainedSample) * REPLAY_CAPACITY <= 61440, "Workflow ring exceeds 60 KiB");

// A single session's contiguous, unacknowledged prefix. All calls are protected
// by the owner's mutex. Socket sends never mutate this buffer.
class ReplayBuffer {
public:
    void clear() { head_ = count_ = 0; next_ = acknowledged_ = 0; }
    size_t size() const { return count_; }
    bool full() const { return count_ == REPLAY_CAPACITY; }
    uint32_t nextSequence() const { return next_; }
    uint32_t acknowledgedNext() const { return acknowledged_; }
    uint32_t oldestSequence() const { return count_ ? records_[head_].sequence : next_; }

    bool append(const Sample& sample, uint32_t overruns) {
        if (full() || next_ == UINT32_MAX) return false;
        RetainedSample& target = records_[(head_ + count_) % REPLAY_CAPACITY];
        target.sample = sample;
        target.sequence = next_++;
        target.overruns = overruns;
        ++count_;
        return true;
    }

    const RetainedSample* find(uint32_t sequence) const {
        if (sequence < acknowledged_ || sequence >= next_) return nullptr;
        const size_t delta = sequence - acknowledged_;
        return delta < count_ ? &records_[(head_ + delta) % REPLAY_CAPACITY] : nullptr;
    }

    bool prefixAvailable(uint32_t next) const {
        return next >= acknowledged_ && next <= next_ && next - acknowledged_ <= count_;
    }

    bool acknowledgePrefix(uint32_t next) {
        if (!prefixAvailable(next)) return false;
        const size_t released = next - acknowledged_;
        head_ = (head_ + released) % REPLAY_CAPACITY;
        count_ -= released;
        acknowledged_ = next;
        return true;
    }

private:
    RetainedSample records_[REPLAY_CAPACITY]{};
    size_t head_ = 0;
    size_t count_ = 0;
    uint32_t next_ = 0;
    uint32_t acknowledged_ = 0;
};

// Starts at observed loss or the first pending durable ACK. Progress, rather
// than a successful TCP write or duplicate ACK, is required to move the bound.
class AckProgressClock {
public:
    void arm(uint32_t now) { if (!armed_) { since_ = now; armed_ = true; } }
    void progress(uint32_t now, bool pending) { since_ = now; armed_ = pending; }
    bool expired(uint32_t now) const {
        return armed_ && static_cast<uint32_t>(now - since_) >= REPLAY_RETENTION_MS;
    }
    uint32_t elapsed(uint32_t now) const { return armed_ ? now - since_ : 0; }
    void clear() { armed_ = false; since_ = 0; }
private:
    uint32_t since_ = 0;
    bool armed_ = false;
};
}  // namespace pgl::gld::datasetworkflowwifi
#endif
