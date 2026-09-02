import time
import json
import serial
from statistics import mean

PORT='COM3'
BAUD=115200

SCENARIOS=[
    {
        'name':'GET_INFO','cmd':'GET_INFO',
        'must':['GLD_INFO_JSON'],
        'done':['GLD_INFO_JSON'],
        'note':'baseline info version/capabilities'
    },
    {
        'name':'GET_STATUS','cmd':'GET_STATUS',
        'must':['GLD_STATUS_JSON'],
        'done':['GLD_STATUS_JSON'],
        'note':'runtime snapshot'
    },
    {
        'name':'RUN_BOOT_CHECK','cmd':'RUN_BOOT_CHECK',
        'must':['RUN_BOOT_CHECK_START','RUN_BOOT_CHECK_DONE'],
        'done':['RUN_BOOT_CHECK_DONE'],
        'note':'boot diagnostics/recovery, non-battery power restore'
    },
    {
        'name':'RUN_CURRENT_STATE_CHECK','cmd':'RUN_CURRENT_STATE_CHECK',
        'must':['RUN_CURRENT_STATE_CHECK_START','RUN_CURRENT_STATE_CHECK_DONE'],
        'done':['RUN_CURRENT_STATE_CHECK_DONE'],
        'note':'observational state check'
    },
    {
        'name':'RUN_I2C_SCAN','cmd':'RUN_I2C_SCAN',
        'must':['GLD_CMD_ACK_JSON','I2C_MANUAL_SCAN'],
        'done':['I2C_MANUAL_SCAN'],
        'note':'global i2c scan'
    },
    {
        'name':'RUN_TCA_CHANNEL_SCAN','cmd':'RUN_TCA_CHANNEL_SCAN',
        'must':['GLD_CMD_ACK_JSON','TCA_MCP_SCAN'],
        'done':['TCA_MCP_SCAN restorePcf'],
        'note':'scan MCP on all TCA channels'
    },
    {
        'name':'RUN_ADS_MCP_SWEEP','cmd':'RUN_ADS_MCP_SWEEP',
        'must':['ADS_MCP_SWEEP_START','ADS_MCP_SWEEP_DONE'],
        'done':['ADS_MCP_SWEEP_DONE'],
        'note':'ADS+MCP sweep diag'
    },
]

def open_serial():
    return serial.Serial(PORT, BAUD, timeout=0.05)


def to_text(raw):
    return raw.decode('utf-8', errors='replace')


def read_lines(ser, timeout_s, done_markers):
    deadline=time.time()+timeout_s
    lines=[]
    found={m:False for m in done_markers}
    while time.time()<deadline:
        chunk=ser.read(1024)
        if not chunk:
            continue
        text=to_text(chunk)
        # split lines while keeping final fragment too
        for line in text.splitlines():
            if line:
                lines.append(line)
        full='\n'.join(lines)
        for m in done_markers:
            if m in full:
                found[m]=True
        if all(found.values()):
            # allow short settle then stop
            settle=time.time()+0.2
            while time.time()<settle:
                extra=ser.read(1024)
                if not extra:
                    continue
                etext=to_text(extra)
                for line in etext.splitlines():
                    if line:
                        lines.append(line)
                full='\n'.join(lines)
            break
    return lines, found


def run_once(ser, cmd, scenario, timeout_s=20):
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write((cmd+'\r\n').encode('ascii'))
    ser.flush()
    lines, done_hits=read_lines(ser, timeout_s, scenario['done'])
    text='\n'.join(lines)
    missing=[m for m in scenario['must'] if m not in text]
    status={
        'ok': len(missing)==0,
        'missing': missing,
        'line_count': len(lines),
        'done_hits': done_hits,
    }
    if scenario['name']=='RUN_I2C_SCAN':
        # extract address summary if present
        for ln in lines:
            if 'I2C_MANUAL_SCAN' in ln:
                status['scan_summary']=ln.strip()
    if scenario['name']=='RUN_TCA_CHANNEL_SCAN':
        status['tca_scan_rows']=sum(1 for ln in lines if 'TCA_MCP_SCAN' in ln)
        status['restore_rows']=sum(1 for ln in lines if 'restorePcf=' in ln)
    if scenario['name']=='RUN_BOOT_CHECK':
        for ln in lines:
            if 'RUN_BOOT_CHECK_START' in ln:
                status['boot_start']=ln.strip()
            if 'BOOT_PROBE_MCP_CONTROL=' in ln:
                status['boot_control']=ln.strip()
    if scenario['name']=='RUN_ADS_MCP_SWEEP':
        status['sweep_rows']=[ln for ln in lines if 'ADS_MCP_SWEEP_' in ln]
    return status


def run_suite(rep=5):
    ser=open_serial()
    summary={}
    for s in SCENARIOS:
        print(f"\n--- {s['name']} x{rep} ---")
        iters=[]
        for i in range(1,rep+1):
            st=run_once(ser,s['cmd'],s,timeout_s=30)
            st['iter']=i
            st['must']=s['must']
            print(f"iter {i}: {'OK' if st['ok'] else 'FAIL'} line_count={st['line_count']} missing={st['missing']}")
            iters.append(st)
            time.sleep(0.8)
        ok=sum(1 for x in iters if x['ok'])
        summary[s['name']]= {
            'ok_count': ok,
            'total': rep,
            'always': ok==rep,
            'note': s['note'],
            'command': s['cmd'],
            'iterations': iters,
            'command_done': s['done'],
            'command_must': s['must'],
            'raw_tail': iters[-1] if iters else None,
        }
        print(f"=> {s['name']}: {ok}/{rep} {'ALWAYS' if ok==rep else 'SOMETIMES' if ok>0 else 'NEVER'}")
    ser.close()
    with open('tmp/com3_audit_results_gl2_5x_baud115200.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    out=run_suite(5)
    print('\n=== SUMMARY ===')
    for k,v in out.items():
        print(k, v['ok_count'], '/', v['total'])
    print('WROTE tmp/com3_audit_results_gl2_5x_baud115200.json')
