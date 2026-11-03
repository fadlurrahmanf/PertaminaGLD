"""Only temporary credential fixtures; never reads production private files."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = {f'gld_model_{model}_dataset_workflow_wifi' for model in (1, 2, 3)}


class WorkflowCredentials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('workflow_fixture_preparer', ROOT / 'firmware/tools/prepare_dataset_workflow_wifi.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def data(self, env, password='Fixture_123', protocol='gld-dataset-wifi/3'):
        return dict(environment=env, username='gld', password=password, protocol=protocol,
                    address='192.168.4.1', port=81, path='/dataset')

    def write(self, project, env, data, directory='gld-dataset-workflow-wifi'):
        path = project / '.pio' / directory / env / 'credentials.local.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def prepare(self, project, env):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = self.module.prepare(project, project / 'build' / env, env)
        self.assertEqual(output.getvalue(), '', 'Credential preparer must not log private values')
        return result

    def test_exact_three_environments(self):
        self.assertEqual(set(self.module.ENVIRONMENTS), ENVIRONMENTS)

    def test_existing_own_credential_stable_and_own_header_only(self):
        for env in sorted(ENVIRONMENTS):
            with self.subTest(env=env), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                path = self.write(project, env, self.data(env))
                before = path.read_bytes()
                include = self.prepare(project, env)
                self.assertEqual(include.name, 'private-dataset-workflow-wifi')
                self.assertEqual(path.read_bytes(), before)
                header = include / 'GldDatasetWorkflowWifiSecrets.h'
                self.assertIn(json.dumps('Fixture_123'), header.read_text())
                self.prepare(project, env)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((project / '.pio/gld-dataset-replay-wifi').exists())

    def test_missing_own_clones_matching_replay_without_changing_source(self):
        for model in (1, 2, 3):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                env = f'gld_model_{model}_dataset_workflow_wifi'
                replay = f'gld_model_{model}_dataset_replay_wifi'
                source = self.write(project, replay, self.data(replay, protocol='gld-dataset-wifi/2'), 'gld-dataset-replay-wifi')
                before = source.read_bytes()
                self.prepare(project, env)
                target = project / '.pio/gld-dataset-workflow-wifi' / env / 'credentials.local.json'
                result = json.loads(target.read_text())
                self.assertEqual(result['protocol'], 'gld-dataset-wifi/3')
                self.assertEqual(result['environment'], env)
                self.assertEqual(result['password'], 'Fixture_123')
                self.assertEqual(source.read_bytes(), before)

    def test_no_matching_replay_fails_without_random_new_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with self.assertRaises((ValueError, FileNotFoundError, RuntimeError)):
                self.prepare(project, 'gld_model_1_dataset_workflow_wifi')
            self.assertFalse(any(project.rglob('credentials.local.json')))
            self.assertFalse(any(project.rglob('*.h')))

    def test_length_boundaries_and_allowed_characters(self):
        for password, valid in [('A'*7, False), ('A'*8, True), ('A'*63, True), ('A'*64, False),
                                ('Valid_12-', True), ('Not+Valid', False), ('Not Valid', False), ('Bad\nValue', False)]:
            with self.subTest(length=len(password), valid=valid), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                env = 'gld_model_1_dataset_workflow_wifi'
                path = self.write(project, env, self.data(env, password))
                before = path.read_bytes()
                if valid:
                    self.prepare(project, env)
                else:
                    with self.assertRaises(ValueError):
                        self.prepare(project, env)
                    self.assertFalse(any(project.rglob('*.h')))
                self.assertEqual(path.read_bytes(), before)

    def test_malformed_own_file_never_falls_back_or_rotates(self):
        for patch in (dict(environment='wrong'), dict(protocol='gld-dataset-wifi/2'), dict(username='other')):
            with self.subTest(field=list(patch)), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                env = 'gld_model_1_dataset_workflow_wifi'
                path = self.write(project, env, dict(self.data(env), **patch))
                before = path.read_bytes()
                replay = 'gld_model_1_dataset_replay_wifi'
                self.write(project, replay, self.data(replay, protocol='gld-dataset-wifi/2'), 'gld-dataset-replay-wifi')
                with self.assertRaises(ValueError):
                    self.prepare(project, env)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse(any(project.rglob('*.h')))

    def test_old_or_unknown_targets_rejected_before_writes(self):
        for env in ('gld_model_1_dataset_wifi', 'gld_model_1_dataset_replay_wifi', 'gld_model_4_dataset_workflow_wifi', 'gld'):
            with self.subTest(env=env), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                with self.assertRaises(ValueError):
                    self.prepare(project, env)
                self.assertEqual(list(project.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
