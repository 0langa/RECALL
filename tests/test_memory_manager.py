from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import config as recall_config  # noqa: E402


class MemoryManagerTests(unittest.TestCase):
    def test_add_and_query_sqlite_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "decisions",
                "Use SQLite as the default local backend for RECALL.",
                {"file": "RECALL_Design_and_Development_Plan.md"},
                tmp,
            )
            self.assertEqual(record.category, "decisions")
            self.assertTrue((Path(tmp) / ".codex_memory" / "vector_index.bin").exists())
            result = memory_manager.query("local backend database", root=tmp, summarize=True)
            self.assertEqual(len(result["results"]), 1)
            self.assertIn("SQLite", result["summary"])

    def test_add_and_query_jsonl_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.ensure_config(tmp)
            cfg = recall_config.load_config(tmp)
            cfg["backend"] = "jsonl"
            recall_config.save_config(cfg, tmp)
            memory_manager.add_record("commands", "Verified command: python -m unittest discover -s tests", root=tmp)
            result = memory_manager.query("unit test command", categories=["commands"], root=tmp, summarize=True)
            self.assertEqual(result["results"][0]["category"], "commands")
            self.assertIn("unittest", result["summary"])

    def test_unknown_category_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record("API Contracts", "Do not break the v1 payload shape.", root=tmp)
            self.assertEqual(record.category, "api_contracts")
            result = memory_manager.query("payload shape", categories=["api_contracts"], root=tmp)
            self.assertEqual(result["results"][0]["category"], "api_contracts")

    def test_secret_like_content_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("debug_history", "api_key=dummy-secret-value", root=tmp)
            result = memory_manager.query("api key", root=tmp)
            self.assertIn("[REDACTED]", result["results"][0]["content"])

    def test_rebuild_index_restores_missing_vector_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("architecture", "Storage is the source of truth for RECALL memories.", root=tmp)
            index_path = Path(tmp) / ".codex_memory" / "vector_index.bin"
            index_path.unlink()
            report = memory_manager.rebuild_index(tmp)
            self.assertEqual(report["indexed_records"], 1)
            self.assertTrue(index_path.exists())
            result = memory_manager.query("source of truth", root=tmp)
            self.assertEqual(result["results"][0]["category"], "architecture")

    def test_query_auto_repairs_incomplete_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("requirements", "RECALL must repair a missing vector index automatically.", root=tmp)
            index_path = Path(tmp) / ".codex_memory" / "vector_index.bin"
            index_path.write_text("", encoding="utf-8")
            result = memory_manager.query("missing vector index", root=tmp)
            self.assertEqual(len(result["results"]), 1)
            index_records = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(index_records), 1)

    def test_doctor_reports_schema_and_index_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("decisions", "Diagnostics should report storage and index state.", root=tmp)
            report = memory_manager.doctor(tmp)
            self.assertEqual(report["backend"], "sqlite")
            self.assertGreaterEqual(report["schema_version"], 1)
            self.assertEqual(report["records"], 1)
            self.assertEqual(report["index_records"], 1)
            self.assertTrue(report["index_complete"])

    def test_retrieval_prefers_weighted_lexical_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("tasks", "Background note about a parser cleanup.", root=tmp)
            memory_manager.add_record("requirements", "Parser cleanup must preserve the public CLI contract.", root=tmp)
            result = memory_manager.query("parser cleanup CLI contract", root=tmp)
            self.assertEqual(result["results"][0]["category"], "requirements")

    def test_category_exclude_filter_removes_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("risks", "The migration path is fragile.", root=tmp)
            memory_manager.add_record("commands", "Run migrations with python scripts.", root=tmp)
            result = memory_manager.query("migration", exclude_categories=["risks"], root=tmp)
            self.assertEqual([item["category"] for item in result["results"]], ["commands"])

    def test_vector_index_records_include_model_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("decisions", "Index records include portable metadata.", root=tmp)
            line = (Path(tmp) / ".codex_memory" / "vector_index.bin").read_text(encoding="utf-8").splitlines()[0]
            payload = json.loads(line)
            self.assertEqual(payload["embedding_model"], "local-hash-v1")
            self.assertEqual(payload["dimensions"], 64)
            self.assertIn("embedding", payload)


if __name__ == "__main__":
    unittest.main()
