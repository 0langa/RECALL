"""MCP surface: lifecycle tools, hygiene tool, contract exposure, save teaching."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import index_store  # noqa: E402
import kimi_mcp_server as server  # noqa: E402
import config  # noqa: E402
import memory_manager  # noqa: E402
import memory_hygiene  # noqa: E402


def call_tool(name: str, arguments: dict) -> dict:
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )
    if "error" in response:
        raise AssertionError(f"tool {name} errored: {response['error']}")
    return json.loads(response["result"]["content"][0]["text"])


def call_tool_direct(name: str, arguments: dict) -> dict:
    return server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )


class McpSurfaceTests(unittest.TestCase):
    def test_tools_list_exposes_full_lifecycle(self) -> None:
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "retrieve_memory",
                "context_packet",
                "save_insight",
                "review_memory",
                "update_memory",
                "memory_hygiene",
                "memory_contract",
                "initialize_project",
            },
        )

    def test_initialize_returns_contract_instructions(self) -> None:
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        result = response["result"]
        self.assertIn("Authority order", result["instructions"])
        self.assertIn("retrieve_memory", result["instructions"])

    def test_memory_contract_tool_returns_lifecycle_and_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = call_tool("memory_contract", {"root": tmp})
            self.assertEqual(payload["contract"]["authority_order"][0], "current user instruction")
            self.assertIn("tooling_quirks", payload["categories"])
            self.assertIn("update_rule", payload["categories"]["commands"])


class McpSaveTests(unittest.TestCase):
    def test_explicit_retry_key_preserves_one_acknowledged_public_save(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = config.default_config()
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                first = call_tool("save_insight", {
                    "root": tmp, "category": "decisions",
                    "content": "Use SQLite as the durable project database.",
                    "idempotency_key": "release-test-save-1",
                })
                retry = call_tool("save_insight", {
                    "root": tmp, "category": "decisions",
                    "content": "Deploy the command runner on a dedicated Windows host.",
                    "idempotency_key": "release-test-save-1",
                })
                self.assertEqual(retry["id"], first["id"])
                self.assertEqual(retry["reason"], "idempotent_replay")
                records = list(memory_manager.iter_records(tmp))
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].content, "Use SQLite as the durable project database.")

    def test_save_insight_rejects_secret_shaped_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "commands",
                    "content": "Deploy token = sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX",
                },
            )
            self.assertEqual(payload["result"], "rejected")
            self.assertIn("secret", payload["reason"])
            self.assertIn("next_action", payload)
            retrieved = call_tool("retrieve_memory", {"root": tmp, "query_text": "deploy token"})
            self.assertEqual(retrieved["results"], [])

    def test_duplicate_save_confirms_existing_instead_of_appending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Use SQLite as the default backend."},
            )
            self.assertEqual(first["result"], "saved")
            second = call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Use SQLite as the default backend."},
            )
            self.assertEqual(second["result"], "updated_existing")
            self.assertEqual(second["id"], first["id"])
            self.assertIn("update_memory", second["next_action"])

    def test_save_preserves_significant_claim_whitespace_on_both_backends_and_orders(self) -> None:
        content = "Release notes location for the current project."
        single_space = "docs/release notes.md"
        double_space = "docs/release  notes.md"
        for backend in ("sqlite", "jsonl"):
            for values in ((single_space, double_space), (double_space, single_space)):
                with self.subTest(backend=backend, values=values), tempfile.TemporaryDirectory() as tmp:
                    cfg = config.default_config()
                    cfg["backend"] = backend
                    config.save_config(cfg, tmp)
                    saved_by_value = {}
                    for value in values:
                        saved_by_value[value] = call_tool(
                            "save_insight",
                            {
                                "root": tmp,
                                "category": "requirements",
                                "content": content,
                                "summary": content,
                                "details": f"The release path is {value}.",
                                "source": "fixture",
                                "status": "validated",
                                "confidence": 0.9,
                                "claim_key": "release.path",
                                "claim_value": value,
                            },
                        )

                    self.assertEqual(len({item["id"] for item in saved_by_value.values()}), 2)
                    self.assertEqual(
                        {
                            memory_manager.get_record(item["id"], tmp).metadata["claim_value"]
                            for item in saved_by_value.values()
                        },
                        {single_space, double_space},
                    )

                    for value in values:
                        replay = call_tool(
                            "save_insight",
                            {
                                "root": tmp,
                                "category": "requirements",
                                "content": content,
                                "summary": content,
                                "details": f"The release path is {value}.",
                                "source": "fixture",
                                "status": "validated",
                                "confidence": 0.9,
                                "claim_key": "release.path",
                                "claim_value": value,
                            },
                        )
                        self.assertEqual(replay["result"], "updated_existing")
                        self.assertEqual(replay["id"], saved_by_value[value]["id"])

                    plan = call_tool(
                        "memory_hygiene",
                        {"root": tmp, "mode": "plan", "claim_key": "release.path"},
                    )
                    conflicts = [
                        proposal
                        for proposal in plan["proposals"]
                        if proposal["proposed_action"] == "review_claim_conflict"
                    ]
                    self.assertEqual(len(conflicts), 1)
                    self.assertEqual(conflicts[0]["details"]["values"], [double_space, single_space])
                    self.assertFalse(conflicts[0]["safe_to_apply"])

    def test_retrieve_memory_is_compact_by_default_and_verbose_on_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Use SQLite as the default backend."},
            )
            compact = call_tool("retrieve_memory", {"root": tmp, "query_text": "default backend"})
            self.assertNotIn("metadata", compact["results"][0])
            self.assertIn("flag", compact["results"][0])
            verbose = call_tool("retrieve_memory", {"root": tmp, "query_text": "default backend", "verbose": True})
            self.assertIn("metadata", verbose["results"][0])

    def test_preference_save_without_evidence_teaches_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ignored = call_tool(
                "save_insight",
                {"root": tmp, "category": "preferences", "content": "User prefers tabs over spaces."},
            )
            self.assertEqual(ignored["result"], "ignored")
            self.assertIn("preference_evidence_type", ignored["next_action"])

            saved = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "preferences",
                    "content": "User prefers tabs over spaces.",
                    "preference_key": "indentation",
                    "preference_evidence_type": "explicit_declaration",
                },
            )
            self.assertEqual(saved["result"], "saved")


class McpLifecycleTests(unittest.TestCase):
    def test_invalid_edit_preserves_entire_record_on_both_backends(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = config.default_config()
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                rid = call_tool("save_insight", {"root": tmp, "category": "requirements",
                                                "content": "Release notes live in docs/old.md.",
                                                "claim_key": "release_notes.path", "claim_value": "docs/old.md"})["id"]
                call_tool("update_memory", {"root": tmp, "op": "confirm", "id": rid})
                before = memory_manager.get_record(rid, tmp)
                for invalid in ({"claim_key": "release_notes.path"}, {"claim_value": "docs/new.md"},
                                {"claim_key": " ", "claim_value": "docs/new.md"},
                                {"clear_claim": True, "claim_key": "release_notes.path", "claim_value": "docs/new.md"}):
                    response = call_tool_direct("update_memory", {"root": tmp, "op": "update", "id": rid,
                                                                 "content": "Release notes moved.", **invalid})
                    self.assertIn("error", response)
                    self.assertEqual(memory_manager.get_record(rid, tmp), before)

    def test_edit_revision_coherence_on_both_backends(self) -> None:
        old = "Release notes live in docs/old.md."
        new = "Release notes live in docs/new.md."
        cases = {
            "content_only": {"content": new},
            "empty_display": {"content": new, "summary": "", "details": ""},
            "summary_only": {"summary": "Release notes location requires review."},
            "details_only": {"details": "Release notes location requires review."},
            "replacement": {"content": new, "summary": new, "details": new,
                            "claim_key": "release_notes.path", "claim_value": "docs/new.md"},
            "claim_only": {"claim_key": "release_notes.path", "claim_value": "docs/new.md"},
            "clear": {"clear_claim": True},
            "noop": {"content": old, "summary": old, "details": old,
                     "claim_key": "release_notes.path", "claim_value": "docs/old.md"},
        }
        evidence_keys = ("confirmed_count", "confirmation_sessions", "last_confirmed", "validated_at", "trust")
        for backend in ("sqlite", "jsonl"):
            for case, changes in cases.items():
                with self.subTest(backend=backend, case=case), tempfile.TemporaryDirectory() as tmp:
                    cfg = config.default_config()
                    cfg["backend"] = backend
                    config.save_config(cfg, tmp)
                    seed = {"root": tmp, "category": "requirements", "content": old, "summary": old,
                            "details": old, "claim_key": "release_notes.path", "claim_value": "docs/old.md"}
                    rid = call_tool("save_insight", {**seed, "source_session": "old-A"})["id"]
                    call_tool("save_insight", {**seed, "source_session": "old-A"})
                    call_tool("save_insight", {**seed, "source_session": "old-B"})
                    before = memory_manager.get_record(rid, tmp)
                    self.assertEqual(before.metadata["status"], "validated")
                    result = call_tool("update_memory", {"root": tmp, "op": "update", "id": rid, **changes})
                    index_store.rebuild(tmp)
                    after = memory_manager.get_record(rid, tmp)
                    self.assertEqual(result["record"]["metadata"], after.metadata)
                    self.assertEqual(after.content, changes.get("content", old))
                    self.assertEqual(after.metadata["recall_fingerprint"],
                                     memory_hygiene.content_fingerprint(after.category, after.content, after.metadata))
                    if case == "noop":
                        for key in evidence_keys:
                            self.assertEqual(after.metadata[key], before.metadata[key])
                        self.assertNotIn("verification_invalidated_at", after.metadata)
                        continue
                    self.assertEqual(after.metadata["status"], "active")
                    self.assertLessEqual(after.metadata["trust"], 0.5)
                    for key in evidence_keys[:-1]:
                        self.assertNotIn(key, after.metadata)
                        self.assertEqual(after.metadata["verification_history"][-1][key], before.metadata[key])
                    self.assertEqual(after.metadata["verification_history"][-1]["trust"], before.metadata["trust"])
                    self.assertIn("verification_invalidated_at", after.metadata)
                    if case in ("content_only", "empty_display"):
                        self.assertNotIn("summary", after.metadata)
                        self.assertNotIn("details", after.metadata)
                        packet = call_tool("context_packet", {"root": tmp, "query_text": "release notes"})
                        self.assertNotIn("docs/old.md", json.dumps(packet))
                        self.assertIn(new, json.dumps(packet))
                        review = call_tool("review_memory", {"root": tmp})
                        self.assertEqual(review["memories"][0]["summary"], new)
                    for key in ("summary", "details"):
                        if case == key + "_only":
                            self.assertEqual(after.metadata[key], changes[key])
                            other = "details" if key == "summary" else "summary"
                            self.assertEqual(after.metadata[other], old)
                    expected_claim = "docs/new.md" if case in ("replacement", "claim_only") else None
                    self.assertEqual(after.metadata.get("claim_value"), expected_claim)
                    retrieved = call_tool("retrieve_memory", {"root": tmp, "query_text": "release notes"})
                    self.assertEqual(retrieved["results"][0]["flag"], "needs_verification")
                    assigned = call_tool("update_memory", {"root": tmp, "op": "update", "id": rid,
                                                           "status": "validated"})
                    self.assertEqual(assigned["record"]["status"], "active")
                    first = memory_manager.confirm_record(rid, tmp, source_session="fresh-C")
                    self.assertEqual(first.metadata["confirmed_count"], 1)
                    self.assertEqual(first.metadata["confirmation_sessions"], ["fresh-C"])
                    self.assertEqual(first.metadata["status"], "active")
                    self.assertIn("verification_invalidated_at", first.metadata)
                    repeated = memory_manager.confirm_record(rid, tmp, source_session="fresh-C")
                    self.assertEqual(repeated.metadata["confirmed_count"], 1)
                    confirmed = call_tool("update_memory", {"root": tmp, "op": "confirm", "id": rid})
                    self.assertEqual(confirmed["record"]["status"], "validated")
                    self.assertNotIn("verification_invalidated_at", confirmed["record"]["metadata"])
                    self.assertEqual(confirmed["record"]["metadata"]["verification_history"],
                                     after.metadata["verification_history"])

    def test_save_after_edit_uses_current_identity(self) -> None:
        for backend in ("sqlite", "jsonl"):
            for dimension in ("content", "category", "tags", "source", "status"):
                with self.subTest(backend=backend, dimension=dimension), tempfile.TemporaryDirectory() as tmp:
                    cfg = config.default_config()
                    cfg["backend"] = backend
                    config.save_config(cfg, tmp)
                    old = "Release notes live in docs/old.md."
                    rid = call_tool("save_insight", {"root": tmp, "category": "requirements", "content": old})["id"]
                    changes = {"content": "Release notes live in docs/new.md.", "category": "decisions",
                               "tags": ["release"], "source": "fixture", "status": "hypothesis"}
                    edited = memory_manager.edit_record(rid, tmp, **{dimension: changes[dimension]})
                    self.assertEqual(edited.metadata["recall_fingerprint"],
                                     memory_hygiene.content_fingerprint(edited.category, edited.content, edited.metadata))
                    if dimension == "content":
                        replay = call_tool("save_insight", {"root": tmp, "category": "requirements", "content": old})
                        self.assertNotEqual(replay["id"], rid)
                        self.assertNotEqual(replay["result"], "updated_existing")
                        self.assertEqual(memory_manager.get_record(rid, tmp).metadata, edited.metadata)
                    # Match the declared fingerprint inputs, including status and tags.
                    metadata = {key: edited.metadata[key] for key in ("status", "source", "tags")
                                if key in edited.metadata}
                    saved = memory_manager.add_record_if_useful(edited.category, edited.content, metadata, tmp)
                    self.assertEqual(saved["action"], "updated_existing")
                    self.assertEqual(saved["record"].id, rid)
                    current = saved["record"]
                    self.assertEqual(current.metadata["recall_fingerprint"],
                                     memory_hygiene.content_fingerprint(current.category, current.content, current.metadata))

    def test_update_memory_supports_deprecate_supersede_and_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = call_tool(
                "save_insight",
                {"root": tmp, "category": "architecture", "content": "Hooks poll for changes every second."},
            )
            new = call_tool(
                "save_insight",
                {"root": tmp, "category": "architecture", "content": "Hooks are event-driven via provider events."},
            )
            superseded = call_tool(
                "update_memory",
                {"root": tmp, "op": "supersede", "id": old["id"], "new_id": new["id"], "note": "Design changed."},
            )
            self.assertEqual(superseded["old"]["status"], "superseded")

            wrong = call_tool(
                "save_insight",
                {"root": tmp, "category": "commands", "content": "Run build with make all."},
            )
            deprecated = call_tool(
                "update_memory",
                {"root": tmp, "op": "deprecate", "id": wrong["id"], "note": "Makefile was removed."},
            )
            self.assertEqual(deprecated["record"]["status"], "deprecated")

            confirmed = call_tool("update_memory", {"root": tmp, "op": "confirm", "id": new["id"]})
            self.assertEqual(confirmed["result"], "ok")

    def test_update_memory_update_rejects_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = call_tool(
                "save_insight",
                {"root": tmp, "category": "commands", "content": "Deploy runs through the CI pipeline."},
            )
            rejected = call_tool(
                "update_memory",
                {
                    "root": tmp,
                    "op": "update",
                    "id": record["id"],
                    "content": "Deploy with password = hunter2secret",
                },
            )
            self.assertEqual(rejected["result"], "rejected")

    def test_update_memory_supersede_without_new_id_explains_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Old decision to replace."},
            )
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {"name": "update_memory", "arguments": {"root": tmp, "op": "supersede", "id": record["id"]}},
                }
            )
            self.assertIn("error", response)
            self.assertIn("save_insight", response["error"]["message"])

    def test_update_memory_update_clears_stale_claim_and_proposed_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "requirements",
                    "content": "Release notes live in docs/old.md.",
                    "status": "active",
                    "summary": "Release notes path is docs/old.md.",
                    "claim_key": "release_notes.path",
                    "claim_value": "docs/old.md",
                },
            )
            updated = call_tool(
                "update_memory",
                {
                    "root": tmp,
                    "op": "update",
                    "id": saved["id"],
                    "content": "Release notes live in docs/new.md.",
                    "summary": "Release notes path is docs/new.md.",
                    "status": "validated",
                },
            )
            index_store.rebuild(tmp)
            record = call_tool(
                "retrieve_memory",
                {"root": tmp, "query_text": "Release notes path is docs/new.md.", "verbose": True},
            )
            old_record = call_tool(
                "retrieve_memory",
                {"root": tmp, "query_text": "Release notes path is docs/old.md.", "verbose": True},
            )
            review = call_tool(
                "review_memory",
                {"root": tmp, "category": ["requirements"], "limit": 10},
            )
            plan = call_tool(
                "memory_hygiene",
                {"root": tmp, "mode": "plan", "claim_key": "release_notes.path"},
            )

            self.assertEqual(updated["record"]["metadata"].get("status"), "active")
            self.assertEqual(updated["record"]["content"], "Release notes live in docs/new.md.")
            self.assertNotIn("claim_key", updated["record"]["metadata"])
            self.assertNotIn("claim_value", updated["record"]["metadata"])
            self.assertEqual(record["results"][0]["id"], saved["id"])
            self.assertTrue(all(item["content"] != "Release notes live in docs/old.md." for item in old_record["results"]))
            self.assertNotIn("claim_key", record["results"][0]["metadata"])
            self.assertEqual(review["memories"][0]["summary"], "Release notes path is docs/new.md.")
            self.assertEqual(plan["action"], "reconcile-current-truth")
            self.assertFalse(any(item.get("details", {}).get("claim_key") == "release_notes.path" for item in plan["proposals"]))

    def test_update_memory_update_can_explicitly_replace_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "requirements",
                    "content": "Release notes live in docs/old.md.",
                    "status": "active",
                    "summary": "Release notes path is docs/old.md.",
                    "claim_key": "release_notes.path",
                    "claim_value": "docs/old.md",
                },
            )
            updated = call_tool(
                "update_memory",
                {
                    "root": tmp,
                    "op": "update",
                    "id": saved["id"],
                    "content": "Release notes live in docs/new.md.",
                    "summary": "Release notes path is docs/new.md.",
                    "claim_key": "release_notes.path",
                    "claim_value": "docs/new.md",
                },
            )
            detail = call_tool(
                "retrieve_memory",
                {"root": tmp, "query_text": "Release notes path is docs/new.md.", "verbose": True},
            )

            self.assertEqual(updated["record"]["metadata"]["claim_key"], "release_notes.path")
            self.assertEqual(updated["record"]["metadata"]["claim_value"], "docs/new.md")
            self.assertEqual(updated["record"]["content"], "Release notes live in docs/new.md.")
            self.assertEqual(detail["results"][0]["metadata"]["claim_key"], "release_notes.path")
            self.assertEqual(detail["results"][0]["metadata"]["claim_value"], "docs/new.md")

    def test_update_memory_update_can_explicitly_clear_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "requirements",
                    "content": "Release notes live in docs/new.md.",
                    "claim_key": "release_notes.path",
                    "claim_value": "docs/new.md",
                },
            )

            updated = call_tool(
                "update_memory",
                {"root": tmp, "op": "update", "id": saved["id"], "clear_claim": True},
            )

            self.assertNotIn("claim_key", updated["record"]["metadata"])
            self.assertNotIn("claim_value", updated["record"]["metadata"])

    def test_update_memory_update_invalid_claim_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "requirements",
                    "content": "Release notes live in docs/old.md.",
                    "claim_key": "release_notes.path",
                    "claim_value": "docs/old.md",
                },
            )
            response = call_tool_direct(
                "update_memory",
                {
                    "root": tmp,
                    "op": "update",
                    "id": saved["id"],
                    "claim_key": "release_notes.path",
                    "content": "Release notes path is docs/new.md.",
                },
            )
            unchanged = call_tool(
                "retrieve_memory",
                {"root": tmp, "query_text": "Release notes live in docs/old.md.", "verbose": True},
            )

            self.assertIn("error", response)
            self.assertEqual(unchanged["results"][0]["content"], "Release notes live in docs/old.md.")
            self.assertEqual(unchanged["results"][0]["metadata"]["claim_value"], "docs/old.md")


class McpHygieneTests(unittest.TestCase):
    def test_hygiene_route_scan_and_apply_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            routed = call_tool(
                "memory_hygiene",
                {"root": tmp, "mode": "route", "text": "temporary scratch note for this task only"},
            )
            self.assertEqual(routed["route"], "current_chat_only")

            secret_route = call_tool(
                "memory_hygiene",
                {"root": tmp, "mode": "route", "text": "api_key = sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX"},
            )
            self.assertEqual(secret_route["route"], "reject")

            call_tool("save_insight", {"root": tmp, "category": "decisions", "content": "Keep memory local-first."})
            scan = call_tool("memory_hygiene", {"root": tmp, "mode": "scan"})
            self.assertEqual(scan["action"], "hygiene-scan")
            applied = call_tool("memory_hygiene", {"root": tmp, "mode": "apply_safe"})
            self.assertEqual(applied["action"], "hygiene-apply")

    def test_safe_hygiene_keeps_same_text_conflicts_on_both_backends_and_orders(self) -> None:
        for backend in ("sqlite", "jsonl"):
            for values in (
                ("docs/verified.md", "docs/guess.md"),
                ("docs/guess.md", "docs/verified.md"),
            ):
                with self.subTest(backend=backend, values=values), tempfile.TemporaryDirectory() as tmp:
                    cfg = config.default_config()
                    cfg["backend"] = backend
                    config.save_config(cfg, tmp)
                    created = []
                    for value in values:
                        metadata = memory_manager.build_card_metadata(
                            source="fixture",
                            status="validated",
                            confidence=0.9,
                            summary="Release notes location for the current project.",
                            details=f"The release path is {value}.",
                            base={
                                "claim_key": "release.path",
                                "claim_value": value,
                                "recall_fingerprint": "legacy-shared-fingerprint",
                                "trust": 0.9,
                            },
                        )
                        created.append(
                            memory_manager.add_record(
                                "requirements",
                                "Release notes location for the current project.",
                                metadata,
                                tmp,
                            )
                        )
                    before = [memory_manager.get_record(record.id, tmp) for record in created]
                    record_ids = {record.id for record in created}

                    plan = call_tool("memory_hygiene", {"root": tmp, "mode": "plan"})
                    applied = call_tool("memory_hygiene", {"root": tmp, "mode": "apply_safe"})
                    after = [memory_manager.get_record(record.id, tmp) for record in created]
                    fresh_plan = call_tool("memory_hygiene", {"root": tmp, "mode": "plan"})
                    retrieved = call_tool(
                        "retrieve_memory",
                        {
                            "root": tmp,
                            "query_text": "release notes location current project",
                            "verbose": True,
                        },
                    )
                    conflicts = [
                        proposal
                        for proposal in plan["proposals"]
                        if proposal["proposed_action"] == "review_claim_conflict"
                    ]

                    self.assertEqual(len(conflicts), 1)
                    self.assertEqual(set(conflicts[0]["details"]["record_ids"]), record_ids)
                    self.assertFalse(
                        any(
                            proposal["proposed_action"] == "merge"
                            and (
                                proposal["id"] in record_ids
                                or bool(record_ids.intersection(proposal.get("related_ids", [])))
                            )
                            for proposal in plan["proposals"]
                        )
                    )
                    self.assertEqual(applied["applied_count"], 0)
                    self.assertEqual(applied["unresolved_conflicts"], conflicts)
                    self.assertEqual(after, before)
                    self.assertTrue(
                        any(
                            proposal["proposed_action"] == "review_claim_conflict"
                            for proposal in fresh_plan["proposals"]
                        )
                    )
                    self.assertEqual({item["id"] for item in retrieved["results"]}, record_ids)
                    self.assertEqual(
                        {item["metadata"]["claim_value"] for item in retrieved["results"]},
                        {"docs/guess.md", "docs/verified.md"},
                    )
                    self.assertTrue(all(item["flag"] == "conflicting" for item in retrieved["results"]))

    def test_safe_hygiene_keeps_significant_whitespace_groups_until_explicit_supersession(self) -> None:
        content = "Release notes location for the current project."
        single_space = "docs/release notes.md"
        double_space = "docs/release  notes.md"
        for backend in ("sqlite", "jsonl"):
            for values in (
                (single_space, double_space, single_space, double_space),
                (double_space, single_space, double_space, single_space),
            ):
                with self.subTest(backend=backend, values=values), tempfile.TemporaryDirectory() as tmp:
                    cfg = config.default_config()
                    cfg["backend"] = backend
                    config.save_config(cfg, tmp)
                    created = []
                    for value in values:
                        metadata = memory_manager.build_card_metadata(
                            source="fixture",
                            status="validated",
                            confidence=0.9,
                            summary=content,
                            details=f"The release path is {value}.",
                            base={
                                "claim_key": "release.path",
                                "claim_value": value,
                                "recall_fingerprint": "legacy-shared-fingerprint",
                                "trust": 0.9,
                            },
                        )
                        created.append(memory_manager.add_record("requirements", content, metadata, tmp))
                    by_id = {record.id: record for record in created}

                    plan = call_tool("memory_hygiene", {"root": tmp, "mode": "plan"})
                    merges = [
                        proposal for proposal in plan["proposals"] if proposal["proposed_action"] == "merge"
                    ]
                    conflicts = [
                        proposal
                        for proposal in plan["proposals"]
                        if proposal["proposed_action"] == "review_claim_conflict"
                    ]

                    self.assertEqual(len(merges), 2)
                    for merge in merges:
                        self.assertEqual(
                            by_id[merge["id"]].metadata["claim_value"],
                            by_id[merge["related_ids"][0]].metadata["claim_value"],
                        )
                    self.assertEqual(len(conflicts), 1)
                    self.assertEqual(set(conflicts[0]["details"]["record_ids"]), set(by_id))
                    self.assertEqual(conflicts[0]["details"]["values"], [double_space, single_space])

                    applied = call_tool("memory_hygiene", {"root": tmp, "mode": "apply_safe"})
                    reopened = [memory_manager.get_record(record.id, tmp) for record in created]
                    current = [
                        record
                        for record in reopened
                        if record.metadata.get("status", "active") in memory_hygiene.CURRENT_STATUSES
                    ]
                    current_by_value = {record.metadata["claim_value"]: record for record in current}
                    fresh_plan = call_tool("memory_hygiene", {"root": tmp, "mode": "plan"})
                    retrieved = call_tool(
                        "retrieve_memory",
                        {"root": tmp, "query_text": content, "verbose": True},
                    )

                    self.assertEqual(applied["applied_count"], 2)
                    self.assertEqual(len(applied["unresolved_conflicts"]), 1)
                    self.assertEqual(set(current_by_value), {single_space, double_space})
                    self.assertFalse(
                        any(
                            proposal["proposed_action"] == "merge"
                            for proposal in fresh_plan["proposals"]
                        )
                    )
                    self.assertTrue(
                        any(
                            proposal["proposed_action"] == "review_claim_conflict"
                            for proposal in fresh_plan["proposals"]
                        )
                    )
                    self.assertEqual(
                        {item["metadata"]["claim_value"] for item in retrieved["results"]},
                        {single_space, double_space},
                    )
                    self.assertTrue(all(item["flag"] == "conflicting" for item in retrieved["results"]))

                    reason = "Checked both distinct release-note files; the single-space path is current."
                    resolved = call_tool(
                        "update_memory",
                        {
                            "root": tmp,
                            "op": "supersede",
                            "id": current_by_value[double_space].id,
                            "new_id": current_by_value[single_space].id,
                            "note": reason,
                        },
                    )
                    reopened_old = memory_manager.get_record(current_by_value[double_space].id, tmp)
                    reopened_new = memory_manager.get_record(current_by_value[single_space].id, tmp)
                    after = call_tool(
                        "retrieve_memory",
                        {"root": tmp, "query_text": content, "verbose": True},
                    )

                    self.assertEqual(resolved["result"], "superseded")
                    self.assertEqual(reopened_old.metadata["lifecycle_note"], reason)
                    self.assertEqual(reopened_old.metadata["superseded_by"], reopened_new.id)
                    self.assertIn(reopened_old.id, reopened_new.metadata["supersedes"])
                    self.assertEqual([item["id"] for item in after["results"]], [reopened_new.id])
                    self.assertEqual(after["results"][0]["metadata"]["claim_value"], single_space)

    def test_hygiene_handler_keeps_claim_conflict_unresolved_until_explicit_supersede(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "release.toml"
            fixture.write_text('path = "docs/verified.md"\n', encoding="utf-8")
            supported = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "requirements",
                    "content": "Primary release path is docs/verified.md.",
                    "status": "validated",
                    "confidence": 0.9,
                    "claim_key": "release.path",
                    "claim_value": "docs/verified.md",
                },
            )
            unsupported = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "requirements",
                    "content": "Primary release path is docs/guess.md.",
                    "status": "validated",
                    "confidence": 0.99,
                    "claim_key": "release.path",
                    "claim_value": "docs/guess.md",
                },
            )

            plan = call_tool("memory_hygiene", {"root": tmp, "mode": "plan", "claim_key": "release.path"})
            applied = call_tool("memory_hygiene", {"root": tmp, "mode": "apply_safe"})
            current = call_tool(
                "retrieve_memory",
                {"root": tmp, "query_text": "Primary release path", "verbose": True},
            )
            proposal = plan["proposals"][0]

            self.assertEqual(proposal["proposed_action"], "review_claim_conflict")
            self.assertEqual(proposal["details"]["resolution"], "review_required")
            self.assertNotIn("winner_id", proposal["details"])
            self.assertFalse(proposal["safe_to_apply"])
            self.assertEqual(applied["applied_count"], 0)
            self.assertEqual(applied["unresolved_conflicts"], [proposal])
            self.assertEqual({item["id"] for item in current["results"]}, {supported["id"], unsupported["id"]})
            self.assertTrue(all(item["flag"] == "conflicting" for item in current["results"]))

            checked = fixture.read_text(encoding="utf-8")
            self.assertIn("docs/verified.md", checked)
            reason = "Checked release.toml: path is docs/verified.md."
            resolved = call_tool(
                "update_memory",
                {
                    "root": tmp,
                    "op": "supersede",
                    "id": unsupported["id"],
                    "new_id": supported["id"],
                    "note": reason,
                },
            )
            reopened_old = memory_manager.get_record(unsupported["id"], tmp)
            reopened_new = memory_manager.get_record(supported["id"], tmp)
            after = call_tool(
                "retrieve_memory",
                {"root": tmp, "query_text": "Primary release path", "verbose": True},
            )

            self.assertEqual(resolved["result"], "superseded")
            self.assertEqual(reopened_old.metadata["lifecycle_note"], reason)
            self.assertEqual(reopened_old.metadata["superseded_by"], supported["id"])
            self.assertIn(unsupported["id"], reopened_new.metadata["supersedes"])
            self.assertEqual([item["id"] for item in after["results"]], [supported["id"]])
            self.assertEqual(after["results"][0]["flag"], "current")


class McpInitTests(unittest.TestCase):
    def test_initialize_project_creates_config_gitignore_and_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            payload = call_tool("initialize_project", {"root": tmp})
            self.assertTrue(payload["activation"]["enabled"])
            self.assertIn(".recall/", payload["gitignore"]["added"])
            self.assertIn("tooling_quirks", payload["categories"])
            self.assertIn("Authority order", payload["contract"])
            self.assertIn("retrieve_memory", payload["first_workflow"])
            gitignore = (Path(tmp) / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".recall/", gitignore)

            # Re-run is idempotent for gitignore entries.
            payload_again = call_tool("initialize_project", {"root": tmp})
            self.assertEqual(payload_again["gitignore"]["added"], [])


if __name__ == "__main__":
    unittest.main()
