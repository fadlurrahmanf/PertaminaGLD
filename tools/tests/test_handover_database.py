"""Synthetic MariaDB distribution/lifecycle/CSV fixtures; no database is started."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("database_handover_under_test", TOOLS / "handover_database.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)


class DatabaseHandoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.source = self.root / "distribution"; (self.source / "bin").mkdir(parents=True)
        for name in ("mysqld.exe", "mysql.exe", "mysqladmin.exe", "mysql_install_db.exe"):
            (self.source / "bin" / name).write_bytes(b"SYNTHETIC-EXECUTABLE-NOT-RUN")
        (self.source / "share").mkdir(); (self.source / "share/bootstrap.sql").write_text("synthetic schema")
        (self.source / "COPYING").write_text("synthetic license")
        self.output = self.root / "artifact"; self.dest = self.root / "runtime"; self.data = self.root / "data"
        self.config = dict(name="pertamina_gld", user="pgl", password="SYNTHETIC'\\ONLY", rootPassword="SYNTHETIC_ROOT_ONLY")
        self.version = mock.patch.object(db, "_version", return_value="10.4.32"); self.version.start()

    def tearDown(self):
        db._OWNED.clear(); self.version.stop(); self.temp.cleanup()

    def export(self):
        return db.export_runtime(self.source, self.output)

    def owned(self):
        process = mock.Mock(); process.pid = 999999; process.poll.return_value = None
        handle = db.OwnedDatabase(process, self.source, self.data, self.config, 33306, io.BytesIO())
        db._OWNED[33306] = handle
        return handle

    def test_distribution_export_extract_excludes_all_live_data_and_configs(self):
        for directory in ("data", "backup"):
            (self.source / directory).mkdir(); (self.source / directory / "PRIVATE").write_text("DO_NOT_EXPORT")
        (self.source / "bin/my.ini").write_text("password=DO_NOT_EXPORT")
        result = self.export(); self.assertEqual(result["version"], "10.4.32")
        names = {x["path"] for x in result["files"]}
        self.assertNotIn("bin/my.ini", names)
        self.assertFalse(any(x.startswith(("data/", "backup/")) for x in names))
        db.extract_runtime(self.output / db.MANIFEST, self.dest)
        self.assertTrue((self.dest / "bin/mysqld.exe").is_file())
        self.assertEqual((self.dest / "licenses/COPYING").read_text(), "synthetic license")

    def test_tampered_archive_and_existing_destination_are_refused(self):
        result = self.export(); part = self.output / result["parts"][0]["path"]
        before = part.read_bytes(); part.write_bytes(before + b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum"): db.extract_runtime(self.output / db.MANIFEST, self.dest)
        self.assertFalse(self.dest.exists())
        part.write_bytes(before); self.dest.mkdir(); keep = self.dest / "keep"; keep.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "new or empty"): db.extract_runtime(self.output / db.MANIFEST, self.dest)
        self.assertEqual(keep.read_text(), "preserve")

    def test_initializer_uses_only_new_owned_data_directory_and_never3306(self):
        def initialized(args, **kwargs):
            self.assertNotIn("--password", " ".join(args))
            self.assertEqual(kwargs["cwd"], self.source)
            self.assertEqual(list(self.data.iterdir()), [], "installer must receive an actually empty datadir")
            self.assertFalse((self.data / db.OWNER).exists())
            self.assertTrue(self.data.with_name(self.data.name + ".handover-initialization.json").is_file())
            self.assertIs(kwargs["stderr"], db.subprocess.STDOUT)
            kwargs["stdout"].write(b"synthetic successful initializer diagnostics")
            (self.data / "mysql").mkdir()
            return SimpleNamespace(returncode=0)
        with mock.patch.object(db.subprocess, "run", side_effect=initialized) as call:
            result = db.initialize(self.source, self.data, self.config, 33306)
            self.assertTrue(result["initialized"]); self.assertEqual(call.call_count, 1)
            with self.assertRaises(ValueError): db.initialize(self.source, self.data, self.config, 33306)
            with self.assertRaisesRegex(ValueError, "other than3306"): db.initialize(self.source, self.root / "other", self.config, 3306)
            self.assertEqual(call.call_count, 1)

    def test_failed_initializer_keeps_outside_diagnostics_and_blocks_blind_retry(self):
        def failed(args, **kwargs):
            self.assertEqual(list(self.data.iterdir()), [])
            kwargs["stdout"].write(b"SYNTHETIC_INITIALIZER_FAILURE_ONLY")
            return SimpleNamespace(returncode=1)
        with mock.patch.object(db.subprocess, "run", side_effect=failed) as call:
            with self.assertRaisesRegex(ValueError, "DB_INITIALIZE_FAILED") as error:
                db.initialize(self.source, self.data, self.config, 33306)
            self.assertNotIn("SYNTHETIC_INITIALIZER_FAILURE_ONLY", str(error.exception))
            self.assertNotIn(self.config["password"], str(error.exception))
            self.assertFalse((self.data / db.OWNER).exists())
            reservation = self.data.with_name(self.data.name + ".handover-initialization.json")
            diagnostics = self.data.with_name(self.data.name + ".initialization-diagnostics.log")
            self.assertEqual(json.loads(reservation.read_text())["initializationState"], "failed")
            self.assertEqual(diagnostics.read_bytes(), b"SYNTHETIC_INITIALIZER_FAILURE_ONLY")
            with self.assertRaisesRegex(ValueError, "reconcile before retry"):
                db.initialize(self.source, self.data, self.config, 33306)
            self.assertEqual(call.call_count, 1)

    def test_sql_uses_ephemeral_defaults_file_and_stdin_without_password_argv(self):
        self.owned(); observed = {}
        def client(args, **kwargs):
            self.assertEqual(args[0], str(self.source / "bin/mysql.exe"))
            self.assertTrue(args[1].startswith("--defaults-extra-file="))
            self.assertNotIn(self.config["password"], " ".join(args))
            config = Path(args[1].split("=", 1)[1]); observed["path"] = config
            text = config.read_text(); self.assertIn("port=33306", text); self.assertIn("protocol=tcp", text)
            self.assertEqual(kwargs["input"], b"SELECT COUNT(*) FROM handover_files;")
            return SimpleNamespace(returncode=0, stdout=b"2\n")
        with mock.patch.object(db, "_listener_owned", return_value=True), mock.patch.object(db.subprocess, "run", side_effect=client):
            result = db.run_sql(self.source, self.config, 33306, "SELECT COUNT(*) FROM handover_files;")
        self.assertEqual(result, b"2\n"); self.assertFalse(observed["path"].exists())

    def test_unowned_or_wrong_port_never_queries_database(self):
        with mock.patch.object(db.subprocess, "run") as call:
            with self.assertRaisesRegex(ValueError, "other than3306"): db.run_sql(self.source, self.config, 3306, "SELECT1")
            with self.assertRaisesRegex(ValueError, "owned isolated"): db.run_sql(self.source, self.config, 33306, "SELECT1")
            call.assert_not_called()

    def test_history_exact_bytes_rows_provenance_and_idempotent_sql(self):
        self.owned(); history = self.root / "history"; history.mkdir()
        csv_raw = b'\xef\xbb\xbfWaktu (ms),Label pengujian,MQ8 (V)\r\n500,"clear,air",0.5\r\n'
        ledger_raw = b'{"seq":0,"sensor":[1,2]}\n{"seq":1}\n'
        files = []
        for name, content in (("test.csv", csv_raw), ("ledger.jsonl", ledger_raw)):
            (history / name).write_bytes(content)
            files.append(dict(path=name, sha256=hashlib.sha256(content).hexdigest(), sources=["original/" + name]))
        sql = []
        with mock.patch.object(db, "_listener_owned", return_value=True), mock.patch.object(db, "run_sql", side_effect=lambda *a, **k: sql.append(a[3])):
            result = db.import_history(self.source, self.config, 33306, dict(files=files), history_root=history)
            again = db.import_history(self.source, self.config, 33306, dict(files=files), history_root=history)
        self.assertEqual(result["files"], 2); self.assertEqual(result["rows"], 3)
        self.assertEqual(result, again); self.assertEqual(sql[:2], sql[2:])
        self.assertIn("X'" + csv_raw.hex() + "'", sql[0])
        self.assertIn("INSERT IGNORE INTO handover_rows", sql[0]); self.assertIn("handover_sources", sql[0])
        self.assertNotIn("INSERT INTO gld_dataset", "\n".join(sql))
        self.assertIn("not an existing database dump", result["source"])

    def test_history_checksum_and_path_escape_are_rejected_before_sql(self):
        self.owned(); (self.root / "file.csv").write_text("a,b\n1,2\n")
        with mock.patch.object(db, "_listener_owned", return_value=True), mock.patch.object(db, "run_sql") as call:
            for item in (dict(path="../file.csv",sha256="0"*64),dict(path="file.csv",sha256="0"*64)):
                with self.assertRaises(ValueError): db.import_history(self.source,self.config,33306,dict(files=[item]),history_root=self.root)
            call.assert_not_called()

    def test_schema_matches_legacy_dataset_columns(self):
        for field in ("device_id", "node_id", "mode", "seq", "timestamp_ms", "label", "nulling_profile_id", "sv0", "sv7", "gain0", "gain7"):
            self.assertIn(field, db.DATASET_SCHEMA)
        for table in ("handover_files", "handover_sources", "handover_rows"):
            self.assertIn(table, db.HISTORY_SCHEMA)

    def test_stop_rejects_unowned_process(self):
        handle = self.owned(); db._OWNED.clear()
        with self.assertRaisesRegex(ValueError, "unowned"): db.stop(handle)
        handle.process.terminate.assert_not_called()

    def test_new_database_provisions_tcp_root_for_graceful_admin_shutdown(self):
        self.data.mkdir()
        receipt=dict(initialized=True,port=33306,database=self.config['name'],rootProvisioned=False)
        process=mock.Mock(pid=999999);process.poll.return_value=None
        statements=[]
        with (mock.patch.object(db,'_owner',return_value=(self.data,receipt)),
              mock.patch.object(db,'_listener_owned',return_value=True),
              mock.patch.object(db.subprocess,'Popen',return_value=process),
              mock.patch.object(db,'run_sql',side_effect=lambda *a,**k:statements.append(a[3]))):
            handle=db.start(self.source,self.data,self.config,33306)
        try:
            self.assertIn("ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY",statements[0])
            self.assertIn("ALTER USER 'root'@'localhost' IDENTIFIED BY",statements[0])
            self.assertIn("TO 'root'@'127.0.0.1' WITH GRANT OPTION",statements[0])
            self.assertTrue(receipt['rootProvisioned'])
        finally:handle.log.close()


if __name__ == "__main__": unittest.main()
