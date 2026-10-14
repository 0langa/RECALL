from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_inspect_package():
    spec = importlib.util.spec_from_file_location("inspect_package", ROOT / "scripts" / "inspect_package.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def secret_errors(files: dict[str, str]) -> list[str]:
    module = load_inspect_package()
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "recall.zip"
        with zipfile.ZipFile(archive, "w") as package:
            for name, text in files.items():
                package.writestr(name, text)
        report = module.inspect_package(archive)
    return [error for error in report["errors"] if error.startswith("Secret-like")]


class InspectPackageSecretTests(unittest.TestCase):
    def test_python_expressions_and_comments_are_not_secrets(self) -> None:
        source = "\n".join([
            "token = marker.group(0)",
            "def _session_pointer_path(root: str, provider: str, session_token: str) -> str:",
            '    session_token = event.session_id or event.transcript_path or "anonymous"',
            "# identifier such as ``token=dummy-secret-value`` must still fail.",
            "",
        ])
        self.assertEqual(secret_errors({"scripts/turn_policy.py": source}), [])

    def test_every_match_is_checked_not_only_the_first(self) -> None:
        # The first hit is a type annotation. The secret two lines down used to
        # go unreported because only the first match in a file was examined.
        source = 'def f(token: str) -> None:\n    pass\ntoken = "dummy-secret-value"\n'
        errors = secret_errors({"scripts/memory_manager.py": source})
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("scripts/memory_manager.py (line 3)", errors[0])

    def test_unquoted_non_expressions_and_quoted_literals_fail(self) -> None:
        for name, text in {
            "scripts/a.py": "token=dummy-secret-value\n",
            "scripts/b.py": '# password = "hunter2hunter2"\n',
            "docs/c.md": "password: hunter2hunter2\n",
        }.items():
            with self.subTest(name=name):
                self.assertEqual(len(secret_errors({name: text})), 1)


if __name__ == "__main__":
    unittest.main()
