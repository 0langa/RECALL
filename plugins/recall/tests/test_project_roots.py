"""Project scope must be known before a store can be created."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import config  # noqa: E402
import memory_manager  # noqa: E402
import project_context  # noqa: E402
import retrieval  # noqa: E402


class ProjectRootTests(unittest.TestCase):
    def test_rootless_write_fails_without_creating_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            os.environ.pop("RECALL_PROJECT_ROOT", None)
            with patch.object(Path, "cwd", return_value=Path(tmp)):
                with self.assertRaises(ValueError):
                    memory_manager.add_record("decisions", "Keep files local.")
                self.assertFalse((Path(tmp) / ".recall").exists())

    def test_rootless_read_has_reason_and_creates_no_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            os.environ.pop("RECALL_PROJECT_ROOT", None)
            with patch.object(Path, "cwd", return_value=Path(tmp)):
                result = retrieval.query("missing decision")
            self.assertEqual(result["results"], [])
            self.assertEqual(result["root_decision"]["status"], "unresolved")
            self.assertEqual(result["empty_reason"], "unresolved_root")
            self.assertFalse((Path(tmp) / ".recall").exists())

    def test_blank_root_is_not_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Path, "cwd", return_value=Path(tmp)):
                with self.assertRaises(ValueError):
                    config.ensure_config("   ")
            self.assertFalse((Path(tmp) / ".recall").exists())

    def test_child_manifest_blocks_ancestor_store_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            config.ensure_config(parent)
            child = parent / "child"
            child.mkdir()
            (child / "pyproject.toml").write_text("[project]\nname='child'\n", encoding="utf-8")
            nested = child / "src"
            nested.mkdir()
            self.assertEqual(project_context.resolve_project_root(nested), child.resolve())
            self.assertFalse((child / ".recall").exists())
            self.assertFalse((parent / ".recall" / "memory.sqlite").exists())

    def test_env_parent_cannot_capture_child_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            child = parent / "child"
            child.mkdir()
            (child / "package.json").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"RECALL_PROJECT_ROOT": str(parent)}):
                with patch.object(Path, "cwd", return_value=child):
                    with self.assertRaises(ValueError):
                        memory_manager.add_record("decisions", "Child owns this claim.")
                    self.assertEqual(config.root_decision()["status"], "ambiguous")
            self.assertFalse((parent / ".recall").exists())
            self.assertFalse((child / ".recall").exists())

    def test_explicit_root_is_reported_and_empty_read_does_not_initialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = retrieval.query("absent", root=tmp)
            self.assertEqual(result["root_decision"]["reason"], "explicit_root")
            self.assertEqual(result["root_decision"]["root"], str(Path(tmp).resolve()))
            self.assertEqual(result["empty_reason"], "no_store")
            self.assertFalse((Path(tmp) / ".recall").exists())


if __name__ == "__main__":
    unittest.main()
