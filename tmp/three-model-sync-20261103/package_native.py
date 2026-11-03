"""Validate only the new native-feature builds using the existing strict packager."""
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    'strict_native_feature_package', ROOT / 'firmware/tools/package_dataset_workflow.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ARTIFACT_ROOT = ROOT / 'firmware/.pio/artifacts/gld-dataset-workflow-wifi-20261103-feature-parity'
module.RECEIPT_ROOT = HERE
module.RECEIPTS = {model: f'model{model}-build-receipt.json' for model in (1, 2, 3)}

strict_package = module.package


def package_with_native_capability(model, modules, core, snapshot, install):
    module.require(not install, 'Use coordinator-reviewed directory deployment after all offline checks')
    result = strict_package(model, modules, core, snapshot, False)
    env = result['environment']
    artifact = module.ARTIFACT_ROOT / env
    manifest_path = artifact / 'manifest.json'
    manifest = module.read(manifest_path)
    manifest['capabilities'] = {'nativeSerial': True, 'datasetWifi': True}
    module.dump(manifest_path, manifest)
    (artifact / 'manifest.sha256').write_text(
        f"{module.sha(manifest_path)}  manifest.json\n", encoding='ascii')
    encoded = {name: module.base64.b64encode((artifact/name).read_bytes()).decode('ascii')
               for name, _ in module.FILES}
    _, uploader, preflight, hub = modules
    _, verified = uploader.validate_firmware_package(manifest, encoded, env, '1002')
    module.require(len(verified) == 4, 'Capability-stamped child validation failed')
    preflight._verify_manifest(manifest_path, env)
    hub.validate_selected_package({'manifest': manifest, 'packageFiles': encoded}, env)
    result.update(manifestSha256=module.sha(manifest_path), nativeSerial=True,
                  capabilityStampedValidators='PASS')
    module.dump(artifact/'offline-package-validation.json', result)
    receipt = module.read(module.RECEIPT_ROOT/module.RECEIPTS[model])
    module.private_verification(env, Path(receipt['buildDirectory']),
        (artifact/'firmware.bin').read_bytes(),
        list(artifact.glob('*.json'))+list(artifact.glob('*.sha256')))
    return result


module.package = package_with_native_capability

if __name__ == '__main__':
    raise SystemExit(module.main())
