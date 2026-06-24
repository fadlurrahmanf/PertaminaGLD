#!/usr/bin/env python3
"""Deploy the GLD Dataset Server tab to a running Node-RED instance."""

import json
import sys
import urllib.request
import urllib.error

NODERED_URL = "http://127.0.0.1:1880"
BROKER_ID   = "pgl_mqtt_broker"   # reuse existing MQTT broker config node
CSV_PATH    = "C:\\\\Users\\\\asus\\\\gld-dataset.csv"  # double-escaped for JS string

def id_(name):
    return f"pgld_ds_{name}"

TAB_ID      = id_("tab")
MYSQL_ID    = id_("mysql_cfg")

# ---------------------------------------------------------------------------
# JavaScript function bodies (plain Python strings — no escaping surprises)
# ---------------------------------------------------------------------------

PARSE_FN = (
    "var p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload;"
    "if(!p||p.seq===undefined||!p.sensor_voltage||p.sensor_voltage.length!==8){node.warn('invalid record');return null;}"
    "var sv=p.sensor_voltage,gain=p.sensor_gain||[0,0,0,0,0,0,0,0];"
    "msg.topic='INSERT INTO gld_dataset"
    " (device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,"
    "sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,"
    "gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)';"
    "msg.payload=["
    "p.device_id||'',p.node_id||0,p.mode||'DATASET',p.seq,p.timestamp_ms||0,p.label||'',p.nulling_profile_id||0,"
    "sv[0],sv[1],sv[2],sv[3],sv[4],sv[5],sv[6],sv[7],"
    "gain[0],gain[1],gain[2],gain[3],gain[4],gain[5],gain[6],gain[7]];"
    "return msg;"
)

CREATE_TABLE_FN = (
    "msg.topic='CREATE TABLE IF NOT EXISTS gld_dataset ("
    "id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,"
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "device_id VARCHAR(16),node_id INT UNSIGNED,"
    "mode VARCHAR(16) DEFAULT \\'DATASET\\',"
    "seq INT UNSIGNED,timestamp_ms BIGINT UNSIGNED,"
    "label VARCHAR(32),nulling_profile_id TINYINT UNSIGNED DEFAULT 0,"
    "sv0 FLOAT,sv1 FLOAT,sv2 FLOAT,sv3 FLOAT,"
    "sv4 FLOAT,sv5 FLOAT,sv6 FLOAT,sv7 FLOAT,"
    "gain0 TINYINT,gain1 TINYINT,gain2 TINYINT,gain3 TINYINT,"
    "gain4 TINYINT,gain5 TINYINT,gain6 TINYINT,gain7 TINYINT)';"
    "msg.payload=[];return msg;"
)

CSV_ROW_FN = (
    "var p=(typeof msg.payload==='string')?JSON.parse(msg.payload):msg.payload;"
    "if(!p||!p.sensor_voltage)return null;"
    "var sv=p.sensor_voltage,gain=p.sensor_gain||[0,0,0,0,0,0,0,0];"
    "msg.payload=[p.device_id||'',p.node_id||0,p.mode||'DATASET',p.seq,p.timestamp_ms||0,p.label||'',p.nulling_profile_id||0]"
    ".concat(sv).concat(gain).join(',')+String.fromCharCode(10);"
    "msg.filename=global.get('gld_csv_path')||'" + CSV_PATH + "';"
    "return msg;"
)

CSV_HEADER_FN = (
    "msg.payload='device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,"
    "sv0,sv1,sv2,sv3,sv4,sv5,sv6,sv7,"
    "gain0,gain1,gain2,gain3,gain4,gain5,gain6,gain7'+String.fromCharCode(10);"
    "msg.filename=global.get('gld_csv_path')||'" + CSV_PATH + "';"
    "return msg;"
)

INIT_FN = (
    "global.set('gld_csv_path','" + CSV_PATH + "');"
    "return msg;"
)

# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------

def fn(nid, name, func, x, y, wires, outputs=1):
    return {"id": id_(nid), "type": "function", "z": TAB_ID, "name": name,
            "func": func, "outputs": outputs, "timeout": 0, "noerr": 0,
            "initialize": "", "finalize": "", "libs": [], "x": x, "y": y, "wires": wires}

def dbg(nid, name, x, y, status_val="payload"):
    return {"id": id_(nid), "type": "debug", "z": TAB_ID, "name": name,
            "active": True, "tosidebar": True, "console": False, "tostatus": True,
            "complete": "payload", "targetType": "msg",
            "statusVal": status_val, "statusType": "msg",
            "x": x, "y": y, "wires": []}

def mqtt_in(nid, name, topic, x, y, wires, retain=False):
    return {"id": id_(nid), "type": "mqtt in", "z": TAB_ID, "name": name,
            "topic": topic, "qos": "0", "datatype": "auto", "broker": BROKER_ID,
            "nl": False, "rap": retain, "rh": 0, "inputs": 0,
            "x": x, "y": y, "wires": wires}

def mysql(nid, name, x, y, wires):
    return {"id": id_(nid), "type": "mysql", "z": TAB_ID, "name": name,
            "mydb": MYSQL_ID, "x": x, "y": y, "wires": wires}

def file_node(nid, name, overwrite, x, y):
    return {"id": id_(nid), "type": "file", "z": TAB_ID, "name": name,
            "filename": "filename", "filenameType": "msg",
            "appendNewline": False, "createDir": True,
            "overwriteFile": "true" if overwrite else "false",
            "x": x, "y": y, "wires": [[]]}

def inject(nid, name, x, y, wires, once=True):
    return {"id": id_(nid), "type": "inject", "z": TAB_ID, "name": name,
            "props": [{"p": "payload"}],
            "repeat": "", "once": once, "onceDelay": "0.5",
            "payload": "", "payloadType": "date",
            "x": x, "y": y, "wires": wires}


nodes = [
    inject("init_inject", "init on boot", 160, 80,
           [[id_("init_fn")]]),

    fn("init_fn", "set csv path", INIT_FN, 380, 80,
       [[id_("create_table_fn"), id_("csv_header_fn")]]),

    fn("create_table_fn", "CREATE TABLE SQL", CREATE_TABLE_FN, 640, 60,
       [[id_("mysql_init")]]),

    mysql("mysql_init", "CREATE TABLE", 880, 60, [[]]),

    fn("csv_header_fn", "CSV header", CSV_HEADER_FN, 640, 120,
       [[id_("csv_header_file")]]),

    file_node("csv_header_file", "write CSV header", overwrite=True, x=880, y=120),

    # Dataset record pipeline
    mqtt_in("mqtt_data_in", "dataset/data",
            "gas-leak-detector/+/dataset/data", 160, 260,
            [[id_("parse_record_fn"), id_("csv_row_fn"), id_("debug_record")]]),

    fn("parse_record_fn", "parse record", PARSE_FN, 400, 260,
       [[id_("mysql_insert")]]),

    mysql("mysql_insert", "INSERT record", 660, 220, [[]]),

    fn("csv_row_fn", "format CSV row", CSV_ROW_FN, 660, 280,
       [[id_("csv_append_file")]]),

    file_node("csv_append_file", "append CSV", overwrite=False, x=880, y=280),

    dbg("debug_record", "record", 660, 340, "payload.label"),

    # Status and nulling viewers
    mqtt_in("mqtt_status_in", "dataset/status",
            "gas-leak-detector/+/dataset/status", 160, 440,
            [[id_("debug_status")]]),

    dbg("debug_status", "status", 400, 440, "payload.state"),

    mqtt_in("mqtt_nulling_in", "nulling/result",
            "gas-leak-detector/+/nulling/result", 160, 520,
            [[id_("debug_nulling")]], retain=True),

    dbg("debug_nulling", "nulling profile", 400, 520, "payload.profileId"),
]

configs = [
    {"id": MYSQL_ID, "type": "MySQLdatabase", "name": "GLD Dataset DB",
     "host": "localhost", "port": "3306", "db": "pertamina_gld",
     "credentials": {"user": "root", "password": ""},
     "tz": "Asia/Jakarta", "charset": "UTF8"},
]

flow = {
    "id":       TAB_ID,
    "label":    "GLD Dataset Server",
    "disabled": False,
    "info":     "Dataset recording: GLD sensor records via MQTT to MySQL + CSV.",
    "nodes":    nodes,
    "configs":  configs,
}

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

def http(method, url, data=None):
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            if not raw:
                return r.status, None
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def get_flows():
    with urllib.request.urlopen(f"{NODERED_URL}/flows", timeout=15) as r:
        data = json.loads(r.read())
    return data.get("flows", data) if isinstance(data, dict) else data


def existing_dataset_flow_ids():
    flows = get_flows()
    ids = []
    for n in flows:
        nid = str(n.get("id", ""))
        label = str(n.get("label", ""))
        if nid == TAB_ID or label == "GLD Dataset Server":
            ids.append(nid)
    return ids


# Delete existing dataset tab(s). Older deployments used a generated Node-RED
# tab id, so lookup by fixed id alone is not enough.
deleted = 0
for flow_id in existing_dataset_flow_ids():
    del_status, _ = http("DELETE", f"{NODERED_URL}/flow/{flow_id}")
    if del_status in (200, 204):
        deleted += 1
        print(f"Deleted existing tab {flow_id}")
    else:
        print(f"Could not delete existing tab {flow_id} (status {del_status})")
if deleted == 0:
    print("No existing GLD Dataset Server tab to delete")

# POST the new tab
status, resp = http("POST", f"{NODERED_URL}/flow", flow)
if status in (200, 201):
    tab_id = resp.get("id", "?") if isinstance(resp, dict) else "?"
    print(f"SUCCESS tabId={tab_id} nodes={len(nodes)} configs={len(configs)}")
else:
    print(f"FAILED status={status} response={resp}", file=sys.stderr)
    sys.exit(1)
