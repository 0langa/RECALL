from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parents[1]
INSPECT_PACKAGE = SUITE_ROOT.parent / "plugins" / "recall" / "scripts" / "inspect_package.py"

# Real lines from RECALL 1.6.1 that the old keyword pattern flagged as secrets.
ORDINARY_PYTHON = "\n".join([
    "token = marker.group(0)",
    "token = token[:-1]",
    "def idf_weight(token: str, doc_freq: dict[str, int], total_docs: int) -> float:",
    "    token = _writes.set((*_writes.get(), _WriteState(path, None, callbacks)))",
    "def _session_pointer_path(root: str | Path, provider: str, session_token: str) -> Path:",
    '    session_token = event.session_id or event.transcript_path or "anonymous"',
    "# identifier such as ``token=dummy-secret-value`` must still fail.",
    "",
])
# Built at runtime so no provider-shaped token sits in the repository.
FAKE_OPENAI_KEY = "sk-" + "x" * 24
SECRET_CASES = {
    "scripts/unquoted.py": "token=dummy-secret-value\n",
    "scripts/quoted.py": 'api_key = "abc123def456ghi789"\n',
    "scripts/commented.py": '# password = "hunter2hunter2"\n',
    "docs/config.md": "password: hunter2hunter2\n",
    "scripts/prefixed.py": f"client = make_client({FAKE_OPENAI_KEY!r})\n",
}


def load_module(name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_package_hygiene_module():
    return load_module("package_hygiene_check", SUITE_ROOT / "scripts" / "package_hygiene_check.py")


def secret_failures(files: dict[str, str]) -> list[str]:
    module = load_package_hygiene_module()
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "recall.zip"
        with zipfile.ZipFile(archive, "w") as package:
            for name, text in files.items():
                package.writestr(name, text)
        report = module.inspect_zip(archive)
    return [failure for failure in report["failures"] if failure.startswith("secret-like")]


class PackageHygieneContractTests(unittest.TestCase):
    def test_required_files_match_hyphen_case_skill_layout(self) -> None:
        module = load_package_hygiene_module()
        required = set(module.REQUIRED_FILES)
        self.assertIn("skills/save-insight/SKILL.md", required)
        self.assertIn("skills/retrieve-memory/SKILL.md", required)
        self.assertIn("skills/define-category/SKILL.md", required)
        self.assertNotIn("skills/save_insight/SKILL.md", required)
        self.assertNotIn("skills/retrieve_memory/SKILL.md", required)

    def test_ordinary_python_is_not_reported_as_a_secret(self) -> None:
        self.assertEqual(secret_failures({"scripts/storage.py": ORDINARY_PYTHON}), [])

    def test_secret_literals_still_fail(self) -> None:
        for name, text in SECRET_CASES.items():
            with self.subTest(name=name):
                failures = secret_failures({name: text})
                self.assertEqual(len(failures), 1, failures)
                self.assertIn(f"{name} (line 1)", failures[0])

    def test_secret_after_a_false_positive_in_the_same_file_still_fails(self) -> None:
        text = ORDINARY_PYTHON + 'token = "dummy-secret-value"\n'
        failures = secret_failures({"scripts/storage.py": text})
        self.assertEqual(len(failures), 1, failures)
        self.assertIn(f"(line {ORDINARY_PYTHON.count(chr(10)) + 1})", failures[0])

    def test_secret_filter_matches_the_plugin_release_inspector(self) -> None:
        suite = load_package_hygiene_module()
        plugin = load_module("inspect_package", INSPECT_PACKAGE)
        cases = {"scripts/storage.py": ORDINARY_PYTHON, **SECRET_CASES}
        for name, text in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    suite.find_secret_lines(name, text, suite.SECRET_PATTERNS),
                    plugin.find_secret_lines(name, text, plugin.SECRET_PATTERNS),
                )


if __name__ == "__main__":
    unittest.main()
