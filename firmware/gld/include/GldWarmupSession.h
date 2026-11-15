#pragma once

#include "GldWarmupReadiness.h"

namespace pgl { namespace gld {

// Candidate 24 V startup policy. Runtime integration and physical parameters
// are intentionally separate: no guessed settings are enabled in a product.
class GldWarmupSession {
public:
    enum class State : uint8_t { Inactive, Warming, Priming, Ready };
    explicit GldWarmupSession(const GldWarmupReadiness::Config& config) : gate_(config) {}

    // powerKnownOn must represent the actual enabled sensor-rail contract for
    // the active board, not simply a successful PCF write.
    void updatePower(uint32_t now, bool external24V, bool powerKnownOn) {
        if (!external24V) {
            state_ = State::Inactive;
            railOn_ = false;
            return;
        }
        if (!powerKnownOn) {
            state_ = State::Warming;
            railOn_ = false;
            return;
        }
        if (!railOn_) {
            railOn_ = true;
            startedAt_ = now;
            gate_.reset(now);
            state_ = State::Warming;
        }
    }

    // Returns true exactly once on a warming->priming transition. The caller
    // must then discard its old averaging buffer before collecting new data.
    bool observe(uint32_t now, const float values[8], uint8_t validMask) {
        if (state_ != State::Warming || !railOn_) return false;
        gate_.sample(now, values, validMask);
        if (!gate_.ready(now)) return false;
        state_ = State::Priming;
        return true;
    }

    // A fresh successful inference is required before presenting READY.
    void noteFreshInference(bool valid) {
        if (state_ == State::Priming && valid) state_ = State::Ready;
    }

    bool blocksInference() const { return state_ == State::Warming; }
    State state() const { return state_; }
    bool railOn() const { return railOn_; }
    uint32_t elapsedMs(uint32_t now) const { return railOn_ ? now - startedAt_ : 0; }
    uint8_t stableMask(uint32_t now) const {
        if (!railOn_) return 0;
        // Warmup has completed; the moving-average refill and normal runtime
        // own subsequent validity. Do not age out the completed warmup result.
        if (state_ == State::Priming || state_ == State::Ready) return 0xff;
        return gate_.stableMask(now);
    }
    bool configured() const { return gate_.configValid(); }

private:
    GldWarmupReadiness gate_;
    State state_ = State::Inactive;
    bool railOn_ = false;
    uint32_t startedAt_ = 0;
};

}}  // namespace pgl::gld
