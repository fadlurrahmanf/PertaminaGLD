#!/usr/bin/env python3
"""Compatibility wrapper for the canonical GLD Dataset Node-RED flow generator.

The dataset flow definition lives in apply-pertamina-gld-dataset-flow.ps1 so the
repo has only one source of truth for the Node-RED tab and checked-in snapshot.
This wrapper preserves the older `python server/nodered/deploy-dataset-flow.py`
operator command by forwarding equivalent arguments to the PowerShell script.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy or generate the GLD Dataset Server Node-RED flow.")
    parser.add_argument("--node-red-url", default="http://127.0.0.1:1880")
    parser.add_argument("--mqtt-host", default="CHANGE_ME_MQTT_HOST")
    parser.add_argument("--mqtt-port", default="1884")
    parser.add_argument("--mqtt-user", default="")
    parser.add_argument("--mqtt-password", default="")
    parser.add_argument("--mysql-host", default="localhost")
    parser.add_argument("--mysql-port", default="3306")
    parser.add_argument("--mysql-database", default="pertamina_gld")
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--mysql-password", default="")
    parser.add_argument("--csv-path", default=r"C:\Users\asus\gld-dataset.csv")
    parser.add_argument("--device-id", default="F001")
    parser.add_argument("--generate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script = Path(__file__).with_name("apply-pertamina-gld-dataset-flow.ps1")
    command = [
        "powershell",
        "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-NodeRedUrl", args.node_red_url,
        "-MqttHost", args.mqtt_host,
        "-MqttPort", str(args.mqtt_port),
        "-MySqlHost", args.mysql_host,
        "-MySqlPort", str(args.mysql_port),
        "-MySqlDatabase", args.mysql_database,
        "-MySqlUser", args.mysql_user,
        "-CsvPath", args.csv_path,
        "-DeviceId", args.device_id,
    ]
    if args.mqtt_user:
        command.extend(["-MqttUser", args.mqtt_user])
    if args.mqtt_password:
        command.extend(["-MqttPassword", args.mqtt_password])
    if args.mysql_password:
        command.extend(["-MySqlPassword", args.mysql_password])
    if args.generate_only:
        command.append("-GenerateOnly")

    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())
