#include "GldWorkflowRadioSchedule.h"
#include <cassert>
#include <cstdint>
#include <initializer_list>

using Schedule = pgl::gld::GldWorkflowRadioSchedule;
using Action = Schedule::Action;
using State = Schedule::State;
using Inputs = Schedule::Inputs;

static Inputs input(uint32_t now) {
    return Inputs{now, true, true, true, false, false, false, true, false, true};
}

static void settle(Schedule& scheduler, const Inputs& in, Action expected, bool ok = true) {
    assert(scheduler.next(in) == expected);
    assert(expected != Action::None);
    assert(scheduler.next(in) == Action::None);  // no duplicate outstanding action
    assert(scheduler.resolve(expected, ok, in.nowMs));
}

static void normalAndIrqPriority() {
    Schedule s(3000, 2000);
    Inputs in = input(100);
    in.sampleDue = true; in.txDue = true;
    settle(s, in, Action::AcquireSample);  // no synthetic samples or time updates
    in.sampleDue = false;
    settle(s, in, Action::StartTx);
    assert(s.state() == State::Transmitting);
    in.nowMs = 600; in.sampleDue = true;
    settle(s, in, Action::AcquireSample);
    in.irqPending = true;
    settle(s, in, Action::FinishTx);       // IRQ wins over due sample
    in.irqPending = false;
    settle(s, in, Action::StartRx);         // RX window is opened promptly
    assert(s.state() == State::Receiving);
    in.nowMs = 1100;
    settle(s, in, Action::AcquireSample);
    in.nowMs = 2600; in.irqPending = true;
    settle(s, in, Action::FinishRx);        // received packet beats deadline and sample
    assert(s.state() == State::Idle);
    assert(!s.resolve(Action::FinishRx, true, in.nowMs));
}

static void rolloverAndTimeouts() {
    Schedule s(1000, 2000);
    Inputs in = input(UINT32_MAX - 499);
    in.txDue = true;
    settle(s, in, Action::StartTx);
    in.txDue = false; in.nowMs = 500;       // exactly 1000 ms across rollover
    in.sampleDue = true;
    settle(s, in, Action::TimeoutTx);       // no RX after TX timeout
    assert(s.state() == State::Fault);
    in.sampleDue = false; in.txDue = true;
    assert(s.next(in) == Action::None);     // timeout cannot silently retransmit
    assert(!s.recover(false));
    assert(s.recover(true));                // explicit outcome + idle reconciliation
    in.nowMs = UINT32_MAX - 999;
    settle(s, in, Action::StartTx);
    in.irqPending = true; in.txDue = false;
    settle(s, in, Action::FinishTx);
    in.irqPending = false;
    settle(s, in, Action::StartRx);
    in.nowMs = 1000;                        // exactly 2000 ms across rollover
    settle(s, in, Action::TimeoutRx);
    assert(s.state() == State::Idle);
}

static void failureAndExplicitRecovery() {
    Schedule s(1000, 2000);
    Inputs in = input(0); in.txDue = true;
    settle(s, in, Action::StartTx, false);
    assert(s.state() == State::Fault);
    assert(s.next(in) == Action::None);     // never retry an uncertain radio operation
    assert(!s.recover(false));
    in.sampleDue = true;
    settle(s, in, Action::AcquireSample);   // recording may continue when safe
    assert(s.state() == State::Fault);
    assert(s.recover(true));
    in.sampleDue = false;
    settle(s, in, Action::StartTx);
    in.radioEnabled = false;
    settle(s, in, Action::AbortRadio, false);
    assert(s.state() == State::Fault);
    assert(!s.recover(false));
    assert(s.recover(true));
}

static void unavailableAndSessionStop() {
    Schedule s(1000, 2000);
    Inputs in = input(0); in.radioAvailable = false; in.txDue = true;
    assert(s.next(in) == Action::None);
    in.sampleDue = true;
    settle(s, in, Action::AcquireSample);   // no radio does not stop acquisition
    in.radioAvailable = true; in.samplingPermitted = false;
    assert(s.next(in) == Action::None);
    in.sampleDue = false;
    settle(s, in, Action::StartTx);
    in.sessionActive = false; in.irqPending = true;
    settle(s, in, Action::AbortRadio);      // session/power safety beats IRQ
    assert(s.state() == State::Fault);      // aborted TX outcome is uncertain
    assert(s.next(in) == Action::None);
    in.sessionActive = true; in.txDue = true; in.irqPending = false;
    assert(s.next(in) == Action::None);     // no retry without reconciliation
    assert(s.recover(true));
}

static void outstandingAndRadioErrors() {
    Schedule s(1000, 2000);
    Inputs in = input(0); in.txDue = true;
    assert(s.next(in) == Action::StartTx);
    assert(!s.resolve(Action::StartRx, true, 0));
    assert(s.pending() == Action::StartTx);
    assert(s.resolve(Action::StartTx, true, 0));
    in.txDue = false; in.irqPending = true;
    settle(s, in, Action::FinishTx);
    in.irqPending = false;
    settle(s, in, Action::StartRx, false);
    assert(s.state() == State::Fault);
    assert(s.recover(true));
    in.txDue = true;
    settle(s, in, Action::StartTx);
    in.irqPending = true; in.txDue = false;
    settle(s, in, Action::FinishTx);
    in.irqPending = false;
    settle(s, in, Action::StartRx);
    in.irqPending = true;
    settle(s, in, Action::FinishRx, false);
    assert(s.state() == State::Fault);
}

static void irqRacesTimeout() {
    Schedule s(1000, 2000);
    Inputs in = input(0); in.txDue = true;
    settle(s, in, Action::StartTx);
    in.txDue = false; in.irqPending = true;
    settle(s, in, Action::FinishTx);
    in.irqPending = false;
    settle(s, in, Action::StartRx);
    in.nowMs = 2000;
    assert(s.next(in) == Action::TimeoutRx);
    assert(!s.cancelPending(Action::FinishRx));
    assert(s.cancelPending(Action::TimeoutRx));
    in.irqPending = true;
    settle(s, in, Action::FinishRx);
    assert(s.state() == State::Idle);
}

static void interruptedBatchIsRetriedAfterRx() {
    Schedule s(1000, 2000);
    Inputs in = input(0); in.txDue = true;
    settle(s, in, Action::StartTx);
    in.txDue = false; in.irqPending = true;
    settle(s, in, Action::FinishTx);
    in.irqPending = false;
    settle(s, in, Action::StartRx);
    in.nowMs = 500; in.sampleDue = true;
    assert(s.next(in) == Action::AcquireSample);
    // Fake ADC observes IRQ after channel 3. The owner discards the local
    // partial array and leaves the same acquisition deadline due.
    const unsigned completedChannels = 3;
    unsigned committedRecords = 0;
    assert(completedChannels < 8 && committedRecords == 0);
    assert(s.resolve(Action::AcquireSample, false, in.nowMs));
    in.irqPending = true; in.nowMs = 501;
    settle(s, in, Action::FinishRx);
    in.irqPending = false; in.nowMs = 502;
    assert(s.next(in) == Action::AcquireSample);
    committedRecords += 1;  // fake owner commits one complete batch
    assert(s.resolve(Action::AcquireSample, true, in.nowMs));
    assert(committedRecords == 1);
}

static void syntheticCadence() {
    // Idealized zero-duration fake operations exercise scheduler ordering only;
    // they are not evidence of device timing or RF reception.
    Schedule s(3000, 2000);
    uint32_t nextSample = 0, nextTx = 0, txStart = 0, rxStart = 0;
    unsigned samples = 0, packets = 0;
    for (uint32_t now = 0; now < 30000; now += 5) {
        Inputs in = input(now);
        in.sampleDue = now >= nextSample;
        in.txDue = now >= nextTx;
        in.irqPending = (s.state() == State::Transmitting && now - txStart >= 100) ||
                        (s.state() == State::Receiving && now - rxStart >= 700);
        const Action action = s.next(in);
        if (action == Action::None) continue;
        if (action == Action::AcquireSample) {
            assert(now == nextSample);
            nextSample += 500;
            ++samples;
        } else if (action == Action::StartTx) {
            nextTx += 10000;
            txStart = now;
        } else if (action == Action::StartRx) {
            rxStart = now;
        } else if (action == Action::FinishRx) {
            ++packets;
        }
        assert(s.resolve(action, true, now));
    }
    assert(samples == 60 && packets == 3);
}

static void pauseStopAndPowerPriority() {
    for (bool releaseLease : {false, true}) {
        Schedule s(3000, 2000);
        Inputs in = input(0); in.txDue = true;
        settle(s, in, Action::StartTx);
        // PAUSE retains lease; STOP may release it after replay drain.
        in.sessionActive = !releaseLease; in.radioEnabled = false;
        in.allowNewTx = false; in.drainInFlight = true; in.sampleDue = false;
        assert(s.next(in) == Action::None);
        in.irqPending = true; in.nowMs = 200;
        settle(s, in, Action::FinishTx);
        in.irqPending = false;
        settle(s, in, Action::StartRx);
        in.nowMs = 2200;
        settle(s, in, Action::TimeoutRx);
        assert(s.state() == State::Idle);
        assert(s.next(in) == Action::None);  // no new TX after pause/stop
    }
    // Pause during RX may finish a received packet normally.
    Schedule rx(3000, 2000);
    Inputs in = input(0); in.txDue = true;
    settle(rx, in, Action::StartTx); in.irqPending = true;
    settle(rx, in, Action::FinishTx); in.irqPending = false;
    settle(rx, in, Action::StartRx);
    in.radioEnabled = false; in.allowNewTx = false; in.drainInFlight = true;
    in.irqPending = true;
    settle(rx, in, Action::FinishRx);
    assert(rx.state() == State::Idle);

    // Unsafe power while TX is in flight must not be disguised as a drain.
    Schedule power(3000, 2000);
    in = input(0); in.txDue = true; settle(power, in, Action::StartTx);
    in.radioEnabled = false; in.drainInFlight = false; in.samplingPermitted = false;
    settle(power, in, Action::AbortRadio);
    assert(power.state() == State::Fault);
    in.txDue = true; assert(power.next(in) == Action::None);
}

static void deadlineAdmission() {
    uint32_t timeout = 123;
    assert(Schedule::txTimeoutFromAppliedConfig(125000, 7, 5, 8, 39, 10000, 2000, timeout));
    assert(timeout > 5 && timeout + 2000 <= 10000);
    assert(!Schedule::txTimeoutFromAppliedConfig(0, 7, 5, 8, 39, 10000, 2000, timeout));
    assert(!Schedule::txTimeoutFromAppliedConfig(125000, 4, 5, 8, 39, 10000, 2000, timeout));
    assert(!Schedule::txTimeoutFromAppliedConfig(125000, 7, 9, 8, 39, 10000, 2000, timeout));
    assert(!Schedule::txTimeoutFromAppliedConfig(7799, 12, 8, 65535, 255, 10000, 2000, timeout));
    Schedule s(0, 2000); Inputs in = input(UINT32_MAX - 99); in.txDue = true;
    assert(!s.setPendingTxTimeout(10));
    assert(s.next(in) == Action::StartTx);
    assert(!s.setPendingTxTimeout(0));
    assert(s.setPendingTxTimeout(200));
    assert(s.resolve(Action::StartTx, true, in.nowMs));
    in.txDue = false; in.nowMs = 100;
    settle(s, in, Action::TimeoutTx);
    assert(s.state() == State::Fault);
}

int main() {
    normalAndIrqPriority();
    rolloverAndTimeouts();
    failureAndExplicitRecovery();
    unavailableAndSessionStop();
    outstandingAndRadioErrors();
    irqRacesTimeout();
    interruptedBatchIsRetriedAfterRx();
    syntheticCadence();
    pauseStopAndPowerPriority();
    deadlineAdmission();
}

