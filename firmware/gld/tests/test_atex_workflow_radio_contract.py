"""Source contracts for the isolated ATEX prototype; no hardware claims."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
WORKFLOW = (ROOT / "firmware/gld/src/GldDatasetWorkflowWifi.cpp").read_text(encoding="utf-8")


def body(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[opening:pos + 1]
    raise AssertionError("unclosed function")


class AtexWorkflowRadioContracts(unittest.TestCase):
    def test_authenticated_downlink_never_commits_or_reboots(self):
        section = body(MAIN, "void reportWorkflowDownlink(")
        self.assertIn("candidateCommandId = runtimeConfig.lastDownlinkCommandId", section)
        self.assertIn("candidateCommandId, requestedMode", section)
        self.assertNotIn("saveDownlinkReplayState(", section)
        self.assertNotIn("onModeCmd(", section)
        self.assertNotIn("ESP.restart", section)
        self.assertNotIn("runtimeConfig.lastDownlinkCommandId =", section)

    def test_radio_start_requires_live_and_reconciled_24v_and_valid_inference(self):
        section = body(MAIN, "bool serviceAtexWorkflowRadio(")
        self.assertIn("external24VPowerMode && !batteryPowerMode", section)
        self.assertIn("pgl::gld::readGldExternalPower()", section)
        self.assertIn("sampling && safePower && lastInferenceValid", section)
        self.assertIn("runtimeConfig.aesKeyPresent && runtimeConfig.aesKeyId != 0", section)
        self.assertIn("radioReady = false", section)
        self.assertIn('failSession("radio_fault")', section)
        self.assertIn("startTransmit(", section)
        self.assertNotIn("->transmit(", section)

    def test_interrupt_discards_partial_batch_and_preserves_deadline(self):
        capture = body(MAIN, "bool captureDatasetWifi(")
        self.assertIn("if (loraRxFlag) { workflowCaptureInterrupted = true; return false; }", capture)
        self.assertLess(capture.index("if (loraRxFlag)"), capture.index("ads.readChannel(channel)"))
        self.assertLess(capture.index("reading.saturated"), capture.rindex("if (loraRxFlag)"))
        self.assertIn("isGldDatasetGainValid(reading.gain)", capture)
        acquire = body(WORKFLOW, "void acquireDueSample(")
        retry = acquire.index("retryInterruptedCapture()")
        self.assertLess(retry, acquire.index("resetPrediction()"))
        self.assertLess(retry, acquire.index("retained.append("))
        self.assertIn("state.nextDue -= INTERVAL_MS", acquire)
        self.assertIn("isReady != nullptr && isReady()", acquire[retry:acquire.index("retained.append(")])

    def test_at_ex_dataset_requires_confirmed_external_power(self):
        ready = body(MAIN, "bool datasetWifiReady(")
        self.assertIn("PGL_GLD_BOARD_PROFILE_GLD_ATEX", ready)
        self.assertIn("external24VPowerMode", ready)
        self.assertIn("GldWorkflowRadioSchedule::State::Fault", ready)
        self.assertIn("!batteryPowerMode", ready)
        self.assertIn("pgl::gld::readGldExternalPower()", ready)
        begin = body(MAIN, "void beginDatasetWorkflowIfNeeded(")
        self.assertIn("!external24VPowerMode", begin)
        self.assertIn("!pgl::gld::readGldExternalPower()", begin)

    def test_irq_timeout_race_does_not_silently_drop_packet(self):
        section = body(MAIN, "bool serviceAtexWorkflowRadio(")
        self.assertIn("action == Action::TimeoutRx", section)
        self.assertIn("RADIOLIB_SX126X_IRQ_RX_DONE", section)
        self.assertIn("workflowRadioScheduler.cancelPending(action)", section)
        self.assertIn("getIrqFlagsChecked(irq)", section)
        self.assertIn("getPacketLengthChecked(len)", section)
        self.assertNotIn("getIrqFlags()", section)
        self.assertNotIn("getPacketLength()", section)
        self.assertIn("RADIOLIB_SX126X_IRQ_TX_DONE", section)

    def test_drain_gates_start_and_summary_and_retains_fault(self):
        section = body(MAIN, "bool serviceAtexWorkflowRadio(")
        self.assertIn("setRadioDrainBlocksStart", section)
        self.assertIn("const bool drain = !sampling && inFlight && safePower", section)
        self.assertIn("txTimeoutFromAppliedConfig", section)
        self.assertLess(section.index("txTimeoutFromAppliedConfig"), section.index("buildTxSnapshot"))
        self.assertIn("radioQuarantined=1 standbyState=", section)
        self.assertIn("RADIOLIB_ERR_CRC_MISMATCH", section)
        self.assertIn("RADIOLIB_ERR_LORA_HEADER_DAMAGED", section)
        failure = body(WORKFLOW, "void failSession(")
        self.assertIn("state.sessionLease && !state.summarySent", failure)
        poll = body(WORKFLOW, "void poll(")
        self.assertIn("!radioDrainBlocksStart.load()", poll)
        start = body(WORKFLOW, "void process(")
        self.assertIn('ackLocked(command, false, "radio_transaction_draining")', start)
        self.assertIn('isReady == nullptr || !isReady()', start)

    def test_timeout_uses_last_successful_radio_configuration_before_sequence(self):
        begin = body(MAIN, "bool beginLoraRadio() {")
        self.assertLess(begin.index("workflowAppliedRadio.valid = false"), begin.index("loraRadio->begin("))
        self.assertGreater(begin.index("workflowAppliedRadio.valid = true"), begin.index("state != RADIOLIB_ERR_NONE"))
        for field in ("bandwidthKhz", "sf", "cr", "preamble"):
            self.assertIn("workflowAppliedRadio." + field, begin)
        service = body(MAIN, "bool serviceAtexWorkflowRadio(")
        self.assertLess(service.index("txTimeoutFromAppliedConfig"), service.index("buildTxSnapshot"))
        self.assertNotIn("getTimeOnAir(", service)

    def test_fault_stops_session_without_dropping_retained_records(self):
        failure = body(WORKFLOW, "void failSession(")
        self.assertIn("stopLocked(reason, true)", failure)
        self.assertNotIn("retained.", failure)
        stop = body(WORKFLOW, "void stopLocked(")
        self.assertIn("state.incomplete = state.incomplete || incomplete", stop)
        self.assertIn("state.summaryPending", stop)
        self.assertNotIn("retained.clear", stop)


if __name__ == "__main__":
    unittest.main()
