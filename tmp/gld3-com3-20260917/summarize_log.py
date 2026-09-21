import json
import pathlib
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
for filename in sys.argv[1:]:
    print('LOG', filename)
    lines = pathlib.Path(filename).read_text(encoding='utf-8', errors='replace').splitlines()
    for prefix in ('GLD_INFO_JSON', 'GLD_STATUS_JSON', 'GLD_TELEMETRY_JSON'):
        matching = [x for x in lines if prefix in x and '{' in x]
        if not matching:
            continue
        try:
            d = json.loads(matching[-1].split('{', 1)[1].join(['{', '']))
        except (ValueError, IndexError):
            print(prefix, 'unparseable')
            continue
        if prefix == 'GLD_INFO_JSON':
            keys = ('deviceId','boardProfile','firmwareVersion','protocolVersion','sensorCount','modbus','pcf8574','model')
        elif prefix == 'GLD_STATUS_JSON':
            keys = ('deviceId','targetChId','mode','uptimeMs','power','bootHealth','model','lora','environment','pcf8574','sensorPower','alarmControl','nulling','modbus','telemetry','runtimeMcpCode','runtimeMcpReadback','runtimeMcpVerified','recovery')
        else:
            keys = tuple(d)
        print(prefix, json.dumps({k:d[k] for k in keys if k in d}, ensure_ascii=False))
    special = [x for x in lines if any(k in x for k in ('GLD_CMD_ACK','I2C_MANUAL_SCAN','TCA_MCP_SCAN','RUN_CURRENT_STATE_CHECK_','ADS_MCP_SWEEP_','BOOT_IC','BOOT_CHECK','BROWNOUT','Brownout','Guru Meditation','rst:'))]
    print('\n'.join(special[-90:]))
