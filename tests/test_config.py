from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


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


if __name__ == "__main__":
    unittest.main()
