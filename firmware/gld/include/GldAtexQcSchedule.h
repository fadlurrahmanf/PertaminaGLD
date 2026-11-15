#pragma once
#include <cstdint>

namespace pgl { namespace gld {
// Isolated scheduling policy only. It never manipulates a radio, a hardware
// pin, NVS, the global Dataset admission lock or an ACK. The integration must
// hold Dataset admission BEFORE begin() and until admissionHeld() becomes false.
class GldAtexQcSchedule {
public:
    enum class State : uint8_t { Idle, StartTx, Transmitting, StartRx, Receiving, Fault };
    enum class Action : uint8_t { None, StartTx, FinishTx, StartRx, FinishRx, TimeoutTx, TimeoutRx, Abort };
    struct Input { uint32_t now; bool safePower; bool radioReady; bool irq; };
    bool begin(bool admissionAlreadyHeld, bool datasetOwnsSession, bool safePower,
               bool radioReady, bool payloadReady, bool wantsRx, uint32_t txTimeoutMs, uint32_t rxTimeoutMs) {
        if (state_ != State::Idle || !admissionAlreadyHeld || datasetOwnsSession || !safePower ||
            !radioReady || !payloadReady || txTimeoutMs == 0 || txTimeoutMs > 0x7fffffffU ||
            (wantsRx && (rxTimeoutMs == 0 || rxTimeoutMs > 0x7fffffffU))) return false;
        wantsRx_ = wantsRx; txTimeout_ = txTimeoutMs; rxTimeout_ = rxTimeoutMs;
        state_ = State::StartTx; return true;
    }
    State state() const { return state_; }
    // Fault retains the admission interlock; the owner must separately disable
    // the radio and decide whether an explicit restart/reconciliation is safe.
    bool admissionHeld() const { return state_ != State::Idle; }
    Action next(const Input& in) {
        if (pending_ != Action::None || state_ == State::Idle || state_ == State::Fault) return Action::None;
        Action action = Action::None;
        if (!in.safePower || !in.radioReady) action = Action::Abort;
        else if (state_ == State::StartTx) action = Action::StartTx;
        else if (state_ == State::Transmitting && in.irq) action = Action::FinishTx;
        else if (state_ == State::Transmitting && uint32_t(in.now - started_) >= txTimeout_) action = Action::TimeoutTx;
        else if (state_ == State::StartRx) action = Action::StartRx;
        else if (state_ == State::Receiving && in.irq) action = Action::FinishRx;
        else if (state_ == State::Receiving && uint32_t(in.now - started_) >= rxTimeout_) action = Action::TimeoutRx;
        pending_=action; return action;
    }
    bool cancelPending(Action action) {
        if (action == Action::None || pending_ != action) return false;
        pending_ = Action::None;
        return true;
    }
    // `ok` means all checked IRQ/SPI/standby operations definitively succeeded.
    // A TX timeout/abort is never retried, even if standby happens to succeed.
    bool resolve(Action action, bool ok, uint32_t now) {
        if (action == Action::None || action != pending_) return false;
        pending_=Action::None;
        switch(action) {
          case Action::StartTx: state_=ok ? State::Transmitting : State::Fault; started_=now; break;
          case Action::FinishTx: state_=!ok ? State::Fault : wantsRx_ ? State::StartRx : State::Idle; break;
          case Action::StartRx: state_=ok ? State::Receiving : State::Fault; started_=now; break;
          case Action::FinishRx: case Action::TimeoutRx: state_=ok ? State::Idle : State::Fault; break;
          case Action::TimeoutTx: state_=State::Fault; break;
          case Action::Abort: state_=(!ok || state_ == State::Transmitting) ? State::Fault : State::Idle; break;
          case Action::None: return false;
        }
        return true;
    }
private:
    State state_=State::Idle;
    Action pending_=Action::None;
    bool wantsRx_=false;
    uint32_t started_=0, txTimeout_=0, rxTimeout_=0;
};
} }
