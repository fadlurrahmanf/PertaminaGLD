from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import json
import pathlib
import re


APPFRAME_MAGIC = 0xAA
APPFRAME_OVERHEAD = 10
STAR_MAX_PAYLOAD = 64
MESH_MAX_PAYLOAD = 80

MSG_SENSOR_DATA = 0x10
MSG_SERVER_PULL_REQUEST = 0x30
MSG_CLUSTER_DATA_RESPONSE = 0x31
FLAG_ALARM_ACK = 0x40
FLAG_GLD_EXT_POWER = 0x80

TYPE_GLD_NORMAL_BATTERY = 0x10
TYPE_GLD_NORMAL_EXTERNAL = 0x90
TYPE_GLD_ALARM_BATTERY = 0x50
TYPE_GLD_ALARM_EXTERNAL = 0xD0

GLD_GAS_CLEAR = 0
GLD_GAS_LPG = 1
GLD_GAS_METHANE = 2
GLD_GAS_PROPANE = 3
GLD_GAS_BUTANE = 4
GLD_LEL_THRESHOLD_PERCENT = 30
GLD_PLAINTEXT_PAYLOAD_SIZE = 4
GLD_ENCRYPTED_PAYLOAD_SIZE = 29
GLD_RECORD_HEADER_SIZE = 5
CLUSTER_DATA_RESPONSE_HEADER_SIZE = 6

NC_FLAG_ALARM = 0x01
NC_FLAG_EXT_POWER = 0x10

DATA_OK = 0x00
DATA_EMPTY = 0x01
DATA_NOT_AVAIL = 0x02
DATA_STALE = 0x03


class AlarmQueue:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.items = []

    def enqueue_if_absent(self, entry):
        if not entry.alarm:
            return "NotAlarm"
        for item in self.items:
            if item["node_id"] == entry.node_id and item["seq"] == entry.current_seq:
                same = (
                    item["flags"] == entry.flags
                    and item["payload"] == entry.payload
                )
                return "AlreadyQueued" if same else "Conflict"
        if len(self.items) >= self.capacity:
            return "Full"
        self.items.append(
            {
                "node_id": entry.node_id,
                "seq": entry.current_seq,
                "flags": entry.flags,
                "payload": entry.payload,
            }
        )
        return "Queued"

    def remove(self, node_id: int, seq: int):
        self.items = [item for item in self.items if not (item["node_id"] == node_id and item["seq"] == seq)]


class TxQueue:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.items = []

    def enqueue(self, kind: str, frame: bytes, node_id: int = 0, gld_seq: int = 0, selected=None):
        if len(self.items) >= self.capacity:
            return "Full"
        self.items.append(
            {
                "kind": kind,
                "frame": frame,
                "node_id": node_id,
                "gld_seq": gld_seq,
                "selected": selected or [],
            }
        )
        return "Ok"

    def pop_success(self, entries, alarm_queue):
        item = self.items.pop(0)
        if item["kind"] == "ClusterDataResponse":
            for selected in item["selected"]:
                if isinstance(selected, tuple):
                    index, expected_seq = selected
                    if entries[index].current_seq != expected_seq:
                        continue
                else:
                    index = selected
                entries[index].sent_seq = entries[index].current_seq
        else:
            for entry in entries:
                if entry.used and entry.node_id == item["node_id"] and entry.current_seq == item["gld_seq"]:
                    entry.sent_seq = entry.current_seq
            if item["kind"] == "AlarmPush":
                alarm_queue.remove(item["node_id"], item["gld_seq"])
        return item


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_plain(gas_class: int, confidence: int, battery_mv: int) -> bytes:
    assert 0 <= gas_class <= 6
    assert 0 <= confidence <= 100
    return bytes([gas_class, confidence]) + battery_mv.to_bytes(2, "big")


def build_aad(node_id: int, seq: int, flags: int, key_id: int) -> bytes:
    return node_id.to_bytes(2, "big") + bytes([seq, flags, key_id])


def make_record_flags(alarm: bool, external_power: bool) -> int:
    return (NC_FLAG_ALARM if alarm else 0) | (NC_FLAG_EXT_POWER if external_power else 0)


def gld_record_size(payload_len: int) -> int:
    return GLD_RECORD_HEADER_SIZE + payload_len


def max_records(mesh_payload_max: int, payload_len: int) -> int:
    return (mesh_payload_max - CLUSTER_DATA_RESPONSE_HEADER_SIZE) // gld_record_size(payload_len)


def encode_app_frame(type_flags: int, src_id: int, dst_id: int, seq: int, payload: bytes, max_payload: int = STAR_MAX_PAYLOAD) -> bytes:
    assert len(payload) <= max_payload
    header = bytes([APPFRAME_MAGIC, type_flags])
    header += src_id.to_bytes(2, "big")
    header += dst_id.to_bytes(2, "big")
    header += bytes([seq, len(payload)])
    crc = crc16_ccitt_false(header + payload)
    return header + payload + crc.to_bytes(2, "big")


def decode_app_frame(frame: bytes):
    assert len(frame) >= APPFRAME_OVERHEAD
    assert frame[0] == APPFRAME_MAGIC
    payload_len = frame[7]
    assert len(frame) == APPFRAME_OVERHEAD + payload_len
    assert payload_len <= STAR_MAX_PAYLOAD
    assert crc16_ccitt_false(frame[:-2]) == int.from_bytes(frame[-2:], "big")
    return {
        "type_flags": frame[1],
        "src_id": int.from_bytes(frame[2:4], "big"),
        "dst_id": int.from_bytes(frame[4:6], "big"),
        "seq": frame[6],
        "payload_len": payload_len,
        "payload": frame[8 : 8 + payload_len],
    }


def encrypted_payload_for(
    gas_class: int,
    confidence: int,
    battery_mv: int,
    node_id: int,
    seq: int,
    record_flags: int,
    key_id: int = 1,
    nonce: bytes = bytes.fromhex("101112131415161718191A1B"),
) -> bytes:
    key = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
    aad = build_aad(node_id, seq, record_flags, key_id)
    plaintext = encode_plain(gas_class, confidence, battery_mv)
    encrypted = AESGCM(key).encrypt(nonce, plaintext, aad)
    return bytes([key_id]) + nonce + encrypted[:16]


def build_gld_frame(gas_class: int, confidence: int, battery_mv: int, seq: int, external_power: bool):
    alarm = gas_class != GLD_GAS_CLEAR and confidence >= GLD_LEL_THRESHOLD_PERCENT
    record_flags = make_record_flags(alarm, external_power)
    type_flags = MSG_SENSOR_DATA
    if alarm:
        type_flags |= FLAG_ALARM_ACK
    if external_power:
        type_flags |= FLAG_GLD_EXT_POWER
    payload = encrypted_payload_for(gas_class, confidence, battery_mv, 0xF001, seq, record_flags)
    return alarm, record_flags, encode_app_frame(type_flags, 0xF001, 0x0001, seq, payload)


def parse_ch_gld_uplink(frame: bytes):
    decoded = decode_app_frame(frame)
    type_flags = decoded["type_flags"]
    allowed = {
        TYPE_GLD_NORMAL_BATTERY,
        TYPE_GLD_ALARM_BATTERY,
        TYPE_GLD_NORMAL_EXTERNAL,
        TYPE_GLD_ALARM_EXTERNAL,
    }
    assert type_flags & 0x3F == MSG_SENSOR_DATA
    assert type_flags in allowed
    assert decoded["payload_len"] == GLD_ENCRYPTED_PAYLOAD_SIZE
    return {
        "node_id": decoded["src_id"],
        "ch_id": decoded["dst_id"],
        "seq": decoded["seq"],
        "type_flags": type_flags,
        "alarm": bool(type_flags & FLAG_ALARM_ACK),
        "external_power": bool(type_flags & FLAG_GLD_EXT_POWER),
        "payload": decoded["payload"],
    }


def build_compact_alarm_ack(ch_id: int, node_id: int, seq: int) -> bytes:
    return encode_app_frame(TYPE_GLD_ALARM_BATTERY, ch_id, node_id, seq, b"")


def encode_gld_record(node_id: int, seq: int, flags: int, payload: bytes) -> bytes:
    assert len(payload) <= STAR_MAX_PAYLOAD
    return node_id.to_bytes(2, "big") + bytes([seq, flags, len(payload)]) + payload


def decode_gld_record(record: bytes):
    assert len(record) >= GLD_RECORD_HEADER_SIZE
    payload_len = record[4]
    assert len(record) == GLD_RECORD_HEADER_SIZE + payload_len
    return {
        "node_id": int.from_bytes(record[0:2], "big"),
        "seq": record[2],
        "flags": record[3],
        "payload_len": payload_len,
        "payload": record[5:],
    }


class CacheEntry:
    def __init__(self):
        self.used = False
        self.node_id = 0
        self.current_seq = 0
        self.sent_seq = 0
        self.flags = 0
        self.last_seen_ms = 0
        self.last_sent_ms = 0
        self.payload = b""

    @property
    def unsent(self):
        return self.used and self.current_seq != self.sent_seq

    @property
    def alarm(self):
        return self.used and bool(self.flags & NC_FLAG_ALARM)


def update_cache(entries, uplink, now_ms: int):
    flags = make_record_flags(uplink["alarm"], uplink["external_power"])
    assert flags & ~(NC_FLAG_ALARM | NC_FLAG_EXT_POWER) == 0
    assert len(uplink["payload"]) == GLD_ENCRYPTED_PAYLOAD_SIZE

    for index, entry in enumerate(entries):
        if entry.used and entry.node_id == uplink["node_id"]:
            if entry.current_seq == uplink["seq"]:
                entry.last_seen_ms = now_ms
                if entry.flags == flags and entry.payload == uplink["payload"]:
                    return "Duplicate", index, uplink["alarm"], False
                return "Conflict", index, False, False

            was_alarm = entry.alarm
            entry.current_seq = uplink["seq"]
            entry.flags = flags
            entry.last_seen_ms = now_ms
            entry.payload = uplink["payload"]
            return "Updated", index, uplink["alarm"], was_alarm and not uplink["alarm"]

    for index, entry in enumerate(entries):
        if not entry.used:
            entry.used = True
            entry.node_id = uplink["node_id"]
            entry.current_seq = uplink["seq"]
            entry.sent_seq = (uplink["seq"] - 1) & 0xFF
            entry.flags = flags
            entry.last_seen_ms = now_ms
            entry.payload = uplink["payload"]
            return "Inserted", index, uplink["alarm"], False

    return "CacheFull", None, False, False


def build_cluster_payload(request_id: int, ch_battery_mv: int, entries, now_ms=0, stale_after_ms=0):
    selected = []
    used = CLUSTER_DATA_RESPONSE_HEADER_SIZE
    payload = bytearray(b"\x00" * CLUSTER_DATA_RESPONSE_HEADER_SIZE)
    payload[0:2] = request_id.to_bytes(2, "big")
    payload[3:5] = ch_battery_mv.to_bytes(2, "big")

    while True:
        candidates = [
            (index, entry)
            for index, entry in enumerate(entries)
            if index not in selected
            and entry.used
            and entry.payload
            and entry.unsent
            and not entry.alarm
            and not (stale_after_ms and now_ms >= entry.last_seen_ms and now_ms - entry.last_seen_ms > stale_after_ms)
        ]
        if not candidates:
            break

        index, entry = sorted(candidates, key=lambda item: item[1].last_seen_ms)[0]
        record = encode_gld_record(entry.node_id, entry.current_seq, entry.flags, entry.payload)
        selected.append(index)
        if used + len(record) > MESH_MAX_PAYLOAD:
            continue
        payload += record
        used += len(record)

    record_count = 0
    offset = CLUSTER_DATA_RESPONSE_HEADER_SIZE
    while offset < len(payload):
        record_len = GLD_RECORD_HEADER_SIZE + payload[offset + 4]
        record_count += 1
        offset += record_len

    if record_count:
        data_status = DATA_OK
    else:
        valid = [entry for entry in entries if entry.used and entry.payload]
        non_stale = [
            entry
            for entry in valid
            if not (stale_after_ms and now_ms >= entry.last_seen_ms and now_ms - entry.last_seen_ms > stale_after_ms)
        ]
        data_status = DATA_NOT_AVAIL if not valid else DATA_STALE if not non_stale else DATA_EMPTY

    payload[2] = data_status
    payload[5] = record_count
    return bytes(payload), selected[:record_count]


def build_single_record_push_frame(ch_id: int, dst_id: int, mesh_seq: int, entry: CacheEntry):
    record = encode_gld_record(entry.node_id, entry.current_seq, entry.flags, entry.payload)
    type_flags = MSG_SENSOR_DATA | (FLAG_ALARM_ACK if entry.alarm else 0)
    return encode_app_frame(type_flags, ch_id, dst_id, mesh_seq, record)


def process_gld_frame(entries, alarm_queue, tx_queue, frame: bytes, now_ms: int, mesh_seq: int):
    uplink = parse_ch_gld_uplink(frame)
    status, index, should_ack, recovery = update_cache(entries, uplink, now_ms)
    if status not in {"Inserted", "Updated", "Duplicate"}:
        return {"status": status, "ack": None, "queued": False}

    entry = entries[index]
    ack = None
    queued = False
    if uplink["alarm"] and should_ack:
        alarm_status = alarm_queue.enqueue_if_absent(entry)
        if alarm_status == "Full":
            return {"status": "AlarmQueueFull", "ack": None, "queued": False}
        if alarm_status == "Conflict":
            return {"status": "AlarmQueueConflict", "ack": None, "queued": False}
        if alarm_status == "Queued":
            push = build_single_record_push_frame(0x0001, 0x0064, mesh_seq, entry)
            if tx_queue.enqueue("AlarmPush", push, entry.node_id, entry.current_seq) != "Ok":
                return {"status": "TxQueueFull", "ack": None, "queued": False}
            queued = True
        ack = build_compact_alarm_ack(0x0001, entry.node_id, entry.current_seq)

    if recovery:
        push = build_single_record_push_frame(0x0001, 0x0064, mesh_seq, entry)
        if tx_queue.enqueue("RecoveryClear", push, entry.node_id, entry.current_seq) != "Ok":
            return {"status": "TxQueueFull", "ack": ack, "queued": queued}
        queued = True

    return {"status": "Ok", "ack": ack, "queued": queued}


def test_type_flags():
    assert TYPE_GLD_NORMAL_BATTERY == 0x10
    assert TYPE_GLD_NORMAL_EXTERNAL == 0x90
    assert TYPE_GLD_ALARM_BATTERY == 0x50
    assert TYPE_GLD_ALARM_EXTERNAL == 0xD0
    assert TYPE_GLD_ALARM_EXTERNAL & 0x3F == MSG_SENSOR_DATA


def test_plain_payload_vector():
    assert encode_plain(GLD_GAS_LPG, 80, 3700).hex().upper() == "01500E74"


def test_alarm_boundary():
    assert not (GLD_GAS_CLEAR != GLD_GAS_CLEAR and 100 >= GLD_LEL_THRESHOLD_PERCENT)
    assert not (GLD_GAS_LPG != GLD_GAS_CLEAR and 29 >= GLD_LEL_THRESHOLD_PERCENT)
    assert GLD_GAS_LPG != GLD_GAS_CLEAR and 30 >= GLD_LEL_THRESHOLD_PERCENT


def test_aad_vector():
    aad = build_aad(0xF001, 0x2A, 0x11, 0x01)
    assert aad.hex().upper() == "F0012A1101"


def test_aes_gcm_vector():
    key = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
    nonce = bytes.fromhex("101112131415161718191A1B")
    aad = bytes.fromhex("F0012A1101")
    plaintext = bytes.fromhex("01500E74")

    encrypted = AESGCM(key).encrypt(nonce, plaintext, aad)
    ciphertext = encrypted[:4]
    tag = encrypted[4:16]
    payload = bytes([0x01]) + nonce + ciphertext + tag

    assert ciphertext.hex().upper() == "C57E0DDB"
    assert tag.hex().upper() == "F88ABEC591E9F5BFAD982A6C"
    assert payload.hex().upper() == "01101112131415161718191A1BC57E0DDBF88ABEC591E9F5BFAD982A6C"
    assert len(payload) == GLD_ENCRYPTED_PAYLOAD_SIZE


def test_record_capacity():
    assert gld_record_size(GLD_ENCRYPTED_PAYLOAD_SIZE) == 34
    assert max_records(MESH_MAX_PAYLOAD, GLD_ENCRYPTED_PAYLOAD_SIZE) == 2


def test_app_frame_crc_and_length():
    payload = bytes.fromhex("01101112131415161718191A1BC57E0DDBF88ABEC591E9F5BFAD982A6C")
    frame = encode_app_frame(TYPE_GLD_ALARM_BATTERY, 0xF001, 0x0064, 0x2A, payload)

    assert len(frame) == APPFRAME_OVERHEAD + GLD_ENCRYPTED_PAYLOAD_SIZE
    assert frame[0] == APPFRAME_MAGIC
    assert frame[1] == TYPE_GLD_ALARM_BATTERY
    assert frame[7] == GLD_ENCRYPTED_PAYLOAD_SIZE
    assert crc16_ccitt_false(frame[:-2]) == int.from_bytes(frame[-2:], "big")


def test_gld_frame_builder_semantics():
    normal_alarm, normal_record_flags, normal_frame = build_gld_frame(
        GLD_GAS_CLEAR, 100, 3700, 0x31, external_power=False
    )
    assert not normal_alarm
    assert normal_record_flags == 0
    normal = decode_app_frame(normal_frame)
    assert normal["type_flags"] == TYPE_GLD_NORMAL_BATTERY
    assert normal["payload_len"] == GLD_ENCRYPTED_PAYLOAD_SIZE

    low_alarm, low_record_flags, low_frame = build_gld_frame(
        GLD_GAS_METHANE, 29, 3700, 0x32, external_power=False
    )
    assert not low_alarm
    assert low_record_flags == 0
    assert decode_app_frame(low_frame)["type_flags"] == TYPE_GLD_NORMAL_BATTERY

    alarm, alarm_record_flags, alarm_frame = build_gld_frame(
        GLD_GAS_LPG, 30, 3700, 0x33, external_power=False
    )
    assert alarm
    assert alarm_record_flags == NC_FLAG_ALARM
    assert decode_app_frame(alarm_frame)["type_flags"] == TYPE_GLD_ALARM_BATTERY

    ext_alarm, ext_record_flags, ext_alarm_frame = build_gld_frame(
        GLD_GAS_LPG, 80, 3700, 0x34, external_power=True
    )
    assert ext_alarm
    assert ext_record_flags == NC_FLAG_ALARM | NC_FLAG_EXT_POWER
    assert decode_app_frame(ext_alarm_frame)["type_flags"] == TYPE_GLD_ALARM_EXTERNAL

    retry_frame = bytes(alarm_frame)
    assert retry_frame == alarm_frame


def test_ch_uplink_parser_and_ack_contract():
    alarm, _, alarm_frame = build_gld_frame(GLD_GAS_LPG, 30, 3700, 0x44, external_power=True)
    assert alarm

    parsed = parse_ch_gld_uplink(alarm_frame)
    assert parsed["node_id"] == 0xF001
    assert parsed["ch_id"] == 0x0001
    assert parsed["seq"] == 0x44
    assert parsed["type_flags"] == TYPE_GLD_ALARM_EXTERNAL
    assert parsed["alarm"]
    assert parsed["external_power"]
    assert len(parsed["payload"]) == GLD_ENCRYPTED_PAYLOAD_SIZE

    ack = build_compact_alarm_ack(0x0001, parsed["node_id"], parsed["seq"])
    decoded_ack = decode_app_frame(ack)
    assert decoded_ack["type_flags"] == TYPE_GLD_ALARM_BATTERY
    assert decoded_ack["src_id"] == 0x0001
    assert decoded_ack["dst_id"] == 0xF001
    assert decoded_ack["seq"] == 0x44
    assert decoded_ack["payload_len"] == 0


def test_ch_node_cache_update_duplicate_conflict_and_recovery():
    entries = [CacheEntry() for _ in range(3)]
    alarm, _, alarm_frame = build_gld_frame(GLD_GAS_LPG, 30, 3700, 0x60, external_power=True)
    assert alarm
    parsed_alarm = parse_ch_gld_uplink(alarm_frame)

    status, index, should_ack, recovery = update_cache(entries, parsed_alarm, now_ms=100)
    assert status == "Inserted"
    assert index == 0
    assert should_ack
    assert not recovery
    assert entries[0].node_id == 0xF001
    assert entries[0].current_seq == 0x60
    assert entries[0].sent_seq == 0x5F
    assert entries[0].flags == NC_FLAG_ALARM | NC_FLAG_EXT_POWER
    assert entries[0].payload == parsed_alarm["payload"]
    assert entries[0].unsent

    duplicate_status, duplicate_index, duplicate_ack, _ = update_cache(entries, parsed_alarm, now_ms=110)
    assert duplicate_status == "Duplicate"
    assert duplicate_index == 0
    assert duplicate_ack
    assert entries[0].current_seq == 0x60

    tampered = dict(parsed_alarm)
    tampered["payload"] = parsed_alarm["payload"][:-1] + bytes([parsed_alarm["payload"][-1] ^ 0x01])
    conflict_status, conflict_index, conflict_ack, _ = update_cache(entries, tampered, now_ms=120)
    assert conflict_status == "Conflict"
    assert conflict_index == 0
    assert not conflict_ack
    assert entries[0].payload == parsed_alarm["payload"]

    clear_alarm, _, clear_frame = build_gld_frame(GLD_GAS_CLEAR, 100, 3700, 0x61, external_power=True)
    assert not clear_alarm
    clear_status, _, clear_ack, clear_recovery = update_cache(entries, parse_ch_gld_uplink(clear_frame), now_ms=130)
    assert clear_status == "Updated"
    assert not clear_ack
    assert clear_recovery
    assert entries[0].flags == NC_FLAG_EXT_POWER
    assert entries[0].unsent


def test_cluster_data_response_packs_two_normal_records_max_and_marks_sent_later():
    entries = [CacheEntry() for _ in range(4)]
    for i, node_id in enumerate([0xF001, 0xF002, 0xF003]):
        payload = encrypted_payload_for(GLD_GAS_CLEAR, 100 - i, 3700 + i, node_id, 0x10 + i, 0)
        frame = encode_app_frame(TYPE_GLD_NORMAL_BATTERY, node_id, 0x0001, 0x10 + i, payload)
        parsed = parse_ch_gld_uplink(frame)
        status, _, _, _ = update_cache(entries, parsed, now_ms=300 + i)
        assert status == "Inserted"

    response, selected = build_cluster_payload(0x1234, 4100, entries)
    assert len(response) == CLUSTER_DATA_RESPONSE_HEADER_SIZE + 2 * gld_record_size(GLD_ENCRYPTED_PAYLOAD_SIZE)
    assert response[0:2].hex().upper() == "1234"
    assert response[2] == DATA_OK
    assert int.from_bytes(response[3:5], "big") == 4100
    assert response[5] == 2
    assert selected == [0, 1]

    first = decode_gld_record(response[6 : 6 + gld_record_size(GLD_ENCRYPTED_PAYLOAD_SIZE)])
    second_offset = 6 + gld_record_size(GLD_ENCRYPTED_PAYLOAD_SIZE)
    second = decode_gld_record(response[second_offset : second_offset + gld_record_size(GLD_ENCRYPTED_PAYLOAD_SIZE)])
    assert first["node_id"] == 0xF001
    assert second["node_id"] == 0xF002
    assert first["payload_len"] == GLD_ENCRYPTED_PAYLOAD_SIZE
    assert second["payload_len"] == GLD_ENCRYPTED_PAYLOAD_SIZE

    for selected_index in selected:
        entries[selected_index].sent_seq = entries[selected_index].current_seq
        entries[selected_index].last_sent_ms = 400

    response2, selected2 = build_cluster_payload(0x1235, 4100, entries)
    assert response2[5] == 1
    assert selected2 == [2]


def test_cluster_response_empty_and_stale_statuses():
    entries = [CacheEntry() for _ in range(2)]
    empty_payload, _ = build_cluster_payload(0x0001, 0xFFFF, entries)
    assert empty_payload[2] == DATA_NOT_AVAIL
    assert empty_payload[5] == 0

    payload = encrypted_payload_for(GLD_GAS_CLEAR, 100, 3700, 0xF001, 0x22, 0)
    frame = encode_app_frame(TYPE_GLD_NORMAL_BATTERY, 0xF001, 0x0001, 0x22, payload)
    update_cache(entries, parse_ch_gld_uplink(frame), now_ms=100)
    entries[0].sent_seq = entries[0].current_seq
    sent_payload, _ = build_cluster_payload(0x0002, 0xFFFF, entries, now_ms=120, stale_after_ms=100)
    assert sent_payload[2] == DATA_EMPTY

    stale_payload, _ = build_cluster_payload(0x0003, 0xFFFF, entries, now_ms=250, stale_after_ms=100)
    assert stale_payload[2] == DATA_STALE


def test_single_record_alarm_and_recovery_push_frames():
    alarm_entry = CacheEntry()
    alarm_payload = encrypted_payload_for(
        GLD_GAS_LPG,
        80,
        3700,
        0xF010,
        0x70,
        NC_FLAG_ALARM | NC_FLAG_EXT_POWER,
    )
    alarm_entry.used = True
    alarm_entry.node_id = 0xF010
    alarm_entry.current_seq = 0x70
    alarm_entry.sent_seq = 0x6F
    alarm_entry.flags = NC_FLAG_ALARM | NC_FLAG_EXT_POWER
    alarm_entry.payload = alarm_payload

    alarm_push = build_single_record_push_frame(0x0001, 0x0064, 0x01, alarm_entry)
    decoded_alarm_push = decode_app_frame(alarm_push)
    assert decoded_alarm_push["type_flags"] == TYPE_GLD_ALARM_BATTERY
    assert decoded_alarm_push["payload_len"] == gld_record_size(GLD_ENCRYPTED_PAYLOAD_SIZE)
    alarm_record = decode_gld_record(decoded_alarm_push["payload"])
    assert alarm_record["node_id"] == 0xF010
    assert alarm_record["flags"] == NC_FLAG_ALARM | NC_FLAG_EXT_POWER

    recovery_entry = CacheEntry()
    recovery_entry.used = True
    recovery_entry.node_id = 0xF010
    recovery_entry.current_seq = 0x71
    recovery_entry.sent_seq = 0x70
    recovery_entry.flags = NC_FLAG_EXT_POWER
    recovery_entry.payload = encrypted_payload_for(
        GLD_GAS_CLEAR, 100, 3700, 0xF010, 0x71, NC_FLAG_EXT_POWER
    )

    recovery_push = build_single_record_push_frame(0x0001, 0x0064, 0x02, recovery_entry)
    decoded_recovery_push = decode_app_frame(recovery_push)
    assert decoded_recovery_push["type_flags"] == MSG_SENSOR_DATA
    recovery_record = decode_gld_record(decoded_recovery_push["payload"])
    assert recovery_record["flags"] == NC_FLAG_EXT_POWER


def test_ch_runtime_alarm_queue_ack_and_tx_success_semantics():
    entries = [CacheEntry() for _ in range(2)]
    alarm_queue = AlarmQueue(capacity=2)
    tx_queue = TxQueue(capacity=2)

    alarm, _, alarm_frame = build_gld_frame(GLD_GAS_LPG, 80, 3700, 0x80, external_power=False)
    assert alarm
    result = process_gld_frame(entries, alarm_queue, tx_queue, alarm_frame, now_ms=1000, mesh_seq=0x01)
    assert result["status"] == "Ok"
    assert result["ack"] is not None
    assert result["queued"]
    assert len(alarm_queue.items) == 1
    assert len(tx_queue.items) == 1
    assert entries[0].unsent

    duplicate = process_gld_frame(entries, alarm_queue, tx_queue, alarm_frame, now_ms=1010, mesh_seq=0x02)
    assert duplicate["status"] == "Ok"
    assert duplicate["ack"] is not None
    assert not duplicate["queued"]
    assert len(alarm_queue.items) == 1
    assert len(tx_queue.items) == 1

    sent_item = tx_queue.pop_success(entries, alarm_queue)
    assert sent_item["kind"] == "AlarmPush"
    assert not entries[0].unsent
    assert alarm_queue.items == []


def test_ch_runtime_alarm_queue_full_blocks_ack():
    entries = [CacheEntry() for _ in range(2)]
    alarm_queue = AlarmQueue(capacity=1)
    tx_queue = TxQueue(capacity=2)

    first_payload = encrypted_payload_for(GLD_GAS_LPG, 80, 3700, 0xF001, 0x01, NC_FLAG_ALARM)
    first_frame = encode_app_frame(TYPE_GLD_ALARM_BATTERY, 0xF001, 0x0001, 0x01, first_payload)
    assert process_gld_frame(entries, alarm_queue, tx_queue, first_frame, 100, 0x01)["ack"] is not None

    second_payload = encrypted_payload_for(GLD_GAS_LPG, 80, 3700, 0xF002, 0x02, NC_FLAG_ALARM)
    second_frame = encode_app_frame(TYPE_GLD_ALARM_BATTERY, 0xF002, 0x0001, 0x02, second_payload)
    blocked = process_gld_frame(entries, alarm_queue, tx_queue, second_frame, 110, 0x02)
    assert blocked["status"] == "AlarmQueueFull"
    assert blocked["ack"] is None
    assert len(alarm_queue.items) == 1


def test_ch_runtime_cluster_response_tx_success_marks_only_selected_sent():
    entries = [CacheEntry() for _ in range(3)]
    tx_queue = TxQueue(capacity=2)
    alarm_queue = AlarmQueue(capacity=2)
    for i, node_id in enumerate([0xF001, 0xF002, 0xF003]):
        payload = encrypted_payload_for(GLD_GAS_CLEAR, 100, 3700, node_id, 0x20 + i, 0)
        frame = encode_app_frame(TYPE_GLD_NORMAL_BATTERY, node_id, 0x0001, 0x20 + i, payload)
        update_cache(entries, parse_ch_gld_uplink(frame), now_ms=200 + i)

    response, selected = build_cluster_payload(0x7788, 0xFFFF, entries)
    selected_with_seq = [(index, entries[index].current_seq) for index in selected]
    assert tx_queue.enqueue(
        "ClusterDataResponse",
        encode_app_frame(MSG_CLUSTER_DATA_RESPONSE, 1, 100, 9, response, max_payload=MESH_MAX_PAYLOAD),
        selected=selected_with_seq,
    ) == "Ok"
    assert selected == [0, 1]
    assert all(entry.unsent for entry in entries)

    tx_queue.pop_success(entries, alarm_queue)
    assert not entries[0].unsent
    assert not entries[1].unsent
    assert entries[2].unsent


def test_ch_response_tx_success_does_not_mark_changed_cache_seq():
    entries = [CacheEntry() for _ in range(2)]
    tx_queue = TxQueue(capacity=2)
    alarm_queue = AlarmQueue(capacity=2)

    payload = encrypted_payload_for(GLD_GAS_CLEAR, 100, 3700, 0xF001, 0x30, 0)
    frame = encode_app_frame(TYPE_GLD_NORMAL_BATTERY, 0xF001, 0x0001, 0x30, payload)
    update_cache(entries, parse_ch_gld_uplink(frame), now_ms=1)
    response, selected = build_cluster_payload(0x9999, 0xFFFF, entries)
    selected_with_seq = [(index, entries[index].current_seq) for index in selected]
    assert tx_queue.enqueue(
        "ClusterDataResponse",
        encode_app_frame(MSG_CLUSTER_DATA_RESPONSE, 1, 100, 9, response, max_payload=MESH_MAX_PAYLOAD),
        selected=selected_with_seq,
    ) == "Ok"

    newer_payload = encrypted_payload_for(GLD_GAS_CLEAR, 100, 3700, 0xF001, 0x31, 0)
    newer_frame = encode_app_frame(TYPE_GLD_NORMAL_BATTERY, 0xF001, 0x0001, 0x31, newer_payload)
    update_cache(entries, parse_ch_gld_uplink(newer_frame), now_ms=2)
    tx_queue.pop_success(entries, alarm_queue)
    assert entries[0].current_seq == 0x31
    assert entries[0].sent_seq != entries[0].current_seq


def test_server_pull_request_contract_and_parser_scaffold_present():
    request_payload = (0x4455).to_bytes(2, "big") + (0x0064).to_bytes(2, "big")
    frame = encode_app_frame(MSG_SERVER_PULL_REQUEST, 0x006F, 0x0064, 0x77, request_payload)
    decoded = decode_app_frame(frame)
    assert decoded["type_flags"] == MSG_SERVER_PULL_REQUEST
    assert decoded["src_id"] == 0x006F
    assert decoded["dst_id"] == 0x0064
    assert decoded["seq"] == 0x77
    assert decoded["payload_len"] == 4
    assert int.from_bytes(decoded["payload"][0:2], "big") == 0x4455
    assert int.from_bytes(decoded["payload"][2:4], "big") == 0x0064
    assert (decoded["payload_len"] - 2) % 2 == 0

    pull_header = pathlib.Path("firmware/ch/include/ChPullRequest.h").read_text(encoding="utf-8")
    pull_src = pathlib.Path("firmware/ch/src/ChPullRequest.cpp").read_text(encoding="utf-8")
    runtime_header = pathlib.Path("firmware/ch/include/ChRuntime.h").read_text(encoding="utf-8")
    assert "parseServerPullRequestFrame" in pull_header
    assert "WrongHop" in pull_src
    assert "UnsupportedHopCount" in pull_header
    assert "decoded.dstId != localChId" in pull_src
    assert "localIsFinalHop" in pull_src
    assert "handleServerPullRequestFrame" in runtime_header
    runtime_src = pathlib.Path("firmware/ch/src/ChStarMeshRuntimeMain.cpp").read_text(encoding="utf-8")
    tx_header = pathlib.Path("firmware/ch/include/ChTxQueue.h").read_text(encoding="utf-8")
    tx_src = pathlib.Path("firmware/ch/src/ChTxQueue.cpp").read_text(encoding="utf-8")
    assert "CH_PULL_RELAY" in runtime_src
    assert "CH_UPLINK_RELAY" in runtime_src
    assert "RelayFrame" in tx_header
    assert "item.kind == ChTxKind::RelayFrame" in tx_src


def test_gateway_and_nodered_pull_use_hoplist_contract():
    gateway_src = pathlib.Path("firmware/gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
    flow_src = pathlib.Path("server/nodered/apply-pertamina-gld-flow.js").read_text(encoding="utf-8")
    flow_json = pathlib.Path("server/nodered/pertamina-gld-server.flow.json").read_text(encoding="utf-8")
    ch_gw_doc = pathlib.Path("docs/design/ch-gw/design.md").read_text(encoding="utf-8")
    gw_doc = pathlib.Path("docs/design/gw/design.md").read_text(encoding="utf-8")

    assert "parseHopList" in gateway_src
    assert 'doc["hopList"]' in gateway_src
    assert "payloadLen = 2 + (hopCount * 2)" in gateway_src
    assert "writeU16Be(&payload[2 + (i * 2)], hopList[i]);" in gateway_src

    build_pull_block = flow_src.split('nodeBase("function", "build_pull"', 1)[1].split('nodeBase("mqtt in", "mqtt_cmd_node"', 1)[0]
    assert "const hopList = Array.isArray(p.hopList)" in flow_src
    assert "nodeIdParam" not in build_pull_block
    assert "Inject SERVER_PULL_REQUEST hopList" in flow_json
    assert '"payload": "{\\"requestId\\":1,\\"hopList\\":[\\"0x0064\\",\\"0x0065\\",\\"0x0066\\"]}"' in flow_json
    assert "normalize pull hopList" in flow_json
    assert "Inject request CH 0x0064 GLD 0xF001" not in flow_json

    assert "| payload | `requestId:uint16BE + hopList:uint16BE[]` |" in ch_gw_doc
    assert "requestId:uint16BE + hopList:uint16BE[]" in gw_doc


def test_server_site_and_dataset_flows_follow_current_firmware_contract():
    decode_src = pathlib.Path("server/nodered/functions/pertamina-gld-decode.js").read_text(encoding="utf-8")
    server_flow = pathlib.Path("server/nodered/pertamina-gld-server.flow.json").read_text(encoding="utf-8-sig")
    server_wrapper = pathlib.Path("server/nodered/apply-pertamina-gld-flow.ps1").read_text(encoding="utf-8-sig")
    dataset_flow = pathlib.Path("server/nodered/pertamina-gld-dataset.flow.json").read_text(encoding="utf-8-sig")
    dataset_generator = pathlib.Path("server/nodered/apply-pertamina-gld-dataset-flow.ps1").read_text(encoding="utf-8-sig")
    dataset_wrapper = pathlib.Path("server/nodered/deploy-dataset-flow.py").read_text(encoding="utf-8")
    dataset_recorder = pathlib.Path("server/nodered/gld_dataset_recorder.py").read_text(encoding="utf-8")
    gateway_src = pathlib.Path("firmware/gateway/src/GatewayMqttMeshMain.cpp").read_text(encoding="utf-8")
    ch_runtime = pathlib.Path("firmware/ch/src/ChStarMeshRuntimeMain.cpp").read_text(encoding="utf-8")
    server_doc = pathlib.Path("docs/design/server/design.md").read_text(encoding="utf-8")
    gw_server_doc = pathlib.Path("docs/design/gw-server/design.md").read_text(encoding="utf-8")

    server_nodes = json.loads(server_flow)
    dataset_nodes = json.loads(dataset_flow)
    server_decode_func = next(
        node["func"] for node in server_nodes
        if node.get("type") == "function" and node.get("name") == "decode Gateway/GLD contract"
    )

    for gas_line in ('2: "methane"', '3: "propane"', '4: "butane"'):
        assert gas_line in decode_src
        assert gas_line in server_decode_func
    for stale_name in ("propana", "butana", "metana"):
        assert stale_name not in decode_src
        assert stale_name not in server_decode_func
        assert stale_name not in server_doc

    assert "Inject GLD SET_MODE dataset" in server_flow
    assert '\\"hex\\":\\"0101\\"' in server_flow
    assert "Inject GLD command placeholder" not in server_flow
    assert '\\"hex\\":\\"0102\\"' not in server_flow
    assert "apply-pertamina-gld-flow.js" in server_wrapper
    assert "ConvertTo-Json -Depth 30" not in server_wrapper

    for text in (dataset_flow, dataset_generator, dataset_recorder):
        for required in ("sensor_voltage", "sensor_gain", "device_id", "node_id", "timestamp_ms", "nulling_profile_id"):
            assert required in text
        for stale_schema in ("p.ch", "p.nodeId", "p.ts_ms", "p.profileId", "ok0", "ok1", "ts_ms"):
            assert stale_schema not in text
    dataset_names = {node.get("name") for node in dataset_nodes}
    dataset_topics = {node.get("topic") for node in dataset_nodes if node.get("topic")}
    start_node = next(node for node in dataset_nodes if node.get("name") == "START_DATASET clear_air_test")
    stop_node = next(node for node in dataset_nodes if node.get("name") == "STOP_DATASET")
    assert "dataset command" in dataset_names
    assert "cmd/ack" in dataset_names
    assert "gas-leak-detector/F001/dataset" in dataset_topics
    assert "gas-leak-detector/+/cmd/ack" in dataset_topics
    assert start_node["payloadType"] == "json"
    assert '"cmd":"START_DATASET"' in start_node["payload"]
    assert '"use_fan_intake":false' in start_node["payload"]
    assert start_node["wires"] == [["pgld_ds_mqtt_dataset_cmd_out"]]
    assert stop_node["payloadType"] == "json"
    assert stop_node["payload"] == '{"cmd":"STOP_DATASET"}'
    assert stop_node["wires"] == [["pgld_ds_mqtt_dataset_cmd_out"]]
    for node in dataset_nodes:
        if "wires" in node and node["wires"]:
            assert all(isinstance(output_wires, list) for output_wires in node["wires"]), node.get("name")
    assert "gas-leak-detector/+/dataset/summary" in dataset_flow
    assert "apply-pertamina-gld-dataset-flow.ps1" in dataset_wrapper
    assert "PARSE_FN" not in dataset_wrapper
    assert "START_DATASET clear_air_test" in server_doc
    assert "gas-leak-detector/+/cmd/ack" in server_doc
    assert "The dataset flow expects the current GLD unified JSON field names" in server_doc

    assert "writeU16Be(&payload[4], ttlSec);" in gateway_src
    assert "payload[6] = static_cast<uint8_t>(commandLen);" in gateway_src
    assert "memcpy(&payload[7], commandBytes, commandLen);" in gateway_src
    assert "const uint16_t ttlSec       = (static_cast<uint16_t>(decoded.payload[4]) << 8) | decoded.payload[5];" in ch_runtime
    assert "const uint8_t  commandLen   = decoded.payload[6];" in ch_runtime
    assert "memcpy(dl->payload, decoded.payload + 7, commandLen);" in ch_runtime
    assert "dl->ttlMs        = ttlSec > 0 ? static_cast<uint32_t>(ttlSec) * 1000UL : PENDING_TTL_MS;" in ch_runtime
    assert "Gateway encodes and CH parses the same wire payload" in gw_server_doc
    assert "CH current parser does not consume TTL" not in gw_server_doc


def test_gld_unified_runtime_scaffolds_present():
    platformio = pathlib.Path("firmware/platformio.ini").read_text(encoding="utf-8")
    command_header = pathlib.Path("firmware/gld/include/GldCommandParser.h").read_text(encoding="utf-8")
    command_src = pathlib.Path("firmware/gld/src/GldCommandParser.cpp").read_text(encoding="utf-8")
    mode_header = pathlib.Path("firmware/gld/include/GldModeManager.h").read_text(encoding="utf-8")
    mode_src = pathlib.Path("firmware/gld/src/GldModeManager.cpp").read_text(encoding="utf-8")
    nulling_header = pathlib.Path("firmware/gld/include/GldNullingService.h").read_text(encoding="utf-8")
    unified_src = pathlib.Path("firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
    radio_header = pathlib.Path("firmware/shared/include/RadioTransport.h").read_text(encoding="utf-8")
    config_header = pathlib.Path("firmware/shared/include/FirmwareConfig.h").read_text(encoding="utf-8")

    assert "[env:gld]" in platformio
    assert "[env:gldw]" not in platformio
    assert "board = esp32-s3-devkitc-1" in platformio
    assert "-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1" in platformio
    assert "gld_unified_esp32s3" not in platformio
    assert "gld_unified_wroom_u1_n16r8_esp32s3" not in platformio
    assert "gld_unified_to_ch2_1_esp32s3" not in platformio
    assert "gld_inference_esp32s3" not in platformio
    assert "gld_dataset_esp32s3" not in platformio
    assert "gld_nulling_runtime_esp32s3" not in platformio
    assert "[env:ch1]" in platformio
    assert "[env:ch2]" in platformio
    assert "[env:ch3]" in platformio
    assert "[env:gw]" in platformio
    assert "ch_star_mesh_runtime_esp32s3" not in platformio
    assert "ch_layer1_1_esp32s3" not in platformio
    assert "ch_layer1_2_esp32s3" not in platformio
    assert "ch_layer2_1_esp32s3" not in platformio
    assert "gateway_mqtt_mesh_esp32s3" not in platformio
    assert "parseSerialCommand" in command_header
    assert "DEBUG_ON" in command_src
    assert "DEBUG_OFF" in command_src
    assert "APP_PING" in command_src
    assert "GET_INFO" in command_src
    assert "GET_STATUS" in command_src
    assert "GldSerialCommandType::AppPing" in command_src
    assert "GldSerialCommandType::GetInfo" in command_src
    assert "GldSerialCommandType::GetStatus" in command_src
    assert "GLD_INFO_JSON" in unified_src
    assert "GLD_STATUS_JSON" in unified_src
    assert "GLD_CMD_ACK_JSON" in unified_src
    assert "disableNetworkForOfflineMode(\"inference_mode\")" in unified_src
    assert "disableNetworkForOfflineMode(\"nulling_mode\")" in unified_src
    assert "WiFi.mode(WIFI_OFF)" in unified_src
    assert "emitCommandAck(\"SET_MODE\", \"ok\", \"mode switch accepted\", true)" in unified_src
    assert "doc[\"targetChId\"] = static_cast<uint16_t>(GLD_CH_ID)" in unified_src
    assert "bootHealth" in unified_src
    assert "sensorVoltage" in unified_src
    assert "sensorGain" in unified_src
    assert "featureOrder" in unified_src
    assert "latestTelemetryValid = true" in unified_src
    assert "lastLoraTxState = txState" in unified_src
    assert "MSG_NODE_DOWNLINK" in command_src
    assert "gldModeFromString" in mode_header
    assert 'strcmp(str, "running")' in mode_src
    assert "runNullingService" in nulling_header
    assert "saveCompleteNullingProfile" in unified_src
    assert "NULLING_RUNTIME_RESULT=PARTIAL_RETRY" in unified_src
    assert "NULLING_AUTO_MODE_SWITCH target=running mode=inference" in unified_src
    assert "RadioTransport" in radio_header
    assert "RadioTxPacket" in radio_header
    assert "AesKeyConfig" in config_header

    alarm, _, alarm_frame = build_gld_frame(GLD_GAS_LPG, 30, 3700, 0x90, external_power=False)
    assert alarm
    retry_snapshot = bytes(alarm_frame)
    assert retry_snapshot == alarm_frame
    assert decode_app_frame(retry_snapshot)["seq"] == 0x90


def test_gld_protocol_reference_matches_active_firmware():
    protocol_header = pathlib.Path("firmware/shared/include/ProtocolConstants.h").read_text(encoding="utf-8")
    unified_src = pathlib.Path("firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
    protocol_ref = pathlib.Path("Pertamina_GLD_Protocol_Reference.md").read_text(encoding="utf-8")
    final_design = pathlib.Path("docs/design/gld/final_design.md").read_text(encoding="utf-8")
    payload_contract = pathlib.Path("docs/design/gld-ch/payload-contract.draft.md").read_text(encoding="utf-8")

    assert "GLD_GAS_METHANE = 2" in protocol_header
    assert "GLD_GAS_PROPANE = 3" in protocol_header
    assert "GLD_GAS_BUTANE = 4" in protocol_header
    assert "| 2 | 2 | methane |" in final_design
    assert "| 3 | 3 | propane |" in final_design
    assert "| 4 | 4 | butane |" in final_design
    assert "| 2 | methane |" in payload_contract
    assert "| 3 | propane |" in payload_contract
    assert "| 4 | butane |" in payload_contract

    assert "GLD_LEL_THRESHOLD_PERCENT = 30" in protocol_header
    assert "confidence >= 30" in final_design
    assert "confidence >= 40" not in protocol_ref
    assert "confidence ≥ 40" not in protocol_ref

    assert "ACTIVE_LOW_OUTPUT_ON = LOW" in unified_src
    assert "ACTIVE_LOW_OUTPUT_OFF = HIGH" in unified_src
    assert "PIN_ALARM_LAMP, alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF" in unified_src
    assert "PIN_BUZZER,     alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF" in unified_src
    assert "PIN_STATUS_LED, alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF" in unified_src
    assert "Alarm lamp, buzzer, and status LED are active-low" in final_design


def test_current_design_docs_mirror_live_source_contracts():
    current_mirror_docs = [
        pathlib.Path("docs/design/README.md"),
        pathlib.Path("docs/design/gld/final_design.md"),
        pathlib.Path("docs/design/gld/design.current-firmware.draft.md"),
        pathlib.Path("docs/design/ch/final_design.md"),
        pathlib.Path("docs/design/gld-ch/payload-contract.draft.md"),
        pathlib.Path("docs/design/ch-ch/design.md"),
        pathlib.Path("docs/design/ch-ch/final_design.md"),
        pathlib.Path("docs/design/ch-gw/design.md"),
        pathlib.Path("docs/design/ch-gw/final_design.md"),
        pathlib.Path("docs/design/gw/design.md"),
        pathlib.Path("docs/design/gw/final_design.md"),
        pathlib.Path("docs/design/gw-server/design.md"),
        pathlib.Path("docs/design/gw-server/final_design.md"),
        pathlib.Path("docs/design/server/design.md"),
        pathlib.Path("docs/design/server/final_design.md"),
    ]
    for path in current_mirror_docs:
        text = path.read_text(encoding="utf-8")
        assert "Status: current source mirror, 2026-06-29." in text, path
        assert "2026-06-26" not in text, path

    firmware_readme = pathlib.Path("firmware/README.md").read_text(encoding="utf-8")
    assert "Status: current source map, 2026-06-29." in firmware_readme

    for name in ("ch-ch", "ch-gw", "gw", "gw-server", "server"):
        design = pathlib.Path(f"docs/design/{name}/design.md").read_text(encoding="utf-8")
        final = pathlib.Path(f"docs/design/{name}/final_design.md").read_text(encoding="utf-8")
        assert design == final, name

    gld_doc = pathlib.Path("docs/design/gld/final_design.md").read_text(encoding="utf-8")
    gld_current_draft = pathlib.Path("docs/design/gld/design.current-firmware.draft.md").read_text(encoding="utf-8")
    ch_doc = pathlib.Path("docs/design/ch/final_design.md").read_text(encoding="utf-8")
    payload_doc = pathlib.Path("docs/design/gld-ch/payload-contract.draft.md").read_text(encoding="utf-8")
    ch_ch_doc = pathlib.Path("docs/design/ch-ch/design.md").read_text(encoding="utf-8")
    ch_gw_doc = pathlib.Path("docs/design/ch-gw/design.md").read_text(encoding="utf-8")
    gw_doc = pathlib.Path("docs/design/gw/design.md").read_text(encoding="utf-8")
    gw_server_doc = pathlib.Path("docs/design/gw-server/design.md").read_text(encoding="utf-8")
    server_doc = pathlib.Path("docs/design/server/design.md").read_text(encoding="utf-8")
    command_header = pathlib.Path("firmware/gld/include/GldCommandParser.h").read_text(encoding="utf-8")

    assert "GLD_FIRMWARE_VERSION = \"0.8.12\"" in pathlib.Path("firmware/shared/include/FirmwareVersion.h").read_text(encoding="utf-8")
    assert "| firmware version | `0.8.12` |" in gld_doc
    assert "| firmware version | `0.7.1` |" in ch_doc
    assert "| firmware version | `0.1.3` |" in gw_doc

    assert "`gld`" in gld_doc
    assert "`gldw`" not in gld_doc
    assert "GLDW / ESP32-S3-WROOM-1U-N16R8" in gld_doc
    assert "`ch1`" in ch_doc
    assert "`ch2`" in ch_doc
    assert "`ch3`" in ch_doc
    assert "`gw`" in gw_doc
    old_env_names = (
        "gld_unified_esp32s3",
        "gld_unified_wroom_u1_n16r8_esp32s3",
        "ch_star_mesh_runtime_esp32s3",
        "ch_layer1_1_esp32s3",
        "ch_layer1_2_esp32s3",
        "ch_layer2_1_esp32s3",
        "gateway_mqtt_mesh_esp32s3",
    )
    for text in (firmware_readme, gld_doc, gld_current_draft, ch_doc, gw_doc):
        for old_env_name in old_env_names:
            assert old_env_name not in text
    assert "final_design.md" not in gld_current_draft
    assert "`docs/design/gld/design.md` dan firmware GLD saat ini" in gld_current_draft

    assert "MSG_GLD_DOWNLINK_CMD" not in command_header
    for text in (gld_doc, payload_doc):
        assert "MSG_NODE_DOWNLINK" in text
        assert "MSG_GLD_DOWNLINK_CMD" not in text

    assert "| Frequency | 920.0 MHz |" in gld_doc
    assert "| MESH | 921.0 MHz | 125 kHz | 9 | 4/5 | `0x34` | 17 dBm | 8 | 2 MHz |" in ch_doc
    assert "| Frequency | 921.0 MHz |" in gw_doc

    assert "confirm count | 10" in gld_doc
    assert "minimum final voltage | `0.0 V`" in gld_doc
    assert "inference`/`running` and `nulling` call the offline-mode guard" in gld_doc
    assert "`gas-leak-detector/F001/dataset/data`" in gld_doc
    assert "`sensor_voltage`" in gld_doc
    assert "`sensor_gain`" in gld_doc
    assert "`feature_order`" in gld_doc

    assert "requestId:uint16BE + hopList:uint16BE[]" in ch_ch_doc
    assert "| payload | `requestId:uint16BE + hopList:uint16BE[]` |" in ch_gw_doc
    assert "nodeId(2) + commandId(2) + ttlSec(2) + commandLen(1) + commandBytes" in ch_gw_doc
    assert "nodeId(2) + commandId(2) + commandLen(1) + commandBytes" not in ch_gw_doc
    assert "Gateway encodes and CH parses the same wire payload" in gw_server_doc
    assert "Gateway wire payload includes TTL. CH current parser does not consume TTL." not in gw_server_doc

    assert "`gld/gateway/cmd/pull`" in gw_doc
    assert "`gld/gateway/cmd/node`" in gw_doc
    assert "`gld/gateway/topology`" in server_doc
    assert "`PGL_TOPOLOGY_PARENT_TTL_MS` | 900000" in server_doc
    assert "The dataset flow expects the current GLD unified JSON field names `sensor_voltage`, `sensor_gain`, `feature_order`, `device_id`, `node_id`, `timestamp_ms`, `label`, and `nulling_profile_id`." in server_doc


def test_ch_rejects_invalid_gld_uplink_semantics():
    payload = bytes(GLD_ENCRYPTED_PAYLOAD_SIZE)
    not_sensor = encode_app_frame(MSG_CLUSTER_DATA_RESPONSE, 0xF001, 0x0001, 0x01, payload)
    assert decode_app_frame(not_sensor)["type_flags"] & 0x3F != MSG_SENSOR_DATA

    invalid_flags = encode_app_frame(MSG_SENSOR_DATA | 0x20, 0xF001, 0x0001, 0x01, payload)
    assert decode_app_frame(invalid_flags)["type_flags"] not in {
        TYPE_GLD_NORMAL_BATTERY,
        TYPE_GLD_ALARM_BATTERY,
        TYPE_GLD_NORMAL_EXTERNAL,
        TYPE_GLD_ALARM_EXTERNAL,
    }


def test_cpp_guard_scaffolds_are_present():
    builder_header = pathlib.Path("firmware/gld/include/GldFrameBuilder.h").read_text(encoding="utf-8")
    builder_src = pathlib.Path("firmware/gld/src/GldFrameBuilder.cpp").read_text(encoding="utf-8")
    ch_header = pathlib.Path("firmware/ch/include/ChUplink.h").read_text(encoding="utf-8")
    ch_src = pathlib.Path("firmware/ch/src/ChUplink.cpp").read_text(encoding="utf-8")
    cache_header = pathlib.Path("firmware/ch/include/NodeCache.h").read_text(encoding="utf-8")
    response_src = pathlib.Path("firmware/ch/src/ClusterResponse.cpp").read_text(encoding="utf-8")
    alarm_queue_header = pathlib.Path("firmware/ch/include/AlarmQueue.h").read_text(encoding="utf-8")
    tx_queue_header = pathlib.Path("firmware/ch/include/ChTxQueue.h").read_text(encoding="utf-8")
    runtime_src = pathlib.Path("firmware/ch/src/ChRuntime.cpp").read_text(encoding="utf-8")

    assert "InvalidInput" in builder_header
    assert "clearBuiltFrame(out)" in builder_src
    assert "isValidInput(input)" in builder_src
    assert "buildCompactAlarmAck" in ch_header
    assert "TYPE_ALARM_ACK_COMPACT" in ch_src
    assert "currentSeq" in cache_header
    assert "sentSeq" in cache_header
    assert "buildClusterDataResponsePayload" in response_src
    assert "buildSingleRecordSensorPushFrame" in response_src
    assert "enqueueAlarmIfAbsent" in alarm_queue_header
    assert "markChTxItemSentInCache" in tx_queue_header
    assert "processGldStarFrame" in runtime_src
    assert "handleServerPullRequestFrame" in runtime_src
    assert "AlarmQueueFull" in runtime_src


def test_invalid_payload_len_rejected_by_contract():
    assert GLD_ENCRYPTED_PAYLOAD_SIZE <= STAR_MAX_PAYLOAD
    assert 65 > STAR_MAX_PAYLOAD


def test_version_constants_format():
    header = pathlib.Path("firmware/shared/include/FirmwareVersion.h").read_text(encoding="utf-8")
    versions = re.findall(r'VERSION\s*=\s*"([^"]+)"', header)

    assert versions
    for version in versions:
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), version

    assert 'GLD_FIRMWARE_VERSION = "0.8.12"' in header
    assert 'CH_FIRMWARE_VERSION = "0.7.1"' in header
    assert 'GATEWAY_FIRMWARE_VERSION = "0.1.3"' in header
    assert 'PROTOCOL_VERSION = "0.1.0"' in header
    assert 'CONFIG_SCHEMA_VERSION = "0.1.0"' in header


def test_gld_operator_firmware_package_generator_present():
    script = pathlib.Path("firmware/tools/package_firmware_release.py").read_text(encoding="utf-8")
    assert "does" in script and "not compile firmware" in script
    assert "bootloader.bin" in script
    assert "partitions.bin" in script
    assert "boot_app0.bin" in script
    assert "firmware.bin" in script
    assert '"packageType": "pertamina-gld-prebuilt-firmware"' in script
    assert '"deviceId": args.device_id' in script
    assert '"boardProfile": args.board_profile' in script
    assert '"flashFiles": flash_files' in script
    assert "sha256(target)" in script
    assert "GLD_FIRMWARE_VERSION" in script


def test_gld_sensor_selftest_scaffold_present():
    platformio = pathlib.Path("firmware/bench/platformio.ini").read_text(encoding="utf-8")
    board_pins = pathlib.Path("firmware/gld/include/BoardPins.h").read_text(encoding="utf-8")
    sensor_main = pathlib.Path("firmware/gld/src/GldSensorSelfTestMain.cpp").read_text(encoding="utf-8")
    ads_reader = pathlib.Path("firmware/gld/src/GldAds1256Reader.cpp").read_text(encoding="utf-8")
    moving_average = pathlib.Path("firmware/gld/src/GldMovingAverage.cpp").read_text(encoding="utf-8")
    power = pathlib.Path("firmware/gld/src/GldPower.cpp").read_text(encoding="utf-8")

    assert "[env:gld_sensor_selftest_esp32s3]" in platformio
    assert "#define PGL_GLD_PIN_SPI_SCK 12" in board_pins
    assert "constexpr int PIN_SPI_SCK = PGL_GLD_PIN_SPI_SCK" in board_pins
    assert "#define PGL_GLD_PIN_ADS1256_CS 47" in board_pins
    assert "constexpr int PIN_ADS1256_CS = PGL_GLD_PIN_ADS1256_CS" in board_pins
    assert "#define PGL_GLD_PIN_BATTERY_VOLTAGE 4" in board_pins
    assert "constexpr int PIN_BATTERY_VOLTAGE = PGL_GLD_PIN_BATTERY_VOLTAGE" in board_pins
    assert '"MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"' in board_pins
    assert "SENSOR_SELFTEST_RESULT=" in sensor_main
    assert "SENSOR_SELFTEST_MIN_SCANS = 5" in sensor_main
    assert "SENSOR_SELFTEST_MAX_SCANS = 12" in sensor_main
    assert "SENSOR_SELFTEST_PASS_SCAN" in sensor_main
    assert "SENSOR_SELFTEST_FAIL_SCAN" in sensor_main
    assert "scanCount == 1" not in sensor_main
    assert "POWER_SELFTEST_RESULT=PASS" in sensor_main
    assert "externalPower=%u" in sensor_main
    assert "pg24=%u" in sensor_main
    assert "powerMode=%s" in sensor_main
    assert "LORA_SELFTEST_RESULT=PASS" in sensor_main
    assert "LORA_SELFTEST_RESULT=FAIL" in sensor_main
    assert "LORA_BEGIN_TCXO16_STATE" in sensor_main
    assert "LORA_BEGIN_XTAL_STATE" in sensor_main
    assert "LORA_BEGIN_STATE" in sensor_main
    assert "LORA_STANDBY_STATE" in sensor_main
    assert "#include <RadioLib.h>" in sensor_main
    assert "new Module" in sensor_main
    assert "new SX1262" in sensor_main
    assert "loraRadio->begin" in sensor_main
    assert "loraRadio->standby" in sensor_main
    assert "transmit(" not in sensor_main
    assert "SENSOR_DATA" not in sensor_main
    assert "MSG_SENSOR_DATA" not in sensor_main
    assert "PIN_LORA_TXEN" in sensor_main
    assert "PIN_ALARM_LAMP" in sensor_main
    assert "PIN_BUZZER" in sensor_main
    assert "ADS_BEGIN_RESULT=" in sensor_main
    assert "ADS_DRDY_BEFORE_BEGIN" in sensor_main
    assert "ADS_DRDY_AFTER_BEGIN" in sensor_main
    assert "ADS_MUX_REG" in sensor_main
    assert "ADS_DRATE_REG" in sensor_main
    assert "status=%s" in sensor_main
    assert "gldAds1256StatusName" in sensor_main
    assert not pathlib.Path("firmware/gld/src/Ads1256Probe.cpp").exists()
    assert not pathlib.Path("firmware/gld/include/Ads1256Probe.h").exists()
    assert "muxSingleEnded" in ads_reader
    assert "#include <ADS1256.h>" in ads_reader
    assert "new ADS1256" in ads_reader
    assert "InitializeADC()" in ads_reader
    assert "ads_->setPGA(PGA_64)" in ads_reader
    assert "ads_->setDRATE(DRATE_30000SPS)" in ads_reader
    assert "ads_->readSingle()" in ads_reader
    assert "waitDrdyLow(1500)" in ads_reader
    assert "gainCalibrate(channel)" in ads_reader
    assert "PGA_VALUE_TABLE" in ads_reader
    assert "PGA_LIB_CONST" in ads_reader
    assert "reading.gain" in sensor_main
    assert "CMD_RDATA" not in ads_reader
    assert "CMD_WREG" not in ads_reader
    assert "spi_->transfer" not in ads_reader
    assert "movingAverageVoltage" in sensor_main
    assert "GLD_SENSOR_MOVING_AVERAGE_WINDOW" in moving_average
    assert "GLD_BATTERY_MV_INVALID" in power
    assert "analogSetPinAttenuation" in power
    assert "GldPowerMode::External5V" in power
    assert "GldPowerMode::External24V" in power
    assert "GldPowerMode::Battery" in power
    assert "mode != GldPowerMode::Battery" in power
    assert "pg24PowerGood" in pathlib.Path("firmware/gld/include/GldPower.h").read_text(encoding="utf-8")
    assert 'return "5v"' in power


def test_gld_nulling_selftest_scaffold_present():
    platformio = pathlib.Path("firmware/bench/platformio.ini").read_text(encoding="utf-8")
    board_pins = pathlib.Path("firmware/gld/include/BoardPins.h").read_text(encoding="utf-8")
    dac_header = pathlib.Path("firmware/gld/include/GldDacMux.h").read_text(encoding="utf-8")
    dac_src = pathlib.Path("firmware/gld/src/GldDacMux.cpp").read_text(encoding="utf-8")
    nulling_main = pathlib.Path("firmware/gld/src/GldNullingSelfTestMain.cpp").read_text(encoding="utf-8")

    assert "[env:gld_nulling_selftest_esp32s3]" in platformio
    assert "#define PGL_GLD_PIN_I2C_SDA 8" in board_pins
    assert "constexpr int PIN_I2C_SDA = PGL_GLD_PIN_I2C_SDA" in board_pins
    assert "#define PGL_GLD_PIN_I2C_SCL 9" in board_pins
    assert "constexpr int PIN_I2C_SCL = PGL_GLD_PIN_I2C_SCL" in board_pins
    assert "TCA9548A_ADDR = 0x71" in board_pins
    assert "MCP4725_ADDR = 0x60" in board_pins
    assert "SENSOR_TO_MUX_CH" in board_pins
    assert "{7, 6, 5, 4, 3, 2, 0, 1}" in board_pins
    assert "#include <TCA9548.h>" in dac_src
    assert "#include <MCP4725.h>" in dac_src
    assert "writeDAC(value, false)" in dac_src
    assert "selectChannel" in dac_src
    assert "GldDacMux" in dac_header
    assert "NULLING_STAGE=BEFORE" in nulling_main
    assert "NULLING_THRESHOLD_V = 0.0001f" in nulling_main
    assert "NULLING_MIN_FINAL_V = 0.0f" in nulling_main
    assert "positive=%u" in nulling_main
    assert "NULLING_STAGE=AFTER" in nulling_main
    assert "NULLING_RESULT ch=%u" in nulling_main
    assert "NULLING_SELFTEST_RESULT=PASS" in nulling_main
    assert "requires_external_power" in nulling_main
    assert "adsReady && dacReady && externalPower" in nulling_main
    assert "EEPROM" not in nulling_main
    assert "saveNullingProfile" not in nulling_main
    assert "transmit(" not in nulling_main
    assert "SENSOR_DATA" not in nulling_main
    assert "MSG_SENSOR_DATA" not in nulling_main


def test_lora_link_selftest_scaffold_present():
    platformio = pathlib.Path("firmware/bench/platformio.ini").read_text(encoding="utf-8")
    ch_pins = pathlib.Path("firmware/ch/include/ChBoardPins.h").read_text(encoding="utf-8")
    ch_rx = pathlib.Path("firmware/ch/src/ChStarRxSelfTestMain.cpp").read_text(encoding="utf-8")
    gld_tx = pathlib.Path("firmware/gld/src/GldLoRaTxSelfTestMain.cpp").read_text(encoding="utf-8")
    gld_config = pathlib.Path("firmware/gld/include/GldSelfTestConfig.h").read_text(encoding="utf-8")

    assert "[env:gld_lora_tx_selftest_esp32s3]" in platformio
    assert "[env:gld_lora_alarm_selftest_esp32s3]" in platformio
    assert "[env:ch_star_rx_selftest_esp32s3]" in platformio
    assert "PIN_RADIO_A_CS = 17" in ch_pins
    assert "PIN_RADIO_A_RST = 7" in ch_pins
    assert "PIN_RADIO_A_BUSY = 15" in ch_pins
    assert "PIN_RADIO_A_DIO1 = 16" in ch_pins
    assert "PIN_RADIO_A_TXEN = 5" in ch_pins
    assert "PIN_RADIO_A_RXEN = 6" in ch_pins
    assert "PIN_RADIO_B_CS = 14" in ch_pins
    assert "PIN_RADIO_B_BUSY = 38" in ch_pins
    assert "PIN_RADIO_B_RXEN = 39" in ch_pins
    assert "PIN_RADIO_B_TXEN = 40" in ch_pins
    assert "PIN_RADIO_B_RST = 41" in ch_pins
    assert "PIN_RADIO_B_DIO1 = 42" in ch_pins
    assert "STAR_SF = 7" in ch_rx
    assert "STAR_CR = 5" in ch_rx
    assert "SPISettings(STAR_SPI_HZ, MSBFIRST, SPI_MODE0)" in ch_rx
    assert "STAR_SPI_HZ = 2000000" in ch_rx
    assert "releaseRadioReset" in ch_rx
    assert "STAR_TCXO_VOLTAGE,\n        false" in ch_rx
    assert "CH_STAR_PROBE radio=%s beginState=%d" in ch_rx
    assert "CH_STAR_ACTIVE_RADIO=%s" in ch_rx
    assert "CH_STAR_RADIO_B_DIAGNOSTIC_FALLBACK=1" in ch_rx
    assert "CH_STAR_RX_READY=1" in ch_rx
    assert "CH_STAR_RX_IDLE_NO_RADIO" in ch_rx
    assert "parseGldUplinkFrame" in ch_rx
    assert "CH_LORA_RX_RESULT=PASS" in ch_rx
    assert "GLD_STAR_TX_SF = 7" in gld_tx
    assert "GLD_STAR_TX_CR = 5" in gld_tx
    assert "buildGldUplinkFrame" in gld_tx
    assert "TX_INTERVAL_MS = 10000" in gld_tx
    assert "GLD_TX_HEADER" in gld_tx
    assert "GLD_STAR_TX_WAIT" in gld_tx
    assert "GLD_STAR_TX_HEX" not in gld_tx
    assert "GLD_LORA_TX_RESULT=PASS" in gld_tx
    assert "GLD_GAS_CLEAR" in gld_tx
    assert "GLD_BATTERY_MV_INVALID" in gld_tx
    assert "CH_ID = 0x0064" in gld_config

    ch_runtime = pathlib.Path("firmware/ch/src/ChStarMeshRuntimeMain.cpp").read_text(encoding="utf-8")
    assert "CH_CACHE_SUMMARY" in ch_runtime
    assert "CH_CACHE_ENTRY" in ch_runtime
    assert "setPacketReceivedAction(onStarPacketReceived)" in ch_runtime
    assert "setPacketReceivedAction(onMeshPacketReceived)" in ch_runtime
    assert "startStarReceive(\"boot\")" in ch_runtime
    assert "startMeshReceive(\"boot\")" in ch_runtime
    assert "receiveStarOnce" not in ch_runtime
    assert "receiveMeshOnce" not in ch_runtime
    assert "CH_STAR_RX_HEX" not in ch_runtime
    assert "LoRaNormalPayload" not in gld_tx
    assert "LoRaAlarmPayload" not in gld_tx
    assert "LoRaHealthPayload" not in gld_tx
