"""Real process cohorts for the public save path and interrupted writers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config
import index_store
import kimi_mcp_server
import memory_manager
import storage
from store_lock import exclusive_lock


def wait_for(path: Path, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {path.name}")
        time.sleep(0.01)


def worker(folder: Path, number: int, mode: str) -> None:
    root = folder / "store"
    if mode == "interrupt":
        with storage.write_transaction(root):
            if storage.backend(root) == "sqlite":
                memory_manager.add_record("facts", "Uncommitted interrupted writer", root=root)
            (folder / "locked").write_text("ready", encoding="utf-8")
            wait_for(folder / "never", 60)
        return
    if mode == "rewrite_interrupt":
        replace = storage.os.replace

        def hold_replace(source, target):
            (folder / "locked").write_text("ready", encoding="utf-8")
            wait_for(folder / "never", 60)
            replace(source, target)

        storage.os.replace = hold_replace
        memory_manager.add_record_if_useful("facts", "Confirmed JSONL baseline", root=root)
        return
    submitted = json.loads((folder / "submissions.json").read_text(encoding="utf-8"))[number]
    # Widen the old check/insert race without synchronizing inside the lock.
    policy = memory_manager.write_policy
    target = policy if hasattr(policy, "find_related_write") else memory_manager.memory_hygiene
    name = "find_related_write" if hasattr(policy, "find_related_write") else "find_related_record"
    original = getattr(target, name)

    def slow_choice(*args, **kwargs):
        result = original(*args, **kwargs)
        time.sleep(0.08)
        return result

    setattr(target, name, slow_choice)
    (folder / f"ready-{number}").write_text("ready", encoding="utf-8")
    wait_for(folder / "go")
    started = time.monotonic()
    try:
        if mode == "idempotency":
            outcome = memory_manager.add_record_if_useful(
                "facts", submitted["content"], {"idempotency_key": "retry-one"}, root,
            )
            response = {"result": outcome["action"], "id": outcome["record"].id}
        else:
            response = kimi_mcp_server.call_save_insight({**submitted, "root": str(root)})
        response["seconds"] = time.monotonic() - started
    except Exception as exc:
        response = {"error": repr(exc), "seconds": time.monotonic() - started}
        raise
    finally:
        (folder / f"response-{number}.json").write_text(json.dumps(response, indent=2), encoding="utf-8")


class WriteConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        evidence = os.environ.get("RECALL_H04_EVIDENCE")
        if evidence:
            Path(evidence).mkdir(parents=True, exist_ok=True)
            self.folder = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=evidence))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.folder = Path(temporary.name)

    def prepare(self, folder: Path, backend: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        root = folder / "store"
        config.ensure_config(root)
        cfg = config.load_config(root)
        cfg["backend"] = backend
        config.save_config(cfg, root)
        storage.init_store(root)
        return root

    def start(self, folder: Path, number: int, mode: str) -> subprocess.Popen:
        stdout = (folder / f"worker-{mode}-{number}.stdout").open("w", encoding="utf-8")
        stderr = (folder / f"worker-{mode}-{number}.stderr").open("w", encoding="utf-8")
        try:
            return subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--worker", str(folder), str(number), mode],
                stdout=stdout, stderr=stderr,
            )
        finally:
            stdout.close()
            stderr.close()

    def cohort(self, backend: str, count: int, mode: str, repeat: int) -> None:
        folder = self.folder / f"{backend}-{mode}-{repeat}"
        root = self.prepare(folder, backend)
        baseline = memory_manager.add_record("risks", "Preserve the original baseline record.", root=root)
        submissions = [
            {"category": f"custom_{number}" if mode == "categories" else "facts", "content": (
                f"Unique fact {number}: component owns its isolated input {number}." if mode in {"distinct", "categories"}
                else "The project keeps the canonical memory store on local disk."
            )} for number in range(count)
        ]
        (folder / "submissions.json").write_text(json.dumps(submissions, indent=2), encoding="utf-8")
        (folder / "before.json").write_text(json.dumps([baseline.__dict__], indent=2), encoding="utf-8")
        processes = [self.start(folder, number, mode) for number in range(count)]
        try:
            for number in range(count):
                wait_for(folder / f"ready-{number}")
            (folder / "go").write_text("go", encoding="utf-8")
            exit_codes = [process.wait(timeout=30) for process in processes]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
        records = list(storage.iter_records(root))
        (folder / "after.json").write_text(json.dumps([record.__dict__ for record in records], indent=2), encoding="utf-8")
        self.assertEqual(exit_codes, [0] * count)
        responses = [json.loads((folder / f"response-{number}.json").read_text(encoding="utf-8")) for number in range(count)]
        by_id = {record.id: record for record in records}
        self.assertEqual(len(by_id), len(records), "ID collision")
        self.assertEqual(by_id[baseline.id], baseline)
        self.assertEqual(len(records), count + 1 if mode in {"distinct", "categories"} else 2)
        for submitted, response in zip(submissions, responses, strict=True):
            self.assertIn(response["id"], by_id, "Acknowledged save missing after reopen")
            self.assertEqual(by_id[response["id"]].content, submitted["content"])
            self.assertIn(response["result"], {"saved", "saved_related", "updated_existing", "ignored"})
        if mode not in {"distinct", "categories"}:
            self.assertEqual(len({response["id"] for response in responses}), 1)
        if mode == "same":
            saved = next(record for record in records if record.category == "facts")
            self.assertEqual(saved.metadata["confirmed_count"], count - 1)
            self.assertEqual(sum(response["result"] == "saved" for response in responses), 1)
            self.assertEqual(sum(response["result"] == "updated_existing" for response in responses), count - 1)
        rebuilt = memory_manager.rebuild_index(root)
        self.assertEqual(rebuilt["indexed_records"], len(records))
        self.assertEqual(set(index_store.load_index(root)), set(by_id))
        self.assertTrue(memory_manager.doctor(root)["index_complete"])
        if mode == "categories":
            self.assertTrue({item["category"] for item in submissions}.issubset(config.load_config(root)["categories"]))

    def test_distinct_save_cohorts(self) -> None:
        for backend in ("sqlite", "jsonl"):
            for repeat in range(3):
                with self.subTest(backend=backend, repeat=repeat):
                    self.cohort(backend, 12, "distinct", repeat)

    def test_same_save_cohorts(self) -> None:
        for backend in ("sqlite", "jsonl"):
            for repeat in range(3):
                with self.subTest(backend=backend, repeat=repeat):
                    self.cohort(backend, 8, "same", repeat)

    def test_explicit_idempotency_retry(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend):
                self.cohort(backend, 8, "idempotency", 0)

    def test_concurrent_custom_categories_survive(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend):
                self.cohort(backend, 12, "categories", 0)

    def test_first_saves_initialize_one_store(self) -> None:
        folder = self.folder / "cold-sqlite"
        folder.mkdir()
        submissions = [{"category": "architecture", "content": f"Cold store initial record {number}."} for number in range(12)]
        (folder / "submissions.json").write_text(json.dumps(submissions), encoding="utf-8")
        processes = [self.start(folder, number, "distinct") for number in range(12)]
        try:
            for number in range(12):
                wait_for(folder / f"ready-{number}")
            (folder / "go").write_text("go", encoding="utf-8")
            exit_codes = [process.wait(timeout=30) for process in processes]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
        records = list(storage.iter_records(folder / "store"))
        (folder / "after.json").write_text(json.dumps([record.__dict__ for record in records], indent=2), encoding="utf-8")
        self.assertEqual(exit_codes, [0] * 12)
        self.assertEqual(len(records), 12)
        by_id = {record.id: record for record in records}
        self.assertEqual(len(by_id), 12)
        for number, submitted in enumerate(submissions):
            response = json.loads((folder / f"response-{number}.json").read_text(encoding="utf-8"))
            self.assertEqual(by_id[response["id"]].content, submitted["content"])

    def test_jsonl_contention_has_a_bounded_error(self) -> None:
        folder = self.folder / "jsonl"
        root = self.prepare(folder, "jsonl")
        process = self.start(folder, 0, "interrupt")
        try:
            wait_for(folder / "locked")
            started = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "store is busy"):
                with exclusive_lock(config.memory_dir(root) / ".write.lock", timeout=0.1):
                    self.fail("A second process acquired the held lock")
            self.assertLess(time.monotonic() - started, 1)
        finally:
            process.kill()
            process.wait(timeout=10)

    def test_categories_and_scopes_stay_separate(self) -> None:
        for backend in ("sqlite", "jsonl"):
            root = self.prepare(self.folder / backend, backend)
            ids = []
            for category, scope in (("facts", "all"), ("decisions", "all"), ("facts", "codex"), ("facts", "claude")):
                arguments = {"root": str(root), "category": category, "content": "The project uses Python for its storage layer.", "applies_to_provider": scope}
                response = kimi_mcp_server.call_save_insight(arguments)
                ids.append(response["id"])
                retry = kimi_mcp_server.call_save_insight(arguments)
                self.assertEqual(retry["id"], response["id"])
            self.assertEqual(len(set(ids)), 4)
            self.assertEqual(len(list(storage.iter_records(root))), 4)

    def test_interrupted_writer_releases_exclusion(self) -> None:
        for backend in ("sqlite", "jsonl"):
            folder = self.folder / backend
            root = self.prepare(folder, backend)
            baseline = memory_manager.add_record("facts", "Preserve committed baseline", root=root)
            process = self.start(folder, 0, "interrupt")
            try:
                wait_for(folder / "locked")
            finally:
                process.kill()
                process.wait(timeout=10)
            self.assertEqual(storage.get_record(baseline.id, root), baseline)
            started = time.monotonic()
            result = memory_manager.add_record_if_useful("facts", "Later writer can save after interruption", root=root)
            self.assertLess(time.monotonic() - started, 10)
            self.assertEqual(result["action"], "saved")
            self.assertEqual(len(list(storage.iter_records(root))), 2)

    def test_interrupted_jsonl_confirmation_preserves_original(self) -> None:
        folder = self.folder / "jsonl"
        root = self.prepare(folder, "jsonl")
        baseline = memory_manager.add_record_if_useful("facts", "Confirmed JSONL baseline", root=root)["record"]
        process = self.start(folder, 0, "rewrite_interrupt")
        try:
            wait_for(folder / "locked")
        finally:
            process.kill()
            process.wait(timeout=10)
        self.assertEqual(storage.get_record(baseline.id, root), baseline)
        retry = memory_manager.add_record_if_useful("facts", "Confirmed JSONL baseline", root=root)
        self.assertEqual(retry["record"].id, baseline.id)
        self.assertEqual(retry["record"].metadata["confirmed_count"], 1)
        self.assertEqual(len(list(storage.iter_records(root))), 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        unittest.main()
