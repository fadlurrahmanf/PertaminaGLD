#!/usr/bin/env python3
"""
GLD Dataset Recorder — subscribes to gas-leak-detector/+/dataset/data
and writes records to MySQL + CSV.

Usage:
    python gld_dataset_recorder.py
    Ctrl+C to stop.
"""
import csv
import json
import os
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
]

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
  gain4 TINYINT, gain5 TINYINT, gain6 TINYINT, gain7 TINYINT
)"""

INSERT_SQL = """
INSERT INTO gld_dataset
  (device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,
   sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,
   gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

def db_init(reset=False):
    if ensure_db():
        try:
            cur = db_conn.cursor()
            if reset:
                cur.execute("DROP TABLE IF EXISTS gld_dataset")
                print("[DB] Dropped old gld_dataset table.", flush=True)
            cur.execute(CREATE_SQL)
            cur.close()
            print("[DB] Table ready.", flush=True)
        except Exception as e:
            print(f"[DB] CREATE TABLE: {e}", flush=True)

def db_insert(row):
    if not ensure_db():
        return
    try:
        cur = db_conn.cursor()
        cur.execute(INSERT_SQL, row)
        cur.close()
    except Exception as e:
        print(f"[DB] INSERT error: {e}", flush=True)

# ─── CSV ──────────────────────────────────────────────────────────────────────
csv_lock = threading.Lock()

def csv_init():
    with csv_lock:
        try:
            # Append rather than truncate: restarting the recorder (crash,
            # reboot, re-run) must not erase previously captured rows. Only
            # write the header when the file is new/empty.
            is_new = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                if is_new:
                    csv.writer(f).writerow(COLS)
            print(f"[CSV] {'Header written to' if is_new else 'Appending to existing'} {CSV_PATH}", flush=True)
        except Exception as e:
            print(f"[CSV] init error: {e}", flush=True)

def csv_append(row):
    with csv_lock:
        try:
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(row)
        except Exception as e:
            print(f"[CSV] append error: {e}", flush=True)

# ─── Record processing ────────────────────────────────────────────────────────
total = 0

def process_record(json_str):
    global total
    try:
        d = json.loads(json_str)
    except Exception as e:
        print(f"[JSON] parse error: {e}", flush=True)
        return

    sv   = d.get("sensor_voltage", [0.0]*8)
    gain = d.get("sensor_gain",    [0]*8)

    # Pad to 8 in case firmware sends fewer values
    while len(sv)   < 8: sv.append(0.0)
    while len(gain) < 8: gain.append(0)

    row = [
        d.get("device_id", ""),
        d.get("node_id", 0),
        d.get("mode", "DATASET"),
        d.get("seq", 0),
        d.get("timestamp_ms", 0),
        d.get("label", ""),
        d.get("nulling_profile_id", 0),
        sv[0], sv[1], sv[2], sv[3], sv[4], sv[5], sv[6], sv[7],
        gain[0], gain[1], gain[2], gain[3], gain[4], gain[5], gain[6], gain[7],
    ]

    csv_append(row)
    db_insert(tuple(row))
    total += 1
    print(f"[REC] seq={d.get('seq')} label={d.get('label')} sv0={sv[0]:.4f} total={total}", flush=True)

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
                ht, data = read_packet(s)
                ptype = ht & 0xF0
                if ptype == 0x30:   # PUBLISH
                    tlen = struct.unpack(">H", data[:2])[0]
                    payload = data[2+tlen:].decode("utf-8", errors="replace")
                    process_record(payload)
                elif ptype == 0xD0:  # PINGRESP
                    pass
        except socket.timeout:
            try:
                s.sendall(b"\xC0\x00")
            except:
                pass
        except KeyboardInterrupt:
            print(f"\n[DONE] Total records: {total}", flush=True)
            break
        except Exception as e:
            print(f"[MQTT] error: {e} — reconnecting in 3s", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    reset_db = "--reset-db" in sys.argv
    print(f"GLD Dataset Recorder starting...", flush=True)
    print(f"  MQTT: {MQTT_HOST}:{MQTT_PORT}  topic: {TOPIC}", flush=True)
    print(f"  MySQL: {MYSQL_HOST}/{MYSQL_DB}  CSV: {CSV_PATH}", flush=True)
    if reset_db:
        print(f"  [!] --reset-db: gld_dataset table will be dropped and recreated.", flush=True)
    print(f"  Ctrl+C to stop.", flush=True)

    db_init(reset=reset_db)
    csv_init()
    mqtt_run()
