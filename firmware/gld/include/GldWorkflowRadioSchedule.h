#pragma once

#include <cstdint>

namespace pgl { namespace gld {

// Pure coordination policy. This type never touches SPI, the radio, the ADC,
// recording state, NVS, or alarms. The main-loop caller owns every operation.
// Deadlines are unsigned elapsed durations; callers must poll at least once per
// uint32_t clock cycle and supply timeout values shorter than a clock cycle.
class GldWorkflowRadioSchedule {
public:
    enum class State : uint8_t { Idle, Transmitting, StartReceive, Receiving, Fault };
    enum class Action : uint8_t {
        None, AcquireSample, StartTx, FinishTx, StartRx, FinishRx,
        TimeoutTx, TimeoutRx, AbortRadio
    };
    struct Inputs {
        uint32_t nowMs;
        bool sessionActive;
        bool radioEnabled;
        bool radioAvailable;
        bool txDue;
        bool sampleDue;
        bool irqPending;
        // The caller establishes that the preceding SPI transaction is over
        // and the specific radio state allows an ADC transaction.
        bool samplingPermitted;
        // A previously started transaction may finish after normal Pause or
        // Stop; a new TX still requires the separate admission flag.
        bool drainInFlight;
        bool allowNewTx;
    };

    GldWorkflowRadioSchedule(uint32_t txTimeoutMs, uint32_t rxWindowMs)
        : txTimeoutMs_(txTimeoutMs), rxWindowMs_(rxWindowMs) {}

    State state() const { return state_; }
    Action pending() const { return pending_; }

    // SX126x LoRa upper bound in microseconds, conservatively including the
    // larger SF5/6 preamble term, explicit header, CRC, and the LDRO divisor.
    // Uses only the successfully applied radio config and no hardware I/O.
    // The vendor synchronous SX126x transmit timeout is 5 ms + 5 * ToA.
    // A transaction that cannot finish within its existing TX cadence is
    // rejected instead of leaving an unbounded drain or overlapping cycles.
    static bool txTimeoutFromAppliedConfig(uint32_t bwHz, uint8_t sf, uint8_t cr,
                                           uint16_t preamble, uint16_t frameBytes,
                                           uint32_t txPeriodMs, uint32_t rxWindowMs,
                                           uint32_t& timeoutMs) {
        if (bwHz < 7799 || bwHz > 500000 || sf < 5 || sf > 12 || cr < 5 || cr > 8 ||
            preamble < 6 || frameBytes == 0 || frameBytes > 255 || txPeriodMs <= rxWindowMs) return false;
        const uint64_t numerator = (uint64_t(1) << sf) * 1000000ULL;
        const uint64_t symbolUs = (numerator + bwHz - 1u) / bwHz;
        const uint64_t divisor = 4u * (sf - 2u); // <= either vendor divisor
        const uint64_t bitsUpper = uint64_t(frameBytes) * 8u + 44u;
        const uint64_t codedUpper = (bitsUpper + divisor - 1u) / divisor;
        const uint64_t symbolsX4 = 4u * (uint64_t(preamble) + 8u) + 25u +
                                   4u * codedUpper * cr;
        // Bounds below are tiny for the validated SX126x parameter ranges,
        // but retain explicit overflow checks for future contract changes.
        if (symbolUs > UINT64_MAX / symbolsX4) return false;
        const uint64_t product = symbolUs * symbolsX4;
        if (product > UINT64_MAX - 3u) return false;
        const uint64_t toaUs = (product + 3u) / 4u;
        if (toaUs > (UINT64_MAX - 999u) / 5u) return false;
        const uint64_t deadlineMs = 5u + (5u * toaUs + 999u) / 1000u;
        if (!deadlineMs || deadlineMs > 0x7fffffffULL || deadlineMs + rxWindowMs > txPeriodMs) return false;
        timeoutMs = static_cast<uint32_t>(deadlineMs);
        return true;
    }

    // Set only after StartTx has been selected and before sequence reservation.
    bool setPendingTxTimeout(uint32_t timeoutMs) {
        if (pending_ != Action::StartTx || timeoutMs == 0 || timeoutMs > 0x7fffffffu) return false;
        txTimeoutMs_ = timeoutMs;
        return true;
    }

    // Cancel only before the caller touches hardware, e.g. a newly latched RX
    // IRQ racing a timeout decision. No state transition or I/O is implied.
    bool cancelPending(Action action) {
        if (action == Action::None || action != pending_) return false;
        pending_ = Action::None;
        return true;
    }

    // No recovery action is sent automatically. The owner must reconcile any
    // uncertain TX outcome, verify that the radio is idle, and clear stale IRQs
    // before recovery; radio idle alone does not prove whether TX was sent.
    bool recover(bool outcomeReconciledAndIdle) {
        if (state_ != State::Fault || pending_ != Action::None || !outcomeReconciledAndIdle) return false;
        state_ = State::Idle;
        return true;
    }

    // Each non-None action must be resolved exactly once before another is
    // issued. IRQ is state-specific and belongs to the radio driver; the
    // caller must clear stale IRQ flags while transitioning radio modes.
    Action next(const Inputs& in) {
        if (pending_ != Action::None) return Action::None;
        Action action = Action::None;
        if (state_ == State::Fault) {
            // Recording can continue if the caller can safely use the ADC.
            if (in.sessionActive && in.sampleDue && in.samplingPermitted) action = Action::AcquireSample;
        } else if ((!in.radioAvailable || ((!in.sessionActive || !in.radioEnabled) && !in.drainInFlight)) && state_ != State::Idle) {
            action = Action::AbortRadio;
        } else if (!in.sessionActive && !in.drainInFlight) {
            action = Action::None;
        } else if (state_ == State::Receiving && in.irqPending) {
            action = Action::FinishRx;
        } else if (state_ == State::Transmitting && in.irqPending) {
            action = Action::FinishTx;
        } else if (state_ == State::Transmitting && in.nowMs - stateStartedMs_ >= txTimeoutMs_) {
            action = Action::TimeoutTx;
        } else if (state_ == State::Receiving && in.nowMs - stateStartedMs_ >= rxWindowMs_) {
            action = Action::TimeoutRx;
        } else if (state_ == State::StartReceive) {
            // Open the receive window immediately after TX completion.
            action = Action::StartRx;
        } else if (in.sampleDue && in.samplingPermitted) {
            action = Action::AcquireSample;
        } else if (state_ == State::Idle && !in.sampleDue && in.radioEnabled && in.radioAvailable && in.txDue && in.allowNewTx) {
            action = Action::StartTx;
        }
        pending_ = action;
        return action;
    }

    // `ok` must describe a definitive operation result, not a timeout or
    // unknown external outcome. On an unknown outcome the caller must stop
    // scheduling and reconcile the radio; do not blindly retry a transmit.
    // `nowMs` is the actual completion time of StartTx/StartRx, not request
    // time. AcquireSample success does not represent or create any record.
    bool resolve(Action action, bool ok, uint32_t nowMs) {
        if (action == Action::None || action != pending_) return false;
        pending_ = Action::None;
        switch (action) {
            case Action::StartTx:
                state_ = ok ? State::Transmitting : State::Fault;
                if (ok) stateStartedMs_ = nowMs;
                break;
            case Action::FinishTx:
                state_ = ok ? State::StartReceive : State::Fault;
                break;
            case Action::StartRx:
                state_ = ok ? State::Receiving : State::Fault;
                if (ok) stateStartedMs_ = nowMs;
                break;
            case Action::TimeoutTx:
                // A completed cleanup does not reveal whether the packet was
                // transmitted. Never re-enter Idle and auto-retry from txDue.
                state_ = State::Fault;
                break;
            case Action::FinishRx:
            case Action::TimeoutRx:
                state_ = ok ? State::Idle : State::Fault;
                break;
            case Action::AbortRadio:
                // A TX may have reached the air even if an abort succeeds.
                state_ = ok && state_ != State::Transmitting ? State::Idle : State::Fault;
                break;
            case Action::AcquireSample:
            case Action::None:
                break;
        }
        return true;
    }

private:
    uint32_t txTimeoutMs_;
    const uint32_t rxWindowMs_;
    uint32_t stateStartedMs_ = 0;
    State state_ = State::Idle;
    Action pending_ = Action::None;
};

} }  // namespace pgl::gld

