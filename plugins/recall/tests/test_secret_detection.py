"""Git object IDs are not the unlabelled AWS-secret heuristic."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import security  # noqa: E402


class SecretDetectionTests(unittest.TestCase):
    def test_hex_evidence_signature_survives_nested_redaction(self) -> None:
        import hashlib
        import hmac

        signature = hmac.new(b"fixture-only-key", b"observed local evidence", hashlib.sha256).hexdigest()
        receipt = {"observed_evidence": {"signature": signature}}
        self.assertEqual(len(signature), 64)
        self.assertFalse(security.contains_secret(signature))
        self.assertEqual(security.redact_value(receipt), receipt)

    def test_normal_git_sha_survives_detection_and_redaction(self) -> None:
        sha = "c07e9766e5cb079e08787a1145a75749050da7a6"
        for value in (sha, sha.upper(), f"Release commit {sha} passed."):
            self.assertFalse(security.contains_secret(value))
            self.assertEqual(security.redact_text(value), value)

    def test_git_sha_shape_does_not_bypass_secret_assignments(self) -> None:
        sha = "c07e9766e5cb079e08787a1145a75749050da7a6"
        for keyword in ("token", "api_key", "password", "secret", "authorization"):
            value = f"{keyword}={sha}"
            self.assertTrue(security.contains_secret(value), keyword)
            self.assertIn("[REDACTED]", security.redact_text(value))

    def test_true_secret_shapes_and_near_sha_remain_blocked(self) -> None:
        values = [
            "AKIAIOSFODNN7EXAMPLE",
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWX",
            "c07e9766e5cb079e08787a1145a75749050da7az",
        ]
        for value in values:
            self.assertTrue(security.contains_secret(value), value)
            self.assertNotEqual(security.redact_text(value), value)


if __name__ == "__main__":
    unittest.main()
