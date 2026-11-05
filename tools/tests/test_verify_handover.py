"""Synthetic clean-export/verifier tests; never start real services."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "verify_handover.py"
SPEC = importlib.util.spec_from_file_location("test_verify_handover_module", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class CleanHandoverVerification(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "checkout with spaces"
        self.report_root = self.base / "reports"
        self.synthetic_secret = "SYNTHETIC_APPROVED_STATE_ONLY"
        self.sources = {
            "apps/gld-operator/python-embed/python.exe": b"synthetic inert executable",
            "apps/gld-operator/bridge.py": b"# source",
            "apps/gld-operator/workflow-connection-profiles.json": b"{}",
            "apps/ch-operator/bridge.py": b"# source",
            "apps/gw-operator/bridge.py": b"# source",
            "apps/operator-hub/bridge.py": b"# source",
            "apps/lib/runner.py": b"# source",
            "server/nodered/apply-pertamina-gld-flow.js": b"// source",
            "tools/handover_stack.py": b"# inert fake child",
            "tools/handover_nodered_runner.cjs": b"// required pending helper",
            "tools/verify_handover.py": b"# source",
            "start-handover.bat": b"rem start",
            "verifikasi-handover.bat": b"rem verify",
            ".gitattributes": b"handover/state/** -text\n",
            ".gitignore": b".env\noutput/handover-verification/\n",
            "handover/state/config/system.json": json.dumps(dict(secret=self.synthetic_secret)).encode(),
            "handover/state/nodered/flows_cred.json": b"synthetic approved encrypted payload",
            "handover/deployment.json": b"{}",
            "handover/plaintext-authorization.json": b"{}",
        }
        forbidden = (
            "server/nodered/.env", "server/nodered/.env.production", "server/nodered/flows_cred.json",
            "apps/operator-hub/credentials.local.json", "apps/operator-hub/startup.local.json",
            "apps/operator-hub/mockups/draft.html", "apps/gld-operator/output/recording.csv",
            "apps/gld-operator/node_modules/test.js", "apps/gld-operator/.pio/secret.h",
            "apps/gld-operator/__pycache__/bridge.pyc", "archive/user-private.txt", "tmp/not-approved.txt",
            "handover/not-approved.txt",
        )
        self.forbidden = set(forbidden)
        for relative, raw in self.sources.items(): self.write(self.repo / relative, raw)
        for relative in forbidden: self.write(self.repo / relative, b"UNAPPROVED_PRIVATE_FIXTURE")
        self.approved = [name for name in self.sources if name.startswith("handover/")]

    @staticmethod
    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)

    def tearDown(self):
        self.temporary.cleanup()

    def static(self, root):
        self.assertEqual(root, self.repo.resolve())
        checks = [dict(name=name, status="pass", code="VERIFIED") for name in verifier.STATIC_LABELS]
        checks.append(dict(name="node_nodered_runtime", status="skip", code="EXPLICIT_RUNTIME_NOT_PROVIDED"))
        return dict(ok=True, checks=checks, approvedHandoverFiles=self.approved)

    def run_verify(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            report = verifier.verify(self.repo, output_root=self.report_root, git_executable="", static_runner=self.static, **kwargs)
        self.assertNotIn(self.synthetic_secret, stream.getvalue())
        self.assertNotIn(self.synthetic_secret, json.dumps(report))
        self.last_console = stream.getvalue()
        return report

    def child(self, command, *, cwd, log, timeout):
        self.assertEqual(timeout, 600)
        self.assertNotEqual(cwd.resolve(), self.repo.resolve())
        self.assertEqual(Path(command[0]), cwd / "apps/gld-operator/python-embed/python.exe")
        self.assertEqual(command[command.index("--port-offset") + 1], "10000")
        self.assertIn("--local-only", command); self.assertIn("--self-test", command); self.assertIn("--no-browser", command)
        self.assertEqual(Path(command[command.index("--repo-root") + 1]), cwd)
        self.assertTrue((cwd / "tools/handover_nodered_runner.cjs").is_file())
        self.assertEqual((cwd / ".gitignore").read_bytes(), self.sources[".gitignore"])
        for relative in self.forbidden: self.assertFalse((cwd / relative).exists(), relative)
        for relative in self.approved: self.assertEqual((cwd / relative).read_bytes(), self.sources[relative])
        work = Path(command[command.index("--work-root") + 1]); self.assertTrue(work.is_relative_to(cwd))
        self.write(work / "stack-result.json", json.dumps(dict(status="PASS", ports=dict(database=43306),
            selfTest=dict(mqttAuthentication=True, aesRoundTrip=True, aesMqttNodeRedDecrypt=True,
                          nodeRedDatabaseInsert=True, nodeRedCsvWrite=True, historyFiles=53, historyRows=999,
                          historyByteMismatches=0, hardwareTested=False), privateExtra=self.synthetic_secret)).encode())
        self.write(log, b"synthetic diagnostic output")
        return dict(returnCode=0, timedOut=False)

    def test_full_default_exports_without_hidden_inputs_and_runs_only_copied_stack(self):
        before = {name: (self.repo / name).read_bytes() for name in self.sources}
        result = self.run_verify(child_runner=self.child)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["ownedServicesStopped"])
        self.assertFalse(result["hardwareTested"])
        self.assertEqual(before, {name: (self.repo / name).read_bytes() for name in self.sources})
        self.assertFalse(result["gitInputs"]["committed"])
        self.assertTrue(result["gitInputs"]["needsCommitPush"])

    def test_static_only_does_not_copy_or_launch_any_child(self):
        child = mock.Mock(side_effect=AssertionError("must not run"))
        result = self.run_verify(static_only=True, child_runner=child)
        self.assertEqual(result["status"], "PASS"); child.assert_not_called()
        self.assertEqual(list(self.report_root.glob("*/clean-checkout")), [])
        self.assertEqual(result["summary"]["total"], len(verifier.STATIC_LABELS))
        self.assertEqual(result["summary"]["passed"], len(verifier.STATIC_LABELS))
        self.assertGreater(result["summary"]["informationalSkipped"], 0)
        self.assertEqual(result["conclusion"]["code"], "STATIC_CHECKS_PASSED_FULL_STACK_NOT_RUN")
        self.assertIn("Uji fungsi stack belum dijalankan", self.last_console)

    def test_failed_child_or_owned_cleanup_is_not_reported_as_success(self):
        def failed(command, **kwargs):
            self.child(command, **kwargs)
            work = Path(command[command.index("--work-root") + 1])
            self.write(work / "stack-result.json", b'{"status":"cleanup_failed"}')
            return dict(returnCode=1, timedOut=False)
        result = self.run_verify(child_runner=failed)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failureCode"], "STACK_TEST_OR_OWNED_CLEANUP_FAILED")
        self.assertTrue(result["workspaceRetained"])

    def test_timeout_keeps_workspace_and_never_assumes_child_cleanup(self):
        result = self.run_verify(child_runner=lambda *_args, **_kwargs: dict(returnCode=None, timedOut=True, childPid=12345))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failureCode"], "CHILD_STILL_RUNNING_WORKSPACE_RETAINED")
        self.assertTrue(list(self.report_root.glob("*/clean-checkout")))
        self.assertNotIn("ownedServicesStopped", result)

    def test_runtime_parts_require_each_hash_and_the_combined_archive_hash(self):
        directory = self.base / "runtime"; raw = b"synthetic archive bytes"
        self.write(directory / "runtime.zip.001", raw)
        manifest = dict(schemaVersion=1, kind="synthetic-kind", archiveSize=len(raw),
            archiveSha256=hashlib.sha256(raw).hexdigest(),
            parts=[dict(path="runtime.zip.001", size=len(raw), sha256=hashlib.sha256(raw).hexdigest())])
        path = directory / "manifest.json"; self.write(path, json.dumps(manifest).encode())
        self.assertEqual(verifier.runtime_parts(path, "synthetic-kind"), [directory / "runtime.zip.001"])
        self.write(directory / "runtime.zip.001", b"changed bytes")
        with self.assertRaises(verifier.VerificationError): verifier.runtime_parts(path, "synthetic-kind")

    def test_tracked_worktree_changes_and_new_ignored_inputs_are_distinguished(self):
        tracked = set(name for name in self.sources if not name.startswith("handover/") and name != "tools/handover_nodered_runner.cjs")
        def git(_root, _executable, args, **_kwargs):
            if args[0] == "ls-files": output = "\0".join(tracked) + "\0"
            elif args[0] == "diff": output = "apps/gld-operator/bridge.py\0"
            else: output = "handover/state/nodered/flows_cred.json\0"
            return SimpleNamespace(returncode=0, stdout=output.encode())
        with mock.patch.object(verifier, "_git", side_effect=git):
            files, result = verifier.select_export_files(self.repo, self.approved, "synthetic-git")
        self.assertIn("tools/handover_nodered_runner.cjs", files)
        self.assertFalse(result["committed"]); self.assertFalse(result["inputsCommitEligible"])
        self.assertEqual(result["modifiedTrackedInputs"], 1)

    def test_child_timeout_does_not_terminate_or_kill_unknown_process(self):
        process = mock.Mock(pid=9876)
        process.wait.side_effect = subprocess.TimeoutExpired(["synthetic"], 600)
        with mock.patch.object(verifier.subprocess, "Popen", return_value=process) as popen:
            result = verifier.run_child(["synthetic"], cwd=self.base, log=self.base / "child.log")
        self.assertTrue(result["timedOut"])
        process.terminate.assert_not_called(); process.kill.assert_not_called()
        environment = popen.call_args.kwargs["env"]
        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["USERPROFILE"], str(self.base / ".verification-user"))
        self.assertNotIn("NODE_PATH", environment)
        self.assertNotIn("PYTHONPATH", environment)

    def test_console_has_checkmarks_progress_counts_history_and_final_conclusion(self):
        result = self.run_verify(child_runner=self.child)
        required = len(verifier.STATIC_LABELS) + len(verifier.FULL_TESTS) + 4
        self.assertEqual(result["summary"]["total"], required)
        self.assertEqual(result["summary"]["passed"], required)
        self.assertEqual(result["summary"]["failed"], 0)
        self.assertEqual(result["summary"]["skipped"], 0)
        self.assertIn(f"{required:02d}/{required:02d}", self.last_console)
        self.assertIn("[✓]", self.last_console)
        self.assertIn("53 file, 999 baris, 0 beda byte", self.last_console)
        self.assertIn("KESIMPULAN: SOFTWARE HANDOVER LULUS", self.last_console)
        self.assertIn("masih perlu commit/push", self.last_console)
        self.assertIn("belum dibuktikan", self.last_console)

    def test_required_full_flags_missing_or_false_cannot_claim_pass(self):
        for name, _label in verifier.FULL_TESTS:
            for missing in (False, True):
                def faulty(command, **kwargs):
                    result = self.child(command, **kwargs)
                    path = Path(command[command.index("--work-root") + 1]) / "stack-result.json"
                    data = json.loads(path.read_text())
                    if missing: data["selfTest"].pop(name)
                    else: data["selfTest"][name] = False
                    path.write_text(json.dumps(data))
                    return result
                with self.subTest(flag=name, missing=missing):
                    report = self.run_verify(child_runner=faulty)
                    self.assertEqual(report["status"], "FAIL")
                    self.assertGreater(report["summary"]["failed"], 0)
                    self.assertIn("[✗]", self.last_console)
                    self.assertNotIn("KESIMPULAN: SOFTWARE HANDOVER LULUS", self.last_console)

    def test_show_report_is_read_only_and_does_not_rerun_services(self):
        self.run_verify(child_runner=self.child)
        path = next(self.report_root.glob("*/report.json")); before = path.read_bytes()
        with mock.patch.object(verifier, "verify", side_effect=AssertionError("must not rerun")), \
             mock.patch.object(verifier, "run_child", side_effect=AssertionError("must not run")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            report = verifier.show_report(path)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(before, path.read_bytes())
        self.assertIn("KESIMPULAN: SOFTWARE HANDOVER LULUS", output.getvalue())
        self.assertNotIn(self.synthetic_secret, output.getvalue())

    def test_history_mismatch_or_missing_counts_cannot_claim_pass(self):
        for field, value in (("historyByteMismatches", 1), ("historyFiles", 0), ("historyRows", None)):
            def faulty(command, **kwargs):
                result = self.child(command, **kwargs)
                path = Path(command[command.index("--work-root") + 1]) / "stack-result.json"
                data = json.loads(path.read_text()); data["selfTest"][field] = value
                path.write_text(json.dumps(data)); return result
            report = self.run_verify(child_runner=faulty)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["conclusion"]["code"], "SOFTWARE_HANDOVER_FAILED")


if __name__ == "__main__":
    unittest.main()
