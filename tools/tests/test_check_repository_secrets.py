from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "check_repository_secrets.py"
SPEC = importlib.util.spec_from_file_location("check_repository_secrets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class RepositorySecretGuardTests(unittest.TestCase):
    def test_placeholder_text_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            path = root / "config.md"
            path.write_text(
                "MQTT_PASSWORD=CHANGE_ME_MQTT_PASSWORD\nMQTT_HOST=CHANGE_ME_MQTT_HOST\n",
                encoding="utf-8",
            )
            self.assertEqual(guard.exposed_digest_hits(path, root), [])

    def test_private_key_marker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            path = root / "secret.pem"
            path.write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
            hits = guard.exposed_digest_hits(path, root)
            self.assertEqual(len(hits), 1)
            self.assertIn("private-key material", hits[0])

    def test_known_digest_is_rejected_without_storing_plaintext_in_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            path = root / "credential.txt"
            # Recovering the original token is intentionally unnecessary. Patch
            # the digest set to prove the detection boundary with a synthetic value.
            token = "synthetic-exposed-value"
            digest = guard.hashlib.sha256(token.encode("utf-8")).hexdigest()
            original = guard.KNOWN_EXPOSED_TOKEN_DIGESTS
            guard.KNOWN_EXPOSED_TOKEN_DIGESTS = {digest}
            try:
                path.write_text(token + "\n", encoding="utf-8")
                hits = guard.exposed_digest_hits(path, root)
            finally:
                guard.KNOWN_EXPOSED_TOKEN_DIGESTS = original
            self.assertEqual(len(hits), 1)
            self.assertIn("known exposed", hits[0])


if __name__ == "__main__":
    unittest.main()
