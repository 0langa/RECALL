from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import memory_manager  # noqa: E402
import memory_review  # noqa: E402


class ApplicationServiceTests(unittest.TestCase):
    def test_review_request_rejects_non_positive_limit(self) -> None:
        from models import ReviewRequest

        with self.assertRaisesRegex(ValueError, "limit must be positive"):
            ReviewRequest(limit=0)

    def test_review_service_matches_legacy_review_shape(self) -> None:
        from models import ReviewRequest
        from services.health_service import review_memory

        with tempfile.TemporaryDirectory(prefix="recall-service-") as tmp:
            memory_manager.add_record(
                "decisions",
                "Use the public application service boundary.",
                memory_manager.build_card_metadata(status="active", source="test"),
                tmp,
            )
            expected = memory_review.review_memory(tmp, statuses=["active"], limit=10)
            response = review_memory(ReviewRequest(root=Path(tmp), statuses=("active",), limit=10))
            self.assertEqual(response.payload, expected)
            self.assertEqual(response.to_dict(), expected)

    def test_review_cli_preserves_public_json_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="recall-service-cli-") as tmp:
            memory_manager.add_record(
                "architecture",
                "Services preserve the public review command.",
                memory_manager.build_card_metadata(status="active", source="test"),
                tmp,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "recall_skill.py"),
                    "--root",
                    tmp,
                    "review-memory",
                    "--status",
                    "active",
                    "--limit",
                    "10",
                ],
                cwd=PLUGIN_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["action"], "review-memory")
            self.assertEqual(payload["review"]["matched"], 1)
            self.assertEqual(payload["review"]["memories"][0]["category"], "architecture")


if __name__ == "__main__":
    unittest.main()
