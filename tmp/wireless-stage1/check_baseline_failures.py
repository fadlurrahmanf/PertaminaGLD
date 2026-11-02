"""Reproduce only observed old failures with HEAD inputs, without stash/checkouts."""
import importlib.util
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def baseline(path):
    return subprocess.check_output(['git', 'show', 'HEAD:' + path], cwd=ROOT, text=True, encoding='utf-8')

ini = baseline('firmware/platformio.ini')
ini_path = OUT / 'baseline-platformio.ini'
ini_path.write_text(ini, encoding='utf-8')
fast = load('baseline_fast_test', 'firmware/gld/tests/test_nulling_fast_scope.py')
fast.PLATFORMIO = ini_path
stability = load('baseline_stability_test', 'firmware/gld/tests/test_nulling_stability_scope.py')
stability.INI = ini
alarm = load('baseline_alarm_test', 'apps/operator-hub/tests/test_gld_alarm_controls.py')
mock_path = OUT / 'baseline-mock.js'
mock_path.write_text(baseline('apps/gld-operator/js/mock.js'), encoding='utf-8')
extractor = alarm.js_function
alarm.js_function = lambda path, name: extractor(mock_path if path.name == 'mock.js' else path, name)
suite = unittest.TestSuite([
    fast.FastNullingScopeTests('test_fast_flag_is_specific_to_model_one'),
    stability.NullingStabilityScopeTests('test_guard_specific_to_fast_model_one'),
    alarm.AlarmUiContractTests('test_mock_pullup_levels_follow_auto_and_manual_commands'),
])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if len(result.failures) != 2 or len(result.errors) != 1:
    raise SystemExit('Unexpected baseline result')
print('CONFIRMED: identical 2 nulling assertions + 1 mock helper error already occur with HEAD inputs.')
