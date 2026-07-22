#!/usr/bin/env python3
"""
GLD Dataset Recorder — subscribes to gas-leak-detector/+/dataset/data
and writes records to MySQL + CSV.

Usage:
    python gld_dataset_recorder.py
    Ctrl+C to stop.
"""
import csv
import hashlib
import json
import math
import os
import re
import socket
import struct
import sys
import time
import threading

# ─── Config ──────────────────────────────────────────────────────────────────
MQTT_HOST  = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT  = int(os.environ.get("MQTT_PORT", "1884"))
MQTT_USER  = os.environ.get("MQTT_USER", "").encode("utf-8")
MQTT_PASS  = os.environ.get("MQTT_PASS", "").encode("utf-8")
MQTT_CID   = b"py-dataset-recorder"
TOPIC      = "gas-leak-detector/+/dataset/data"

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASS = os.environ.get("MYSQL_PASS", "")
MYSQL_DB   = os.environ.get("MYSQL_DB", "pertamina_gld")

CSV_PATH   = os.environ.get("GLD_DATASET_CSV", "gld-dataset.csv")

# Columns match design Section 6.2.8 / 10.2.2 field names
COLS = [
    "device_id", "node_id", "mode", "seq", "timestamp_ms", "label", "nulling_profile_id",
    "sv0","sv1","sv2","sv3","sv4","sv5","sv6","sv7",
    "gain0","gain1","gain2","gain3","gain4","gain5","gain6","gain7",
    "sensor_status", "feature_order", "record_key",
]
EXPECTED_FEATURE_ORDER = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
VALID_GAINS = {1, 2, 4, 8, 16, 32, 64}
DEVICE_ID_RE = re.compile(r"^[0-9A-F]{4}$")

# ─── MySQL ────────────────────────────────────────────────────────────────────
try:
    import mysql.connector as _mc
    HAS_MYSQL = True
except ImportError:
    try:
        import pymysql as _mc
        _mc.install_as_MySQLdb()
        HAS_MYSQL = True
    except ImportError:
        HAS_MYSQL = False
        print("[WARN] No mysql driver found. Only CSV will be written.", flush=True)

db_conn = None

def ensure_db():
    global db_conn
    if not HAS_MYSQL:
        return False
    try:
        # is_connected() is a mysql.connector-only method; pymysql connections
        # don't have it, so guard with hasattr instead of assuming the
        # mysql.connector API on whichever driver actually imported.
        alive = db_conn is not None and (
            not hasattr(db_conn, "is_connected") or db_conn.is_connected()
        )
        if not alive:
            if hasattr(_mc, "connect"):
                db_conn = _mc.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                                      user=MYSQL_USER, password=MYSQL_PASS,
                                      database=MYSQL_DB, autocommit=True)
            else:
                import pymysql
                db_conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                                          user=MYSQL_USER, password=MYSQL_PASS,
                                          database=MYSQL_DB, autocommit=True)
        return True
    except Exception as e:
        print(f"[DB] connect error: {e}", flush=True)
        db_conn = None
        return False

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS gld_dataset (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  device_id VARCHAR(16),
  node_id INT UNSIGNED,
  mode VARCHAR(16) DEFAULT 'DATASET',
  seq INT UNSIGNED,
  timestamp_ms BIGINT UNSIGNED,
  label VARCHAR(32),
  nulling_profile_id TINYINT UNSIGNED DEFAULT 0,
  sv0 FLOAT, sv1 FLOAT, sv2 FLOAT, sv3 FLOAT,
  sv4 FLOAT, sv5 FLOAT, sv6 FLOAT, sv7 FLOAT,
  gain0 TINYINT, gain1 TINYINT, gain2 TINYINT, gain3 TINYINT,
  gain4 TINYINT, gain5 TINYINT, gain6 TINYINT, gain7 TINYINT,
  sensor_status VARCHAR(32) NOT NULL,
  feature_order VARCHAR(128) NOT NULL,
  record_key CHAR(64) NOT NULL,
  UNIQUE KEY uq_gld_dataset_record_key (record_key)
)"""

INSERT_SQL = """
INSERT INTO gld_dataset
  (device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,
   sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,
   gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7,
   sensor_status,feature_order,record_key)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

SCHEMA_COLUMNS = {
    "sensor_status": "VARCHAR(32) NULL",
    "feature_order": "VARCHAR(128) NULL",
    "record_key": "CHAR(64) NULL",
}

def db_init(reset=False):
    if ensure_db():
        try:
            cur = db_conn.cursor()
            if reset:
                cur.execute("DROP TABLE IF EXISTS gld_dataset")
                print("[DB] Dropped old gld_dataset table.", flush=True)
            cur.execute(CREATE_SQL)
            for name, definition in SCHEMA_COLUMNS.items():
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='gld_dataset' AND COLUMN_NAME=%s",
                    (MYSQL_DB, name),
                )
                if int(cur.fetchone()[0]) == 0:
                    cur.execute(f"ALTER TABLE gld_dataset ADD COLUMN {name} {definition}")
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='gld_dataset' AND INDEX_NAME='uq_gld_dataset_record_key'",
                (MYSQL_DB,),
            )
            if int(cur.fetchone()[0]) == 0:
                cur.execute("ALTER TABLE gld_dataset ADD UNIQUE KEY uq_gld_dataset_record_key (record_key)")
            cur.close()
            print("[DB] Table ready.", flush=True)
        except Exception as e:
            print(f"[DB] CREATE TABLE: {e}", flush=True)

def db_insert(row):
    if not ensure_db():
        return "unavailable"
    try:
        cur = db_conn.cursor()
        cur.execute("SELECT 1 FROM gld_dataset WHERE record_key=%s LIMIT 1", (row[-1],))
        if cur.fetchone() is not None:
            cur.close()
            return "duplicate"
        cur.execute(INSERT_SQL, row)
        cur.close()
        return "inserted"
    except Exception as e:
        print(f"[DB] INSERT error: {e}", flush=True)
        return "error"

# ─── CSV ──────────────────────────────────────────────────────────────────────
csv_lock = threading.Lock()
seen_record_keys = set()

def csv_init():
    global seen_record_keys
    with csv_lock:
        parent = os.path.dirname(os.path.abspath(CSV_PATH))
        os.makedirs(parent, exist_ok=True)
        is_new = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
        if is_new:
            with open(CSV_PATH, "x" if not os.path.exists(CSV_PATH) else "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(COLS)
                f.flush()
                os.fsync(f.fileno())
        else:
            with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != COLS:
                    raise RuntimeError("existing CSV schema does not match the validated dataset schema; choose a new CSV path")
                seen_record_keys = {row["record_key"] for row in reader if row.get("record_key")}
        print(f"[CSV] {'Header written to' if is_new else 'Appending to existing'} {CSV_PATH}", flush=True)

def csv_append(row):
    with csv_lock:
        try:
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(row)
                f.flush()
                os.fsync(f.fileno())
            return True
        except Exception as e:
            print(f"[CSV] append error: {e}", flush=True)
            return False

# ─── Record processing ────────────────────────────────────────────────────────
total = 0

def _record_key(record):
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def normalize_record(d, topic=None):
    if not isinstance(d, dict):
        raise ValueError("payload must be a JSON object")
    device_id = str(d.get("device_id") or "").upper()
    if not DEVICE_ID_RE.fullmatch(device_id):
        raise ValueError("device_id must be exactly four hexadecimal digits")
    if topic:
        parts = topic.split("/")
        if len(parts) != 4 or parts[0] != "gas-leak-detector" or parts[1].upper() != device_id or parts[2:] != ["dataset", "data"]:
            raise ValueError("MQTT topic device does not match payload device_id")
    node_id = d.get("node_id")
    if not isinstance(node_id, int) or isinstance(node_id, bool) or node_id != int(device_id, 16):
        raise ValueError("node_id must equal the hexadecimal device_id")
    if str(d.get("mode") or "").upper() != "DATASET":
        raise ValueError("mode must be DATASET")
    seq = d.get("seq")
    timestamp_ms = d.get("timestamp_ms")
    profile_id = d.get("nulling_profile_id")
    if not isinstance(seq, int) or isinstance(seq, bool) or not 0 <= seq <= 0xFFFFFFFF:
        raise ValueError("seq must be a uint32")
    if not isinstance(timestamp_ms, int) or isinstance(timestamp_ms, bool) or not 0 <= timestamp_ms <= 0xFFFFFFFF:
        raise ValueError("timestamp_ms must be a uint32")
    if not isinstance(profile_id, int) or isinstance(profile_id, bool) or not 1 <= profile_id <= 255:
        raise ValueError("nulling_profile_id must be 1..255")
    label = str(d.get("label") or "")
    if not label or len(label) > 31 or any(ord(char) < 32 for char in label) or label[0] in "=+-@":
        raise ValueError("label is empty, unsafe for CSV, or longer than 31 characters")

    sv = d.get("sensor_voltage")
    gain = d.get("sensor_gain")
    status = d.get("sensor_status")
    feature_order = d.get("feature_order")
    if not isinstance(sv, list) or len(sv) != 8 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in sv):
        raise ValueError("sensor_voltage must contain exactly eight finite numbers")
    if not isinstance(gain, list) or len(gain) != 8 or any(isinstance(value, bool) or not isinstance(value, int) or value not in VALID_GAINS for value in gain):
        raise ValueError("sensor_gain must contain exactly eight supported integer PGA gains")
    if not isinstance(status, list) or len(status) != 8 or any(value != 0 or isinstance(value, bool) for value in status):
        raise ValueError("all eight sensor_status values must be Ok (0)")
    if feature_order != EXPECTED_FEATURE_ORDER:
        raise ValueError("feature_order does not match the canonical model order")

    identity = {
        "device_id": device_id,
        "node_id": node_id,
        "seq": seq,
        "timestamp_ms": timestamp_ms,
        "label": label,
        "nulling_profile_id": profile_id,
        "sensor_voltage": sv,
        "sensor_gain": gain,
        "sensor_status": status,
        "feature_order": feature_order,
    }
    key = _record_key(identity)
    row = [
        device_id, node_id, "DATASET", seq, timestamp_ms, label, profile_id,
        *sv, *gain,
        json.dumps(status, separators=(",", ":")),
        json.dumps(feature_order, separators=(",", ":")),
        key,
    ]
    return row, key


def process_record(json_str, topic=None):
    global total
    try:
        d = json.loads(json_str)
    except Exception as e:
        print(f"[JSON] parse error: {e}", flush=True)
        return False
    try:
        row, key = normalize_record(d, topic)
    except ValueError as e:
        print(f"[REJECT] {e}", flush=True)
        return False
    if key in seen_record_keys:
        print(f"[DEDUP] seq={d.get('seq')} key={key[:12]}", flush=True)
        return False
    db_result = db_insert(tuple(row))
    if db_result == "error":
        return False
    if not csv_append(row):
        return False
    seen_record_keys.add(key)
    total += 1
    print(f"[REC] seq={d.get('seq')} label={d.get('label')} sv0={row[7]:.4f} db={db_result} total={total}", flush=True)
    return True

# ─── MQTT raw client ──────────────────────────────────────────────────────────
def enc_rem(n):
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        if n: b |= 0x80
        out.append(b)
        if not n: break
    return bytes(out)

def read_packet(sock):
    hdr = sock.recv(1)
    if not hdr:
        raise ConnectionError("connection closed")
    rem = 0; mul = 1
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("connection closed mid-header")
        b = chunk[0]; rem += (b & 0x7F) * mul; mul <<= 7
        if not (b & 0x80): break
    data = b""
    while len(data) < rem:
        chunk = sock.recv(rem - len(data))
        if not chunk:
            raise ConnectionError("connection closed mid-packet")
        data += chunk
    return hdr[0], data

def mqtt_run():
    topic_bytes = TOPIC.encode("ascii")
    while True:
        s = None
        try:
            s = socket.socket()
            s.settimeout(30)
            s.connect((MQTT_HOST, MQTT_PORT))

            # CONNECT
            cid = struct.pack(">H", len(MQTT_CID)) + MQTT_CID
            flags = 0x02
            auth = b""
            if MQTT_USER:
                flags |= 0x80
                auth += struct.pack(">H", len(MQTT_USER)) + MQTT_USER
            if MQTT_PASS:
                flags |= 0x40
                auth += struct.pack(">H", len(MQTT_PASS)) + MQTT_PASS
            var = b"\x00\x04MQTT\x04" + bytes([flags]) + b"\x00\x3c" + cid + auth
            s.sendall(b"\x10" + enc_rem(len(var)) + var)
            ht, data = read_packet(s)
            if data[1] != 0:
                raise RuntimeError(f"CONNACK error {data[1]}")
            print(f"[MQTT] Connected to {MQTT_HOST}:{MQTT_PORT}", flush=True)

            # SUBSCRIBE
            tp  = struct.pack(">H", len(topic_bytes)) + topic_bytes + b"\x00"
            var = struct.pack(">H", 1) + tp
            s.sendall(b"\x82" + enc_rem(len(var)) + var)
            read_packet(s)  # SUBACK
            print(f"[MQTT] Subscribed to {TOPIC}", flush=True)

            # Read loop
            s.settimeout(60)
            while True:
                try:
                    ht, data = read_packet(s)
                except socket.timeout:
                    s.sendall(b"\xC0\x00")
                    continue
                ptype = ht & 0xF0
                if ptype == 0x30:   # PUBLISH
                    if len(data) < 2:
                        raise ValueError("truncated MQTT PUBLISH")
                    tlen = struct.unpack(">H", data[:2])[0]
                    if 2 + tlen > len(data):
                        raise ValueError("truncated MQTT PUBLISH topic")
                    topic = data[2:2+tlen].decode("utf-8", errors="strict")
                    offset = 2 + tlen
                    qos = (ht >> 1) & 0x03
                    if qos:
                        if offset + 2 > len(data):
                            raise ValueError("truncated MQTT PUBLISH packet id")
                        offset += 2
                    payload = data[offset:].decode("utf-8", errors="strict")
                    process_record(payload, topic)
                elif ptype == 0xD0:  # PINGRESP
                    pass
        except KeyboardInterrupt:
            print(f"\n[DONE] Total records: {total}", flush=True)
            break
        except Exception as e:
            print(f"[MQTT] error: {e}; reconnecting in 3s", flush=True)
            time.sleep(3)
        finally:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass


if __name__ == "__main__":
    reset_db = "--reset-db" in sys.argv
    print(f"GLD Dataset Recorder starting...", flush=True)
    print(f"  MQTT: {MQTT_HOST}:{MQTT_PORT}  topic: {TOPIC}", flush=True)
    print(f"  MySQL: {MYSQL_HOST}/{MYSQL_DB}  CSV: {CSV_PATH}", flush=True)
    if reset_db:
        print(f"  [!] --reset-db: gld_dataset table will be dropped and recreated.", flush=True)
    print(f"  Ctrl+C to stop.", flush=True)

    db_init(reset=reset_db)
    try:
        csv_init()
        mqtt_run()
    finally:
        if db_conn is not None:
            try:
                db_conn.close()
            except Exception:
                pass
