"""Collect isolated build evidence, never read private credential contents."""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'firmware/.pio/artifacts/gld-dataset-wifi-20261102'
BOOT_APP = Path('C:/Users/MSI/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    records = []
    for model in (1, 2, 3):
        env = f'gld_model_{model}_dataset_wifi'
        build = ROOT / f'firmware/.pio/build-wireless-stage1-model{model}' / env
        log_path = ROOT / f'tmp/wireless-stage1/compile-model{model}.log'
        log = log_path.read_text(encoding='utf-8', errors='replace')
        if not re.search(r'\[SUCCESS\]|\bSUCCESS\s+\d', log):
            raise RuntimeError(f'{env} has no successful build evidence')
        if f'gld\\models\\model_{model}\\model_data.cpp.o' not in log:
            raise RuntimeError(f'{env} model object not confirmed')
        target = DEST / env
        target.mkdir(parents=True, exist_ok=True)
        files = []
        for name, source, offset in (
            ('bootloader.bin', build / 'bootloader.bin', '0x0000'),
            ('partitions.bin', build / 'partitions.bin', '0x8000'),
            ('boot_app0.bin', BOOT_APP, '0xE000'),
            ('firmware.bin', build / 'firmware.bin', '0x10000'),
        ):
            if not source.is_file():
                raise RuntimeError(f'Missing build artifact: {source}')
            out = target / name
            shutil.copy2(source, out)
            actual = digest(out)
            if actual != digest(source):
                raise RuntimeError('Artifact copy hash mismatch')
            files.append(dict(name=name, offset=offset, bytes=out.stat().st_size, sha256=actual))
        stats = [line.strip() for line in log.splitlines() if line.strip().startswith(('RAM:', 'Flash:'))]
        source_files = [
            'firmware/platformio.ini', 'firmware/gld/src/GldUnifiedMain.cpp',
            'firmware/gld/src/GldDatasetWifi.cpp', 'firmware/gld/include/GldDatasetWifi.h',
            'firmware/tools/prepare_dataset_wifi.py',
            f'firmware/gld/models/model_{model}/NeuralNetwork.cpp',
            f'firmware/gld/models/model_{model}/model_data.cpp',
            f'firmware/gld/models/model_{model}/ModelMetadata.h',
        ]
        record = dict(environment=env, model=model, build=str(build), artifacts=str(target), files=files, usage=stats,
                      sourceSha256={path: digest(ROOT / path) for path in source_files},
                      credentialFile=f'firmware/.pio/gld-dataset-wifi/{env}/credentials.local.json',
                      evidence='compiled only; no upload or hardware proof')
        records.append(record)
        (target / 'build-evidence.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    (DEST / 'build-summary.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    for record in records:
        firmware = next(f for f in record['files'] if f['name'] == 'firmware.bin')
        print(json.dumps(dict(environment=record['environment'], bytes=firmware['bytes'], sha256=firmware['sha256'], usage=record['usage'], artifacts=record['artifacts'])))

if __name__ == '__main__':
    main()
