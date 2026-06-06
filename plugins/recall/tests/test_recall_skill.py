from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "recall_skill.py"


def run_skill(root: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ADAPTER), "--root", root, *args],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


class RecallSkillAdapterTests(unittest.TestCase):
    def test_save_retrieve_and_define_use_public_skill_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            category = run_skill(
                tmp,
                "define-category",
                "api_contracts",
                "--description",
                "Stable API shapes and compatibility promises.",
                "--weight",
                "1.4",
            )
            self.assertEqual(category["action"], "define-category")
            self.assertEqual(category["details"]["weight"], 1.4)

            saved = run_skill(
                tmp,
                "save-insight",
                "api_contracts",
                "Callbacks must keep their webhook payload shape stable.",
                "--summary",
                "Webhook payload shape is stable.",
                "--details",
                "Consumers depend on callback field names staying compatible.",
                "--tag",
                "webhooks",
                "--source",
                "skill",
                "--status",
                "active",
                "--importance",
                "0.8",
                "--confidence",
                "0.9",
            )
            self.assertEqual(saved["action"], "save-insight")
            self.assertEqual(saved["category"], "api_contracts")

            result = run_skill(
                tmp,
                "retrieve-memory",
                "stable webhook payload",
                "--category",
                "api_contracts",
                "--summary",
            )
            self.assertIn("webhook payload shape", result["summary"])
            self.assertEqual(result["results"][0]["metadata"]["source"], "skill")


if __name__ == "__main__":
    unittest.main()
