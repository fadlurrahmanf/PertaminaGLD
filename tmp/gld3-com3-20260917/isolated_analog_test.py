"""Bounded volatile per-rail DAC/ADC test with cleanup; no calibration writes."""
import datetime
import json
import math
import pathlib
import re
import sys
import time

import serial

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = pathlib.Path(__file__).resolve().parent
direct = '--direct' in sys.argv
prefix = 'isolated-direct' if direct else 'isolated-analog'
rows = []
latest = {}
acks = {}
buffer = bytearray()
link = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=2)
link.dtr = False
link.rts = False
link.port = 'COM3'
active_channel = None
cleanup_errors = []

with (root / (prefix + '.log')).open('a', encoding='utf-8') as log:
    def record(line):
        line = re.sub(r'(?i)("(?:password|wifiPassword|mqttPassword|aesKey|keyHex|token|secret)"\s*:\s*")[^"]*', r'\1<redacted>', line)
        log.write(datetime.datetime.now().isoformat(timespec='milliseconds') + ' ' + line + '\n')
        log.flush()

    def read_for(seconds, predicate=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            data = link.read(link.in_waiting or 1)
            buffer.extend(data)
            while b'\n' in buffer:
                raw, _, rest = buffer.partition(b'\n')
                buffer[:] = rest
                line = raw.decode('utf-8', errors='replace').rstrip('\r')
                record(line)
                if line.startswith('ADS_MCP_SWEEP_RESULT '):
                    fields = dict(re.findall(r'(\w+)=(\S+)', line))
                    latest.setdefault('sweep_results', {})[int(fields['ch'])] = fields
                elif line.startswith('ADS_MCP_SWEEP_DETAIL '):
                    fields = dict(re.findall(r'(\w+)=(\S+)', line))
                    latest.setdefault('sweep_details', {})[int(fields['ch'])] = fields
                elif line.startswith('ADS_MCP_SWEEP_DONE '):
                    latest['sweep_done'] = line
                for kind in ('GLD_CMD_ACK_JSON', 'GLD_STATUS_JSON', 'GLD_TELEMETRY_JSON'):
                    if line.startswith(kind + ' '):
                        try:
                            obj = json.loads(line.split(' ', 1)[1])
                            latest[kind] = obj
                            if kind == 'GLD_CMD_ACK_JSON':
                                acks[obj['cmd']] = obj
                        except (ValueError, KeyError):
                            pass
            if predicate and predicate():
                return True
        return not predicate or predicate()

    def send(command, ack_name=None):
        if ack_name:
            acks.pop(ack_name, None)
        record('>>> ' + command)
        link.write((command + '\n').encode())
        link.flush()
        if not ack_name:
            return None
        if not read_for(7, lambda: ack_name in acks):
            raise RuntimeError('ACK timeout: ' + ack_name)
        ack = acks[ack_name]
        if ack.get('status') != 'ok':
            raise RuntimeError('Command rejected: ' + json.dumps(ack))
        read_for(0.65)
        return ack

    def power(enabled, channel=None):
        payload = {'enabled': enabled, 'all': True} if channel is None else {'enabled': enabled, 'channel': channel}
        send('SET_SENSOR_POWER_JSON ' + json.dumps(payload), 'SET_SENSOR_POWER')

    def code(channel, value):
        return send('SET_SESSION_MCP_JSON ' + json.dumps({'channel': channel, 'code': value}), 'SET_SESSION_MCP')

    def sample_after(ack_uptime):
        read_for(1.3)
        latest.pop('GLD_TELEMETRY_JSON', None)
        send('GET_TELEMETRY')
        if not read_for(7, lambda: 'GLD_TELEMETRY_JSON' in latest):
            raise RuntimeError('Telemetry timeout')
        obj = latest['GLD_TELEMETRY_JSON']
        if obj['telemetry']['sampleMs'] <= ack_uptime:
            raise RuntimeError('Stale telemetry sample')
        return obj

    try:
        link.open()
        read_for(0.5)
        power(False)
        for ch in range(8):
            active_channel = ch
            power(True, ch)
            if direct:
                code(ch, 0)
                for key in ('sweep_done', 'sweep_results', 'sweep_details'):
                    latest.pop(key, None)
                send('RUN_ADS_MCP_SWEEP', 'RUN_ADS_MCP_SWEEP')
                if not read_for(30, lambda: 'sweep_done' in latest):
                    raise RuntimeError('Direct sweep timeout')
                result = latest.get('sweep_results', {}).get(ch)
                detail = latest.get('sweep_details', {}).get(ch)
                if result is None or detail is None:
                    raise RuntimeError('Missing target sweep evidence')
                restore_ack = code(ch, 0)
                row = {'method': 'direct_adc_single_rail_target_row_only', 'channel': ch, 'result': result, 'detail': detail, 'restoreZeroAck': restore_ack['status']}
                rows.append(row)
                print(json.dumps(row), flush=True)
                power(False, ch)
                active_channel = None
                (root / (prefix + '-results.json')).write_text(json.dumps(rows, indent=2), encoding='utf-8')
                continue
            low_ack = code(ch, 0)
            low = sample_after(low_ack['uptimeMs'])
            high_ack = code(ch, 4000)
            high = sample_after(high_ack['uptimeMs'])
            restore_ack = code(ch, 0)
            lo = low['telemetry']['sensorVoltage'][ch]
            hi = high['telemetry']['sensorVoltage'][ch]
            en_bit = [0, 6, 7, 3, 4, 5, 2, 1][ch]
            mask_ok = all(x['sensorPower']['outputMask'] == 1 << en_bit for x in (low, high))
            states = [x['telemetry']['sensorStatus'][ch] for x in (low, high)]
            row = {'method': 'cached_moving_average_preliminary_only', 'channel': ch, 'sensor': low['telemetry']['featureOrder'][ch], 'v0': lo, 'v4000': hi, 'delta': hi-lo, 'adcStatus': states, 'singleRailMaskOk': mask_ok, 'writeLowAck': low_ack['status'], 'writeHighAck': high_ack['status'], 'restoreZeroAck': restore_ack['status'], 'sampleMs': [low['telemetry']['sampleMs'], high['telemetry']['sampleMs']], 'finite': math.isfinite(lo) and math.isfinite(hi)}
            rows.append(row)
            print(json.dumps(row), flush=True)
            power(False, ch)
            active_channel = None
            (root / (prefix + '-results.json')).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    finally:
        if link.is_open:
            if active_channel is not None:
                try:
                    code(active_channel, 0)
                except Exception as exc:
                    cleanup_errors.append('zero: ' + str(exc))
            try:
                power(True)
                send('SET_ALARM_MODE_JSON {"mode":"auto"}', 'SET_ALARM_MODE')
                send('GET_STATUS')
                read_for(2)
            except Exception as exc:
                cleanup_errors.append('power/auto: ' + str(exc))
            link.close()
        (root / (prefix + '-results.json')).write_text(json.dumps(rows, indent=2), encoding='utf-8')
        print('CLEANUP', json.dumps({'errors': cleanup_errors, 'completedChannels': len(rows)}), flush=True)
        if cleanup_errors:
            raise RuntimeError('; '.join(cleanup_errors))
