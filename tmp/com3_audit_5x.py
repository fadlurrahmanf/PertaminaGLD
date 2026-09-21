import time, json, re, statistics
import serial
from serial import Serial

PORT = 'COM3'
BAUDS = [921600, 115200]
SCENARIOS = [
    {
        'name': 'GET_INFO',
        'cmd': 'GET_INFO',
        'must': ['GLD_INFO_JSON'],
        'done_patterns': ['GLD_INFO_JSON'],
        'note': 'baseline info, version + caps'
    },
    {
        'name': 'GET_STATUS',
        'cmd': 'GET_STATUS',
        'must': ['GLD_STATUS_JSON'],
        'done_patterns': ['GLD_STATUS_JSON'],
        'note': 'runtime telemetry/status snapshot'
    },
    {
        'name': 'RUN_BOOT_CHECK',
        'cmd': 'RUN_BOOT_CHECK',
        'must': ['RUN_BOOT_CHECK_START', 'RUN_BOOT_CHECK_DONE'],
        'done_patterns': ['RUN_BOOT_CHECK_DONE'],
        'note': 'boot diagnostics + non-battery restore power policy'
    },
    {
        'name': 'RUN_CURRENT_STATE_CHECK',
        'cmd': 'RUN_CURRENT_STATE_CHECK',
        'must': ['RUN_CURRENT_STATE_CHECK_START', 'RUN_CURRENT_STATE_CHECK_DONE'],
        'done_patterns': ['RUN_CURRENT_STATE_CHECK_DONE'],
        'note': 'no-change observational diagnostics'
    },
    {
        'name': 'RUN_I2C_SCAN',
        'cmd': 'RUN_I2C_SCAN',
        'must': ['GLD_CMD_ACK_JSON', 'I2C_MANUAL_SCAN'],
        'done_patterns': ['I2C_MANUAL_SCAN'],
        'note': 'global I2C address discovery'
    },
    {
        'name': 'RUN_TCA_CHANNEL_SCAN',
        'cmd': 'RUN_TCA_CHANNEL_SCAN',
        'must': ['TCA_MCP_SCAN', 'TCA_MCP_SCAN restorePcf', 'GLD_CMD_ACK_JSON'],
        'done_patterns': ['GLD_CMD_ACK_JSON', 'TCA_MCP_SCAN restorePcf'],
        'note': 'per-channel MCP scan via TCA + PCF restore'
    },
    {
        'name': 'RUN_ADS_MCP_SWEEP',
        'cmd': 'RUN_ADS_MCP_SWEEP',
        'must': ['ADS_MCP_SWEEP_START', 'ADS_MCP_SWEEP_DONE'],
        'done_patterns': ['ADS_MCP_SWEEP_DONE'],
        'note': 'diagnostic ADS/MCP sweep'
    },
]


def open_serial():
    last_err = None
    for baud in BAUDS:
        try:
            ser = Serial(PORT, baudrate=baud, timeout=0.05)
            # give device time, clear noise
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write(b'\n')
            time.sleep(0.25)
            ser.read_all()
            return ser, baud
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f'Cannot open {PORT}: {last_err}')


def read_line(ser):
    try:
        raw = ser.readline()
    except Exception:
        return ''
    if not raw:
        return ''
    try:
        return raw.decode('utf-8', errors='replace').strip('\r\n')
    except Exception:
        return ''


def run_one(ser, cmd, timeout_s=15, done_markers=None, min_idle=0.2):
    if done_markers is None:
        done_markers = []
    ser.reset_input_buffer()
    ser.write((cmd + '\r\n').encode('ascii', errors='ignore'))
    ser.flush()

    deadline = time.time() + timeout_s
    lines = []
    seen = []
    found = {}

    # capture at least a little so command can start
    while time.time() < deadline:
        line = read_line(ser)
        if not line:
            time.sleep(0.02)
            continue
        lines.append(line)
        # keep latest 300 lines
        if len(lines) > 500:
            lines = lines[-500:]
        for dm in done_markers:
            if dm in line:
                found[dm] = True
        if found.keys() >= {dm for dm in done_markers}:
            # allow tail settle
            t = time.time() + min_idle
            while time.time() < t:
                l2 = read_line(ser)
                if l2:
                    lines.append(l2)
                else:
                    break
            break
    return lines, found


def check_case(scenario, lines):
    text = '\n'.join(lines)
    must = scenario['must']
    missing = [m for m in must if m not in text]
    ack = 'GLD_CMD_ACK_JSON' in text
    status = {
        'ok': len(missing) == 0,
        'missing': missing,
        'has_ack': ack,
        'lines': len(lines),
        'sample': '\n'.join(lines[:3])
    }
    # extra signal extraction
    if scenario['name'] == 'RUN_BOOT_CHECK':
        m = re.findall(r'BOOT_PROBE_MCP_CONTROL=done tested=(\d+) dacReady=(\d+) writeOkCount=(\d+)/(\d+) writeMask=0x([0-9A-Fa-f]+)', text)
        status['mcp_control'] = m[-1] if m else None
        m2 = re.findall(r'GLD_SENSOR_SCAN seq=(\d+)', text)
        status['sensor_scan_rows'] = len(m2)
    if scenario['name'] == 'RUN_TCA_CHANNEL_SCAN':
        status['tca_scan_rows'] = text.count('TCA_MCP_SCAN')
        status['restore_row'] = 'TCA_MCP_SCAN restorePcf=' in text
    if scenario['name'] == 'RUN_I2C_SCAN':
        # capture address summary if available
        m = re.findall(r'I2C_MANUAL_SCAN range=([^\n]+)', text)
        status['scan_summary'] = m[-1] if m else None
    if scenario['name'] == 'RUN_ADS_MCP_SWEEP':
        status['sweep_ok_lines'] = [ln for ln in lines if 'ADS_MCP_SWEEP_' in ln][:5]
    if scenario['name'] == 'GET_STATUS':
        m = re.findall(r'"alarmControlMode":"(.*?)"', text)
        status['alarmControlMode'] = m[-1] if m else None
    return status


def run_suite(rep=5):
    ser, baud = open_serial()
    print(f'CONNECTED port={PORT} baud={baud}')
    results = {}
    for s in SCENARIOS:
        scenario = dict(s)
        stats = []
        print(f"\n--- {scenario['name']} ({scenario['cmd']}) x{rep} ---")
        for i in range(1, rep+1):
            lines, found = run_one(ser, scenario['cmd'], timeout_s=18, done_markers=scenario['done_patterns'])
            status = check_case(scenario, lines)
            status['iter'] = i
            status['found_patterns'] = {k: bool(v) for k, v in found.items()}
            status['raw_tail'] = lines[-5:]
            if status['ok']:
                mark = 'OK'
            else:
                mark = 'FAIL'
            stats.append(status)
            print(f"iter {i}: {mark} missing={status['missing']} lines={status['lines']} ack={status['has_ack']}")
            if status['missing']:
                print('  detail missing:', ', '.join(status['missing']))
                if status['raw_tail']:
                    print('  tail:', status['raw_tail'][-1])
            time.sleep(0.5)
        ok_count = sum(1 for x in stats if x['ok'])
        results[scenario['name']] = {
            'ok_count': ok_count,
            'total': rep,
            'freq': ok_count/rep,
            'always': ok_count == rep,
            'iterations': stats,
            'note': scenario['note'],
            'command': scenario['cmd'],
            'done': scenario['done_patterns'],
            'must': scenario['must'],
        }
    ser.close()

    print('\n=== SUMMARY ===')
    for name, r in results.items():
        status = 'ALWAYS' if r['always'] else ('SOMETIMES' if r['ok_count'] > 0 else 'NEVER')
        print(f"{name}: {r['ok_count']}/{r['total']} -> {status}")
    return results


if __name__ == '__main__':
    results = run_suite(5)
    # persist evidence
    with open('tmp/com3_audit_results_gl2_5x.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print('\nSaved results to tmp/com3_audit_results_gl2_5x.json')
