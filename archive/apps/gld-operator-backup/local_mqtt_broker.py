"""Tiny MQTT 3.1.1 broker for the GLD operator bench.

This broker intentionally implements only the subset the GLD firmware and the
operator bridge need: CONNECT, PUBLISH, SUBSCRIBE, PINGREQ, and DISCONNECT with
QoS 0 delivery. It is not a production broker; it is a local bench dependency
so the GLD dataset path can run without Node-RED/Aedes.
"""

from __future__ import annotations

import socket
import struct
import threading
from dataclasses import dataclass, field
from typing import Callable


LogFn = Callable[[str], None]


def _enc_remaining(length: int) -> bytes:
    out = bytearray()
    while True:
        byte = length & 0x7F
        length >>= 7
        if length:
            byte |= 0x80
        out.append(byte)
        if not length:
            return bytes(out)


def _read_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data.extend(chunk)
    return bytes(data)


def _read_packet(sock: socket.socket) -> tuple[int, bytes]:
    header = _read_exact(sock, 1)[0]
    remaining = 0
    multiplier = 1
    while True:
        byte = _read_exact(sock, 1)[0]
        remaining += (byte & 0x7F) * multiplier
        if not (byte & 0x80):
            break
        multiplier <<= 7
        if multiplier > 128 * 128 * 128:
            raise ValueError("bad MQTT remaining length")
    return header, _read_exact(sock, remaining)


def _read_utf(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(data):
        raise ValueError("truncated MQTT string")
    length = struct.unpack(">H", data[offset:offset + 2])[0]
    offset += 2
    end = offset + length
    if end > len(data):
        raise ValueError("truncated MQTT string value")
    return data[offset:end].decode("utf-8", errors="replace"), end


def _topic_matches(subscription: str, topic: str) -> bool:
    sub_parts = subscription.split("/")
    topic_parts = topic.split("/")
    for index, part in enumerate(sub_parts):
        if part == "#":
            return index == len(sub_parts) - 1
        if index >= len(topic_parts):
            return False
        if part != "+" and part != topic_parts[index]:
            return False
    return len(topic_parts) == len(sub_parts)


@dataclass(eq=False)
class _Client:
    sock: socket.socket
    addr: tuple[str, int]
    broker: "LocalMqttBroker"
    client_id: str = ""
    subscriptions: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def send_packet(self, packet_type: int, payload: bytes = b"") -> None:
        packet = bytes([packet_type]) + _enc_remaining(len(payload)) + payload
        with self.lock:
            self.sock.sendall(packet)

    def send_publish(self, topic: str, payload: bytes) -> None:
        topic_bytes = topic.encode("utf-8")
        body = struct.pack(">H", len(topic_bytes)) + topic_bytes + payload
        self.send_packet(0x30, body)

    def run(self) -> None:
        try:
            while not self.broker.stopping.is_set():
                header, data = _read_packet(self.sock)
                packet_type = header & 0xF0
                qos = (header >> 1) & 0x03
                if packet_type == 0x10:
                    self._handle_connect(data)
                elif packet_type == 0x30:
                    self._handle_publish(data, qos)
                elif packet_type == 0x80:
                    self._handle_subscribe(data)
                elif packet_type == 0xA0:
                    self._handle_unsubscribe(data)
                elif packet_type == 0xC0:
                    self.send_packet(0xD0)
                elif packet_type == 0xE0:
                    break
                else:
                    self.broker.log(f"MQTT_BROKER_UNSUPPORTED packet=0x{packet_type:02X} client={self.client_id}")
        except Exception as exc:
            if not self.broker.stopping.is_set():
                self.broker.log(f"MQTT_BROKER_CLIENT_CLOSED client={self.client_id or self.addr[0]} reason={exc}")
        finally:
            self.broker.remove_client(self)
            try:
                self.sock.close()
            except OSError:
                pass

    def _handle_connect(self, data: bytes) -> None:
        proto, offset = _read_utf(data, 0)
        if offset + 4 > len(data):
            raise ValueError("truncated CONNECT")
        level = data[offset]
        flags = data[offset + 1]
        offset += 4
        self.client_id, offset = _read_utf(data, offset)
        if flags & 0x80:
            _, offset = _read_utf(data, offset)
        if flags & 0x40:
            _, offset = _read_utf(data, offset)
        if proto not in {"MQTT", "MQIsdp"}:
            raise ValueError(f"unsupported protocol {proto}")
        if level == 5:
            self.send_packet(0x20, b"\x00\x00\x00")
        else:
            self.send_packet(0x20, b"\x00\x00")
        self.broker.log(f"MQTT_BROKER_CONNECT client={self.client_id or '-'} addr={self.addr[0]}:{self.addr[1]}")

    def _handle_subscribe(self, data: bytes) -> None:
        if len(data) < 2:
            raise ValueError("truncated SUBSCRIBE")
        packet_id = data[:2]
        offset = 2
        granted = bytearray()
        with self.broker.lock:
            while offset < len(data):
                topic, offset = _read_utf(data, offset)
                if offset >= len(data):
                    raise ValueError("truncated SUBSCRIBE qos")
                offset += 1
                self.subscriptions.add(topic)
                granted.append(0)
                self.broker.log(f"MQTT_BROKER_SUB client={self.client_id or '-'} topic={topic}")
        self.send_packet(0x90, packet_id + bytes(granted or b"\x00"))

    def _handle_unsubscribe(self, data: bytes) -> None:
        if len(data) < 2:
            raise ValueError("truncated UNSUBSCRIBE")
        packet_id = data[:2]
        offset = 2
        with self.broker.lock:
            while offset < len(data):
                topic, offset = _read_utf(data, offset)
                self.subscriptions.discard(topic)
        self.send_packet(0xB0, packet_id)

    def _handle_publish(self, data: bytes, qos: int) -> None:
        topic, offset = _read_utf(data, 0)
        packet_id = b""
        if qos:
            packet_id = data[offset:offset + 2]
            offset += 2
        payload = data[offset:]
        self.broker.publish(topic, payload)
        if qos == 1 and packet_id:
            self.send_packet(0x40, packet_id)


class LocalMqttBroker:
    def __init__(self, host: str, port: int, log: LogFn | None = None) -> None:
        self.host = host
        self.port = port
        self.log = log or print
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.clients: set[_Client] = set()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self.stopping.is_set()

    def start(self) -> None:
        if self.running:
            return
        self.stopping.clear()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(20)
        server.settimeout(1.0)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="gld-local-mqtt-broker", daemon=True)
        self._thread.start()
        self.log(f"MQTT_BROKER_LISTEN host={self.host} port={self.port}")

    def stop(self) -> None:
        self.stopping.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        with self.lock:
            clients = list(self.clients)
        for client in clients:
            try:
                client.sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def remove_client(self, client: _Client) -> None:
        with self.lock:
            self.clients.discard(client)
        self.log(f"MQTT_BROKER_DISCONNECT client={client.client_id or '-'}")

    def publish(self, topic: str, payload: bytes) -> None:
        with self.lock:
            targets = [
                client
                for client in self.clients
                if any(_topic_matches(sub, topic) for sub in client.subscriptions)
            ]
        self.log(f"MQTT_BROKER_PUBLISH topic={topic} bytes={len(payload)} subscribers={len(targets)}")
        for client in targets:
            try:
                client.send_publish(topic, payload)
            except OSError:
                self.remove_client(client)

    def _serve(self) -> None:
        while not self.stopping.is_set():
            try:
                assert self._server is not None
                sock, addr = self._server.accept()
                sock.settimeout(120)
                client = _Client(sock=sock, addr=addr, broker=self)
                with self.lock:
                    self.clients.add(client)
                threading.Thread(target=client.run, name=f"gld-mqtt-client-{addr[0]}:{addr[1]}", daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                if not self.stopping.is_set():
                    self.log("MQTT_BROKER_ACCEPT_FAILED")
                break
