from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import json


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_default_config_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = recall_config.ensure_config(tmp)
            self.assertTrue(path.exists())
            cfg = recall_config.load_config(tmp)
            self.assertEqual(cfg["backend"], "sqlite")
            self.assertIn("requirements", cfg["categories"])

    def test_custom_category_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.add_category("API Contracts", "Stable API shapes", 1.4, tmp)
            cfg = recall_config.load_config(tmp)
            self.assertIn("api_contracts", cfg["categories"])
            self.assertEqual(cfg["categories"]["api_contracts"]["weight"], 1.4)

    def test_invalid_backend_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.ensure_config(tmp)
            path = recall_config.config_path(tmp)
            payload = path.read_text(encoding="utf-8").replace('"backend": "sqlite"', '"backend": "remote"')
            path.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported RECALL backend"):
                recall_config.load_config(tmp)

    def test_project_root_config_is_copied_before_default_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_config = Path(tmp) / "memory_config.json"
            payload = recall_config.default_config()
            payload["backend"] = "jsonl"
            payload["categories"]["requirements"]["weight"] = 1.9
            root_config.write_text(json.dumps(payload), encoding="utf-8")

            target = recall_config.ensure_config(tmp)
            cfg = recall_config.load_config(tmp)
            self.assertEqual(target, Path(tmp) / ".codex_memory" / "memory_config.json")
            self.assertEqual(cfg["backend"], "jsonl")
            self.assertEqual(cfg["categories"]["requirements"]["weight"], 1.9)

    def test_invalid_category_weight_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "weight must be greater than zero"):
            recall_config.validate_config({"categories": {"bad": {"weight": 0}}})
        with self.assertRaisesRegex(ValueError, "weight must be numeric"):
            recall_config.validate_config({"categories": {"bad": {"weight": "heavy"}}})


if __name__ == "__main__":
    unittest.main()
