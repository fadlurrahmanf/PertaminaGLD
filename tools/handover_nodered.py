"""Prepare an isolated portable Node-RED profile; deploy via revisioned local API.

Preparation runs copied generators only. It never starts Node-RED or changes the
source snapshot, repository flows, current user profile or an existing work profile.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handover_runtime as archive_util

RECEIPT = "nodered-prepared.json"
PROJECT_LABELS = {"Pertamina GLD Server", "GLD Dataset Server"}


def require(condition, message):
    archive_util._require(condition, message)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _nodes(value):
    if isinstance(value, dict): value = value.get("flows")
    require(isinstance(value, list) and all(isinstance(n, dict) and isinstance(n.get("id"), str) for n in value),
            "NODE_RED_INVALID_FLOW_DOCUMENT")
    require(len({n["id"] for n in value}) == len(value), "NODE_RED_DUPLICATE_NODE_IDS")
    return value


def _nonproject(nodes):
    replaced = {n["id"] for n in nodes if n.get("type") == "tab" and n.get("label") in PROJECT_LABELS}
    return [copy.deepcopy(n) for n in nodes if not (n["id"].startswith(("pgl_", "pgld_ds_")) or
            n["id"] in replaced or n.get("z") in replaced)]


def _copy_tree(source, destination, *, exclude_modules=False):
    require(source.is_dir() and not archive_util._reparse(source), "NODE_RED_SNAPSHOT_TREE_UNAVAILABLE")
    for current, directories, files in os.walk(source, followlinks=False):
        base = Path(current); relative = base.relative_to(source); target = destination / relative
        allowed = []
        for name in sorted(directories):
            child = base / name
            require(not archive_util._reparse(child), "NODE_RED_LINKED_SNAPSHOT_REFUSED")
            if not (exclude_modules and name == "node_modules"):
                allowed.append(name)
        directories[:] = allowed; target.mkdir(parents=True, exist_ok=True)
        for name in files:
            path = base / name
            require(path.is_file() and not archive_util._reparse(path), "NODE_RED_LINKED_SNAPSHOT_REFUSED")
            shutil.copy2(path, target / name)


def _fingerprint(snapshot, generator, system, dbconfig, ports, offset):
    digest = hashlib.sha256()
    inputs = [(snapshot, "snapshot", sorted(snapshot.rglob("*"))),
              (generator, "generator", [generator / "apply-pertamina-gld-flow.js", generator / "apply-pertamina-gld-dataset-flow.ps1"] +
               sorted((generator / "functions").rglob("*")))]
    for source, prefix, paths in inputs:
        for path in paths:
            require(not archive_util._reparse(path), "NODE_RED_LINKED_INPUT_REFUSED")
            if path.is_file() and "node_modules" not in path.relative_to(source).parts:
                digest.update((prefix + "/" + path.relative_to(source).as_posix()).encode())
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    digest.update(json.dumps(dict(system=system, database=dbconfig, ports=ports, offset=offset), sort_keys=True).encode())
    return digest.hexdigest()


def _run(args, env):
    result = subprocess.run(args, env=env, capture_output=True, timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0, "NODE_RED_COPIED_GENERATOR_FAILED")


def _settings_tail(port, local_only=True):
    # Names and other settings remain from the copied profile. Only filesystem
    # locations are rebased; filenames in the snapshot remain available.
    return "\n// Portable handover overrides; original is preserved in handover-original.\n" + f"""
{"module.exports.uiHost = '127.0.0.1';" if local_only else "// Preserve the original dashboard bind address on a normal handover."}
module.exports.uiPort = {port};
module.exports.userDir = __dirname;
module.exports.flowFile = 'flows.json';
module.exports.functionGlobalContext = Object.assign({{}}, module.exports.functionGlobalContext || {{}}, {{
    crypto: require('crypto'), fs: require('fs'), path: require('path')
}});
const __handoverPath = require('path');
const __handoverStores = Object.assign({{}}, module.exports.contextStorage || {{}});
for (const [name, store] of Object.entries(__handoverStores)) {{
    if (store && typeof store === 'object' && store.module === 'localfilesystem') {{
        const prior = store.config && store.config.dir;
        const folder = prior ? __handoverPath.basename(String(prior)) : 'context';
        __handoverStores[name] = Object.assign({{}}, store, {{config: Object.assign({{}}, store.config || {{}}, {{
            dir: __handoverPath.join(__dirname, folder)
        }})}});
    }}
}}
if (!__handoverStores.pglTopologyFile) {{
    __handoverStores.pglTopologyFile = {{module:'localfilesystem',config:{{dir:__handoverPath.join(__dirname,'pgl-context')}}}};
}}
module.exports.contextStorage = __handoverStores;
"""


def _isolate_nonproject(nodes, offset):
    if not offset: return nodes
    for node in nodes:
        if node.get("type") in ("aedes broker", "mqtt-broker"):
            if node.get("type") == "aedes broker":
                # node-red-contrib-aedes uses mqtt_port, not the core MQTT
                # config node's port field. Preserve disabled WS listeners.
                field = "mqtt_port" if "mqtt_port" in node or "port" not in node else "port"
                fields = [field] + (["mqtt_ws_port"] if str(node.get("mqtt_ws_port", "")) not in ("", "0", "None") else [])
                for key in fields:
                    try: port = int(node.get(key, 1883)) + offset
                    except (TypeError, ValueError): raise archive_util.RuntimeErrorSafe("NODE_RED_INVALID_SNAPSHOT_BROKER_PORT") from None
                    require(1024 <= port <= 65535, "NODE_RED_INVALID_SNAPSHOT_BROKER_PORT")
                    node[key] = str(port)
                node["host"] = "127.0.0.1"
            else:
                try: port = int(node.get("port", 1883)) + offset
                except (TypeError, ValueError): raise archive_util.RuntimeErrorSafe("NODE_RED_INVALID_SNAPSHOT_BROKER_PORT") from None
                require(1024 <= port <= 65535, "NODE_RED_INVALID_SNAPSHOT_BROKER_PORT")
                node["port"] = str(port)
                if str(node.get("broker", "")).lower() not in ("localhost", "127.0.0.1", "::1", ""):
                    node["broker"] = "127.0.0.1"; node["autoConnect"] = False
    return nodes


def prepare(repo_root, snapshot_root, runtime_root, work_root, system, dbconfig, ports, port_offset=0):
    repo, snapshot_root, runtime, work = (Path(p).absolute() for p in (repo_root, snapshot_root, runtime_root, work_root))
    snapshot = snapshot_root / "nodered"; source_generator = repo / "server/nodered"
    require(snapshot.is_dir() and (snapshot / "settings.js").is_file() and (snapshot / "flows.json").is_file(), "NODE_RED_PROFILE_SNAPSHOT_MISSING")
    require(type(port_offset) is int, "NODE_RED_INVALID_PORT_OFFSET")
    effective = {}
    for key in ("nodeRed", "mqtt", "database", "hub"):
        value = ports.get(key)
        require(type(value) is int and 1024 <= value + port_offset <= 65535, "NODE_RED_INVALID_PORT")
        effective[key] = value + port_offset
    require(len(set(effective.values())) == len(effective), "NODE_RED_PORTS_CONFLICT")
    require(isinstance(system, dict) and isinstance(system.get("serverEnv"), dict) and isinstance(system.get("broker"), dict),
            "NODE_RED_SYSTEM_CONFIGURATION_MISSING")
    broker = system["broker"]
    require(all(isinstance(broker.get(k), str) and broker[k] for k in ("host", "username", "password")), "NODE_RED_BROKER_CONFIGURATION_MISSING")
    require(all(isinstance(dbconfig.get(k), str) and dbconfig[k] for k in ("name", "user", "password")), "NODE_RED_DATABASE_CONFIGURATION_MISSING")
    node = runtime / "node/node.exe"
    modules = runtime / "user-node_modules"
    require(node.is_file() and (modules / "node-red-node-mysql/package.json").is_file(), "NODE_RED_RUNTIME_OR_MYSQL_MODULE_MISSING")
    profile = work / "nodered"; generator = work / "generator"; flows_path = work / "nodered-deployment-flows.json"
    receipt_path = work / RECEIPT
    fingerprint = _fingerprint(snapshot, source_generator, system, dbconfig, ports, port_offset)
    result = dict(profile=str(profile), flows=str(flows_path), generator=str(generator), ports=effective,
                  csv=str(work / "history/incoming/gld-dataset.csv"))
    if receipt_path.exists():
        receipt = _json(receipt_path)
        require(receipt.get("fingerprint") == fingerprint and profile.is_dir() and flows_path.is_file(), "NODE_RED_PROFILE_INPUTS_CHANGED_OR_INCOMPLETE")
        return result
    archive_util._empty_destination(profile)
    require(not generator.exists() and not flows_path.exists(), "NODE_RED_WORK_FILES_ALREADY_EXIST")
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nodered-prepare-", dir=work) as temporary:
        stage = Path(temporary); staged_profile = stage / "nodered"; staged_generator = stage / "generator"
        _copy_tree(snapshot, staged_profile, exclude_modules=True)
        raw_dir = staged_profile / "handover-original"; raw_dir.mkdir(exist_ok=True)
        for name in ("settings.js", "flows.json", "flows_cred.json", ".config.runtime.json"):
            if (snapshot / name).is_file(): shutil.copy2(snapshot / name, raw_dir / name)
        _copy_tree(modules, staged_profile / "node_modules")
        with (staged_profile / "settings.js").open("a", encoding="utf-8") as stream:
            stream.write(_settings_tail(effective["nodeRed"], local_only=bool(port_offset)))
        nonproject = _isolate_nonproject(_nonproject(_nodes(_json(snapshot / "flows.json"))), port_offset)
        (staged_profile / "flows.json").write_text(json.dumps(nonproject, ensure_ascii=False, indent=2), encoding="utf-8")
        staged_generator.mkdir()
        for name in ("apply-pertamina-gld-flow.js", "apply-pertamina-gld-dataset-flow.ps1"):
            shutil.copy2(source_generator / name, staged_generator / name)
        _copy_tree(source_generator / "functions", staged_generator / "functions")
        env = os.environ.copy()
        for key, value in system["serverEnv"].items():
            require(isinstance(key, str) and isinstance(value, str), "NODE_RED_INVALID_SERVER_ENVIRONMENT")
            env[key] = value
        env["MQTT_USER"], env["MQTT_PASS"] = broker["username"], broker["password"]
        host = "127.0.0.1" if port_offset else broker["host"]
        replay = profile / "pertamina-gld-replay-state.json"
        env["PGL_REPLAY_STATE_PATH"] = str(replay)
        main_args = [str(node), str(staged_generator / "apply-pertamina-gld-flow.js"), "--generate-only",
                     "--node-red-user-dir", str(profile), "--mqtt-host", host, "--mqtt-port", str(effective["mqtt"]),
                     "--replay-state-path", str(replay), "--field-test-log-dir", str(work / "field-test-logs"),
                     "--topology-bootstrap-file", str(profile / "pertamina-gld-topology-bootstrap.json"),
                     "--gateway-base-url", str(system["serverEnv"].get("GATEWAY_BASE_URL", "http://0.0.0.0")),
                     "--gateway-status-url", str(system["serverEnv"].get("GATEWAY_STATUS_URL", "http://0.0.0.0/disabled"))]
        if host.lower() not in ("127.0.0.1", "localhost", "::1"): main_args.append("--allow-insecure-mqtt")
        _run(main_args, env)
        csv_path = Path(result["csv"]); csv_path.parent.mkdir(parents=True, exist_ok=True)
        # GenerateOnly does not provision credentials; inject the selected DB
        # password into the resulting copied document, never process argv.
        dataset_args = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(staged_generator / "apply-pertamina-gld-dataset-flow.ps1"), "-GenerateOnly",
                        "-MqttHost", host, "-MqttPort", str(effective["mqtt"]), "-MySqlHost", "127.0.0.1",
                        "-MySqlPort", str(effective["database"]), "-MySqlDatabase", dbconfig["name"],
                        "-MySqlUser", dbconfig["user"], "-CsvPath", csv_path.as_posix()]
        _run(dataset_args, env)
        header_match = re.search(r'^\$csvHeader\s*=\s*"([^"\r\n]+)"',
                                 (staged_generator / "apply-pertamina-gld-dataset-flow.ps1").read_text(encoding="utf-8-sig"), re.M)
        require(header_match is not None, "NODE_RED_DATASET_CSV_HEADER_UNAVAILABLE")
        csv_header = header_match.group(1)
        if csv_path.exists() and csv_path.stat().st_size:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
                require(stream.readline().rstrip("\r\n") == csv_header, "NODE_RED_INCOMING_CSV_SCHEMA_DIFFERS")
        else:
            csv_path.write_text(csv_header + "\r\n", encoding="utf-8", newline="")
        main = _nodes(_json(staged_generator / "pertamina-gld-server.flow.json"))
        dataset = _nodes(_json(staged_generator / "pertamina-gld-dataset.flow.json"))
        for entry in main + dataset:
            if entry.get("type") == "mqtt-broker":
                entry["credentials"] = dict(user=broker["username"], password=broker["password"])
            if entry.get("type") == "MySQLdatabase":
                entry["credentials"] = dict(user=dbconfig["user"], password=dbconfig["password"])
                # mysql2 accepts a UTC offset, rather than an IANA zone name.
                entry["tz"] = "+07:00"
        merged = _nodes(nonproject + main + dataset)
        # Keep Node-RED's palette metadata aligned with the offline modules,
        # without ever editing the original user's package.json.
        package_path=staged_profile / "package.json"
        package=_json(package_path) if package_path.exists() else {"name":"gld-handover-profile","version":"1.0.0"}
        dependencies=package.setdefault("dependencies",{})
        for name in ("node-red-contrib-aedes","node-red-node-mysql"):
            metadata=runtime / "user-node_modules" / name / "package.json"
            if metadata.exists():dependencies[name]=_json(metadata)["version"]
        package_path.write_text(json.dumps(package,indent=2)+"\n",encoding="utf-8")
        staged_flows = stage / flows_path.name
        staged_flows.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        _run([str(node), "--check", str(staged_profile / "settings.js")], env)
        if profile.exists(): profile.rmdir()
        staged_profile.rename(profile); staged_generator.rename(generator); staged_flows.rename(flows_path)
        receipt_path.write_text(json.dumps(dict(schemaVersion=1, fingerprint=fingerprint, ports=effective,
            source="snapshot plus canonical copied generators", nonProjectNodes=len(nonproject), projectNodes=len(main) + len(dataset)), sort_keys=True, indent=2), encoding="utf-8")
    return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def deploy(node_red_url, flows_path, token=""):
    try:
        parsed = urllib.parse.urlsplit(node_red_url)
        require(parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1") and
                not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and
                parsed.path in ("", "/"), "NODE_RED_DEPLOY_REQUIRES_LOCAL_URL")
        desired = _nodes(_json(flows_path)); desired_kept = _nonproject(desired)
        nonproject_ids = {node["id"] for node in desired_kept}
        project = [copy.deepcopy(node) for node in desired if node["id"] not in nonproject_ids]
        require(project, "NODE_RED_PROJECT_FLOW_MISSING")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        headers = {"Node-RED-API-Version": "v2", "Content-Type": "application/json"}
        if token: headers["Authorization"] = "Bearer " + token
        endpoint = node_red_url.rstrip("/") + "/flows"
        with opener.open(urllib.request.Request(endpoint, headers=headers), timeout=30) as response:
            current = json.load(response)
        require(isinstance(current, dict) and current.get("rev") and isinstance(current.get("flows"), list), "NODE_RED_V2_REVISION_REQUIRED")
        kept = _nonproject(_nodes(current["flows"])); merged = _nodes(kept + project)
        payload = json.dumps(dict(rev=current["rev"], flows=merged), ensure_ascii=False).encode("utf-8")
        headers["Node-RED-Deployment-Type"] = "full"
        with opener.open(urllib.request.Request(endpoint, data=payload, headers=headers, method="POST"), timeout=30) as response:
            result = json.load(response)
        return dict(applied=True, apiShape="v2-envelope", projectNodes=len(project), preservedNodes=len(kept),
                    totalNodes=len(merged), revisionReturned=isinstance(result, dict) and bool(result.get("rev")))
    except Exception:
        # Never reflect response/error bodies, bearer tokens, or submitted flows.
        raise archive_util.RuntimeErrorSafe("NODE_RED_DEPLOY_FAILED: inspect local service state before any retry") from None
