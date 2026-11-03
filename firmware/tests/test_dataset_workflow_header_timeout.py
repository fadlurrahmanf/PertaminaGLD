"""Timeout integration contracts plus deterministic header scheduling fixture.

No firmware/native C++ compilation, board or socket is used. The fixture uses
the production adapter's ordered stages and timeout expression. Actual installed
vendor/framework source checks guard the API assumptions; it is not a substitute
for fragmented-header/next-Hello verification on the ESP32.
"""
from __future__ import annotations

import configparser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'firmware/gld/src/GldDatasetWorkflowWifi.cpp'


def body(source, signature):
    start = source.index('{', source.index(signature))
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def production_adapter():
    source = SOURCE.read_text(encoding='utf-8')
    return body(body(source, 'class CheckedServer'), 'void loop()')


def timeout_ms():
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read(ROOT / 'firmware/platformio.ini', encoding='utf-8')
    values = []
    for model in (1, 2, 3):
        flags = config[f'env:gld_model_{model}_dataset_wifi']['build_flags']
        values.append(int(re.search(r'-DWEBSOCKETS_TCP_TIMEOUT=(\d+)', flags)[1]))
    if len(set(values)) != 1:
        raise AssertionError('Three final models must keep the same vendor deadline')
    return values[0]


def adapter_seconds(milliseconds):
    # Read the production expression instead of duplicating its constant.
    match = re.search(r'timeoutSeconds\s*=\s*\(WEBSOCKETS_TCP_TIMEOUT\s*\+\s*(\d+)u\)\s*/\s*(\d+)u', production_adapter())
    if not match:
        raise AssertionError('Review the timeout conversion when its expression changes')
    return (milliseconds + int(match[1])) // int(match[2])


def production_stages():
    signatures = {
        'handleNewClients();': 'accept',
        'client.tcp->setTimeout(timeoutSeconds);': 'normalize',
        'WebSocketsServerCore::loop();': 'parse',
    }
    source = production_adapter()
    return [stage for _, stage in sorted((source.index(token), stage) for token, stage in signatures.items())]


class HeaderClient:
    """Virtual-clock fixture for Stream's timeout-per-character behavior.

    A disconnect while timedRead is waiting does not shortcut its timeout,
    matching the actual ESP32 Stream.cpp. Times/chunks are deterministic.
    """
    def __init__(self, chunks, disconnect_at=None):
        self.chunks = list(chunks)
        self.disconnect_at = disconnect_at
        self.connected = True
        self.now = 0
        self.pending = bytearray()
        self.stream_timeout = 0

    def esp32_set_timeout(self, seconds):
        self.stream_timeout = seconds * 1000

    def timed_read(self):
        deadline = self.now + self.stream_timeout
        while True:
            if self.disconnect_at is not None and self.now >= self.disconnect_at:
                self.connected = False
                self.chunks.clear()
            while self.chunks and self.chunks[0][0] <= self.now:
                _, chunk = self.chunks.pop(0)
                self.pending.extend(chunk)
            if self.pending:
                value = self.pending.pop(0)
                return value
            if self.now >= deadline:
                return -1
            # Advance virtual idle reads; disconnect does not end timedRead.
            next_chunk = self.chunks[0][0] if self.chunks else deadline
            next_close = self.disconnect_at if self.connected and self.disconnect_at is not None else deadline
            self.now = min(deadline, max(self.now + 1, min(next_chunk, next_close)))

    def read_header_line(self):
        result = bytearray()
        value = self.timed_read()
        while value >= 0 and value != ord('\n'):
            result.append(value)
            value = self.timed_read()
        return bytes(result)


def process_header(client, stages):
    line = None
    for stage in stages:
        if stage == 'accept':
            # Actual vendor newClient passes the ms macro to an ESP32
            # seconds setter on every accepted client, overwriting old state.
            client.esp32_set_timeout(timeout_ms())
        elif stage == 'normalize':
            client.esp32_set_timeout(adapter_seconds(timeout_ms()))
        elif stage == 'parse':
            line = client.read_header_line()
    return line, client.now


class WorkflowHeaderTimeoutTests(unittest.TestCase):
    def test_production_order_normalizes_after_vendor_accept_before_first_header(self):
        source = production_adapter()
        self.assertEqual(production_stages(), ['accept', 'normalize', 'parse'])
        self.assertLess(source.index('if (!_runnning) return'), source.index('WEBSOCKETS_YIELD()'))
        self.assertLess(source.index('WEBSOCKETS_YIELD()'), source.index('handleNewClients()'))
        self.assertNotIn('WebSocketsServer::loop()', source)
        self.assertIn('client.status == WSC_HEADER', source)
        self.assertIn('client.tcp->getTimeout() != timeoutSeconds * 1000u', source)
        complete = SOURCE.read_text(encoding='utf-8')
        self.assertIn('CheckedServer socket;', complete)
        self.assertIn('socket.loop();', body(complete, 'void transmitter(void*)'))

    def test_vendor_deadline_stays_milliseconds_for_every_model(self):
        self.assertEqual(timeout_ms(), 1000, 'Never fix the seconds API by retuning the vendor macro to 1 ms')
        for milliseconds, seconds in ((1, 1), (999, 1), (1000, 1), (1001, 2), (2000, 2)):
            self.assertEqual(adapter_seconds(milliseconds), seconds)

    def test_fragmented_header_within_deadline_is_preserved(self):
        client = HeaderClient([(0, b'GET /dataset HTTP/1.1\r'), (50, b'\n')])
        line, elapsed = process_header(client, production_stages())
        self.assertEqual(line, b'GET /dataset HTTP/1.1\r')
        self.assertEqual(elapsed, 50)
        self.assertEqual(client.stream_timeout, 1000)

    def test_aborted_header_returns_then_next_healthy_client_is_processed(self):
        abandoned = HeaderClient([(0, b'GET /data')], disconnect_at=20)
        first, blocked = process_header(abandoned, production_stages())
        self.assertEqual(first, b'GET /data')
        self.assertEqual(blocked, 1000)
        self.assertFalse(abandoned.connected)
        healthy = HeaderClient([(0, b'GET /dataset HTTP/1.1\r\n')])
        next_line, additional = process_header(healthy, production_stages())
        self.assertEqual(next_line, b'GET /dataset HTTP/1.1\r')
        self.assertLessEqual(blocked + additional, 1000)

    def test_fixture_detects_unfixed_or_wrongly_ordered_normalization(self):
        for stages in (['accept', 'parse'], ['normalize', 'accept', 'parse']):
            _, elapsed = process_header(HeaderClient([(0, b'GET /data')], disconnect_at=20), stages)
            self.assertEqual(elapsed, 1000000, 'Old unit mismatch must reproduce a 1,000-second wait')


class ActualDependencyTimeoutContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        framework = Path.home() / '.platformio/packages/framework-arduinoespressif32'
        vendor = ROOT / 'firmware/.pio/workflow-libdeps-model2/gld_model_2_dataset_workflow_wifi/WebSockets/src'
        if not (framework / 'cores/esp32/Stream.cpp').is_file() or not (vendor / 'WebSocketsServer.cpp').is_file():
            raise unittest.SkipTest('Installed framework/vendor sources unavailable; adapter fixture is still checked')
        cls.server = (vendor / 'WebSocketsServer.cpp').read_text(encoding='utf-8')
        cls.header = (vendor / 'WebSocketsServer.h').read_text(encoding='utf-8')
        cls.stream = (framework / 'cores/esp32/Stream.cpp').read_text(encoding='utf-8')
        cls.client = (framework / 'libraries/WiFi/src/WiFiClient.cpp').read_text(encoding='utf-8')

    def test_actual_vendor_accept_resets_timeout_and_core_does_not_accept_again(self):
        accept = body(self.server, 'WSclient_t * WebSocketsServerCore::newClient(')
        self.assertIn('client->tcp->setTimeout(WEBSOCKETS_TCP_TIMEOUT)', accept)
        outer = body(self.server, 'void WebSocketsServer::loop(void)')
        self.assertLess(outer.index('handleNewClients()'), outer.index('WebSocketsServerCore::loop()'))
        core = body(self.server, 'void WebSocketsServerCore::loop(void)')
        self.assertIn('handleClientData()', core)
        self.assertNotIn('handleNewClients()', core)
        self.assertIn("client->tcp->readStringUntil('\\n')", body(self.server, 'void WebSocketsServerCore::handleClientData('))
        self.assertNotRegex(self.header, r'virtual\s+.*\b(?:newClient|handleNewClients)\s*\(')

    def test_actual_esp32_api_and_stream_match_fixture_units_and_disconnect_behavior(self):
        setter = body(self.client, 'int WiFiClient::setTimeout(uint32_t seconds)')
        self.assertIn('Client::setTimeout(seconds * 1000)', setter)
        timed = body(self.stream, 'int Stream::timedRead()')
        self.assertIn('millis() - _startMillis < _timeout', timed)
        self.assertNotIn('connected()', timed)
        line = body(self.stream, 'String Stream::readStringUntil(')
        self.assertIn('timedRead()', line)


if __name__ == '__main__':
    unittest.main()
