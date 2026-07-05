from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SmokeRecallTests(unittest.TestCase):
    def test_smoke_recall_json_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "smoke_recall.py"), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertGreaterEqual(result["records"], 4)
        self.assertIn("SessionStart injects the lifecycle contract for the activated project", result["checks"])
        self.assertIn("SessionStart stays quiet for non-activated projects", result["checks"])


if __name__ == "__main__":
    unittest.main()
