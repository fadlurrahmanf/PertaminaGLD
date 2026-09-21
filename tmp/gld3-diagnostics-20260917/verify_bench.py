"""Evaluate recorded GLD3 bench evidence without treating it as gas calibration."""
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent

def log(name):
    return (ROOT / name).read_text(encoding='utf-8', errors='replace')

def messages(text, marker):
    return [json.loads(line.split(marker + ' ', 1)[1])
            for line in text.splitlines() if marker + ' {' in line]

def fields(text, marker):
    return [dict(re.findall(r'(\w+)=([^\s]+)', line.split(marker, 1)[1]))
            for line in text.splitlines() if marker in line and '>>> ' not in line]

before_info = messages(log('before-status.log'), 'GLD_INFO_JSON')[-1]
after_info = messages(log('final-status.log'), 'GLD_INFO_JSON')[-1]
status = messages(log('final-status.log'), 'GLD_STATUS_JSON')[-1]
sweep_text = log('sweep-twice.log')
rows = fields(sweep_text, 'ADS_MCP_SWEEP_RESULT ')
details = fields(sweep_text, 'ADS_MCP_SWEEP_DETAIL ')
channel_restores = fields(sweep_text, 'ADS_MCP_SWEEP_RESTORE_CHANNEL ')
assert len(details) == len(channel_restores), 'Missing restore-channel evidence'
for detail, restore in zip(details, channel_restores):
    assert detail['ch'] == restore['ch']
    detail.update(restore)
done = fields(sweep_text, 'ADS_MCP_SWEEP_DONE ')
restores = fields(sweep_text, 'ADS_MCP_SWEEP_RESTORE ')
observed = fields(log('observation.log'), 'RUN_CURRENT_STATE_CHECK_SCOPE=')
guard_text = log('guard-and-restart.log')
boot = fields(guard_text, 'GLD3_BOOT_MCP_CONTROL ')
checks = {
    'new_version': after_info['firmwareVersion'] == '0.8.31' and after_info['boardProfile'].startswith('GLD3'),
    'identity_config_preserved': all(before_info[k] == after_info[k] for k in
                                    ('deviceId', 'nodeId', 'targetChId', 'appConfig', 'starLora', 'security')),
    'two_complete_sweeps': len(rows) == len(details) == 16 and len(done) == 2,
    'sweep_status_truthful_pass': all(x.get('status') == 'pass' and x.get('executionPassCount') == '8/8'
                                    and x.get('analogResponse') == 'not_graded' for x in done),
    'every_row_passes': all(x.get('ok') == '1' for x in rows),
    'all_dac_readbacks_restore': all(all(x.get(k) == '1' for k in
                                        ('baselineRead', 'match0', 'match4000', 'restoreMatch'))
                                   and x.get('persistentWrite') == '0' for x in details),
    # A gross electrical-response check for this bench, not a calibration spec.
    'bench_abs_delta_over_50mV': all(math.isfinite(float(x['delta'])) and abs(float(x['delta'])) > 0.05 for x in rows),
    'power_mask_readback_restored': len(restores) == 2 and all(x.get('originalPcf') == x.get('finalPcf') == '0xFF'
                                                            and x.get('finalRead') == x.get('restoreMatch') == '1'
                                                            for x in restores),
    'isolated_baselines_repeat': len(details) == 16 and [x['baseline'] for x in details[:8]] == [x['baseline'] for x in details[8:]],
    'no_reset_during_sweeps': 'BOOT_PROBE_' not in sweep_text and 'rst:0x' not in sweep_text,
    'observational_scan_labelled': 'isolatedFunctional=not_tested' in log('observation.log')
                                   and 'authoritativeBootMcp=8/8' in log('observation.log'),
    'manual_override_guard': 'ADS_MCP_SWEEP_DONE status=blocked reason=active_session_mcp_override' in guard_text,
    'final_boot_control': len(boot) == 8 and all(all(x.get(k) == '1' for k in
                                                  ('baselineRead', 'lowMatch', 'highMatch', 'restoreMatch')) for x in boot),
    'final_adc_sht_power_ok': status['telemetry']['valid'] and status['telemetry']['sensorStatus'] == [0] * 8
                            and status['environment']['valid'] and status['sensorPower']['outputMask'] == 255,
    'calibration_still_unclaimed': status['model']['activeNullingProfileId'] == 0
                                 and not status['model']['inferenceValid'],
    'alarm_auto_off': status['alarmControl']['mode'] == 'auto' and not status['alarmControl']['physicalCommanded'],
}
report = {'allChecksPass': all(checks.values()), 'checks': checks,
          'sweepRows': rows, 'sweepReadbacks': details, 'sweepSummary': done,
          'finalVersion': after_info['firmwareVersion'], 'finalAdcVoltage': status['telemetry']['sensorVoltage'],
          'notProven': ['gas calibration/accuracy', 'RF end-to-end', 'RS485 external master', 'physical fan/alarm operation',
                        'physical root cause of all-on MCP scan dependence']}
(ROOT / 'bench-verdict.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'allChecksPass': report['allChecksPass'], 'checks': checks}, indent=2))
raise SystemExit(not report['allChecksPass'])
