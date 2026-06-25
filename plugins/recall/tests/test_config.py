from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_default_config_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = recall_config.ensure_config(tmp)
            self.assertTrue(path.exists())
            self.assertEqual(path.parent.name, ".recall")
            cfg = recall_config.load_config(tmp)
            self.assertEqual(cfg["backend"], "sqlite")
            self.assertEqual(cfg["capture_mode"], "standard")
            self.assertEqual(cfg["recall_mode"], "relevant")
            self.assertEqual(cfg["observability_mode"], "quiet")
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
            expected = Path(tmp) / ".recall" / "memory_config.json"
            self.assertTrue(target.samefile(expected), f"{target} is not {expected}")
            self.assertEqual(cfg["backend"], "jsonl")
            self.assertEqual(cfg["categories"]["requirements"]["weight"], 1.9)

    def test_existing_codex_memory_store_remains_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / ".codex_memory"
            legacy.mkdir()
            payload = recall_config.default_config()
            payload["backend"] = "jsonl"
            (legacy / "memory_config.json").write_text(json.dumps(payload), encoding="utf-8")

            self.assertEqual(recall_config.memory_dir(tmp), legacy.resolve())
            cfg = recall_config.load_config(tmp)
            self.assertEqual(cfg["backend"], "jsonl")
            self.assertFalse((Path(tmp) / ".recall").exists())

    def test_neutral_memory_store_wins_when_both_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            neutral = Path(tmp) / ".recall"
            legacy = Path(tmp) / ".codex_memory"
            neutral.mkdir()
            legacy.mkdir()
            neutral_payload = recall_config.default_config()
            neutral_payload["backend"] = "sqlite"
            legacy_payload = recall_config.default_config()
            legacy_payload["backend"] = "jsonl"
            (neutral / "memory_config.json").write_text(json.dumps(neutral_payload), encoding="utf-8")
            (legacy / "memory_config.json").write_text(json.dumps(legacy_payload), encoding="utf-8")

            self.assertEqual(recall_config.memory_dir(tmp), neutral.resolve())
            self.assertEqual(recall_config.load_config(tmp)["backend"], "sqlite")

    def test_invalid_category_weight_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "weight must be greater than zero"):
            recall_config.validate_config({"categories": {"bad": {"weight": 0}}})
        with self.assertRaisesRegex(ValueError, "weight must be numeric"):
            recall_config.validate_config({"categories": {"bad": {"weight": "heavy"}}})

    def test_update_categories_script_normalizes_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_config = Path(tmp) / "memory_config.json"
            payload = recall_config.default_config()
            payload["categories"]["API Contracts"] = {
                "description": "Stable API shapes",
                "weight": 1.4,
            }
            root_config.write_text(json.dumps(payload), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "update_categories.py"), "--root", tmp],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            report = json.loads(completed.stdout)
            cfg = recall_config.load_config(tmp)
            self.assertIn("api_contracts", report["categories"])
            self.assertIn("api_contracts", cfg["categories"])
            self.assertNotIn("API Contracts", cfg["categories"])

    def test_capture_mode_is_validated_and_can_be_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = recall_config.set_capture_mode("manual", tmp)
            self.assertEqual(cfg["capture_mode"], "manual")
            self.assertEqual(recall_config.load_config(tmp)["capture_mode"], "manual")
            with self.assertRaisesRegex(ValueError, "Unsupported RECALL capture_mode"):
                recall_config.validate_config({"capture_mode": "always-on"})


if __name__ == "__main__":
    unittest.main()
