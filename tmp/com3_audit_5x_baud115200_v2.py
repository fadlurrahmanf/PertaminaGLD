import json
import time
import serial

PORT='COM3'
BAUD=115200
REPEAT=5
TIMEOUT=12

SCENARIOS=[
    ('GET_INFO','GET_INFO',['GLD_INFO_JSON'],['GLD_INFO_JSON'], 'baseline info/caps'),
    ('GET_STATUS','GET_STATUS',['GLD_STATUS_JSON'],['GLD_STATUS_JSON'],'runtime status'),
    ('RUN_BOOT_CHECK','RUN_BOOT_CHECK',['RUN_BOOT_CHECK_START','RUN_BOOT_CHECK_DONE'],['RUN_BOOT_CHECK_DONE'],'boot diagnostics'),
    ('RUN_CURRENT_STATE_CHECK','RUN_CURRENT_STATE_CHECK',['RUN_CURRENT_STATE_CHECK_START','RUN_CURRENT_STATE_CHECK_DONE'],['RUN_CURRENT_STATE_CHECK_DONE'],'state check'),
    ('RUN_I2C_SCAN','RUN_I2C_SCAN',['GLD_CMD_ACK_JSON','I2C_MANUAL_SCAN'],['I2C_MANUAL_SCAN'],'i2c full scan'),
    ('RUN_TCA_CHANNEL_SCAN','RUN_TCA_CHANNEL_SCAN',['GLD_CMD_ACK_JSON','TCA_MCP_SCAN'],['TCA_MCP_SCAN restorePcf'],'per TCA channel scan'),
    ('RUN_ADS_MCP_SWEEP','RUN_ADS_MCP_SWEEP',['ADS_MCP_SWEEP_START','ADS_MCP_SWEEP_DONE'],['ADS_MCP_SWEEP_DONE'],'ADS/MCP sweep'),
]


def decode_line(raw):
    return raw.decode('utf-8','replace').strip('\r\n')


def run_once(ser,cmd,done_markers,timeout=TIMEOUT):
    ser.reset_input_buffer(); ser.reset_output_buffer()
    ser.write((cmd+'\r\n').encode('ascii'))
    ser.flush()

    found={k:False for k in done_markers}
    lines=[]
    deadline=time.time()+timeout
    while time.time()<deadline:
        raw=ser.readline()
        if not raw:
            continue
        line=decode_line(raw)
        if not line:
            continue
        lines.append(line)
        for k in done_markers:
            if k in line:
                found[k]=True
        if all(found.values()):
            break
    return lines,found

def run_scenario(ser,name,cmd,must_markers,done_markers):
    rows=[]
    print(f"\n=== {name} ({cmd}) ===")
    for i in range(1,REPEAT+1):
        lines,found=run_once(ser,cmd,done_markers)
        text='\n'.join(lines)
        missing=[m for m in must_markers if m not in text]
        ok=(len(missing)==0)
        print(f"iter {i}: {'OK' if ok else 'FAIL'}|lines={len(lines)}|missing={missing}")
        if missing:
            if lines:
                print(f"  last: {lines[-1]}")
        rows.append({'iter':i,'ok':ok,'line_count':len(lines),'missing':missing,'tail':lines[-1:]})
        time.sleep(0.8)
    ok_count=sum(1 for r in rows if r['ok'])
    print(f"result {name}: {ok_count}/{REPEAT}")
    return {'name':name,'ok_count':ok_count,'rows':rows}


def main():
    with serial.Serial(PORT, BAUD, timeout=0.2) as ser:
        # warmup read
        ser.write(b'\r\n')
        time.sleep(0.2)
        ser.read_all()
        all_results={}
        for name,cmd,must,done,note in SCENARIOS:
            all_results[name]=run_scenario(ser,name,cmd,must,done)
            all_results[name]['must']=must
            all_results[name]['done']=done
            all_results[name]['note']=note

    out={k:{'ok_count':v['ok_count'],'always':v['ok_count']==REPEAT,'frequency':v['ok_count']/REPEAT,'rows':v['rows'],'must':v['must'],'done':v['done'],'note':v['note']} for k,v in all_results.items()}
    with open('tmp/com3_audit_results_gl2_5x_baud115200_v2.json','w',encoding='utf-8') as f:
        json.dump(out,f,indent=2)
    print('\n--- SUMMARY ---')
    for k,v in out.items():
        print(k, f"{v['ok_count']}/5", 'ALWAYS' if v['always'] else ('SOMETIMES' if v['ok_count']>0 else 'NEVER'))
    print('saved tmp/com3_audit_results_gl2_5x_baud115200_v2.json')

if __name__ == '__main__':
    main()
