from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def load_package_hygiene_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "package_hygiene_check.py"
    spec = importlib.util.spec_from_file_location("package_hygiene_check", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PackageHygieneContractTests(unittest.TestCase):
    def test_required_files_match_hyphen_case_skill_layout(self) -> None:
        module = load_package_hygiene_module()
        required = set(module.REQUIRED_FILES)
        self.assertIn("skills/save-insight/SKILL.md", required)
        self.assertIn("skills/retrieve-memory/SKILL.md", required)
        self.assertIn("skills/define-category/SKILL.md", required)
        self.assertNotIn("skills/save_insight/SKILL.md", required)
        self.assertNotIn("skills/retrieve_memory/SKILL.md", required)


if __name__ == "__main__":
    unittest.main()
