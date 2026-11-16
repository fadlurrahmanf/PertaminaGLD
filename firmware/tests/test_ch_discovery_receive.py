from pathlib import Path


def test_config_request_arms_receiver_once_and_reports_tx_result():
    source = Path('firmware/ch/src/ChStarMeshRuntimeMain.cpp').read_text(encoding='utf-8')
    transmit = source[source.index('bool transmitRadio('):source.index('bool enqueueRelayFrame(')]
    request = source[source.index('void sendConfigRequest()'):source.index('void sendConfigResponse(')]
    assert 'radio->setPacketReceivedAction(onMeshPacketReceived)' in transmit
    assert 'startMeshReceive("after-tx")' in transmit
    assert 'startMeshReceive(' not in request
    assert 'const bool txOk = transmitRadio(' in request
    assert 'CH_CONFIG_REQUEST_TX parentId=0x%04X txOk=%u' in request


def test_radiolib_rearming_clears_pending_irq():
    source = Path('firmware/lib/RadioLib/src/modules/SX126x/SX126x.cpp').read_text(encoding='utf-8')
    common = source[source.index('int16_t SX126x::startReceiveCommon('):source.index('int16_t SX126x::readData(')]
    assert 'standby()' in common
    assert 'clearIrqStatus()' in common


def test_hello_and_retry_do_not_rearm_after_transmit():
    source = Path('firmware/ch/src/ChStarMeshRuntimeMain.cpp').read_text(encoding='utf-8')
    initial = source[source.index('bool sendHello()'):source.index('void retryHelloIfNeeded()')]
    retry = source[source.index('void retryHelloIfNeeded()'):source.index('void sendConfigRequest()')]
    assert 'transmitRadio(meshRadio' in initial and 'startMeshReceive(' not in initial
    assert 'transmitRadio(meshRadio' in retry and 'startMeshReceive(' not in retry
    assert 'startMeshAckTransaction(MeshAckKind::Hello' in initial
    assert 'meshAck.retryCount++' in retry
