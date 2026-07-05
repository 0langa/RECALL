#!/usr/bin/env python3
"""Narrow adapter used by bundled RECALL skills.

This is the public skill execution surface for the stdlib V1 plugin. The
lower-level memory_manager module remains the internal backend used by hooks,
tests, and support diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import config as recall_config
import corpus_migration
import memory_hygiene
import memory_noise
import memory_review
import memory_manager
import security
from models import ContextPacketRequest, ReviewRequest
from services.health_service import review_memory
from services import provenance_service
from services import lifecycle_service
from services.context_service import build_context_packet
from services import recovery_service
from services.finalizer_service import apply_finalizer_batch


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_json_card(*, file_path: str | None, use_stdin: bool) -> dict[str, Any]:
    if bool(file_path) == use_stdin:
        raise ValueError("save-turn-card requires exactly one of --file or --stdin.")
    raw = sys.stdin.read() if use_stdin else Path(str(file_path)).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"turn card JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("turn card JSON must be an object.")
    return payload


def load_stdin_object() -> dict[str, Any]:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("stdin JSON must be an object.")
    return payload


def string_value(
    payload: dict[str, Any],
    name: str,
    *,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    value = payload.get(name, default)
    if value is None:
        if required:
            raise ValueError(f"turn card is missing required field: {name}")
        return None
    if not isinstance(value, str):
        raise ValueError(f"turn card field {name} must be a string.")
    cleaned = value.strip()
    if required and not cleaned:
        raise ValueError(f"turn card field {name} must not be empty.")
    return cleaned or None


def float_value(payload: dict[str, Any], name: str) -> float | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ValueError(f"turn card field {name} must be a number.")
    return float(value)


def list_value(payload: dict[str, Any], name: str) -> list[str]:
    value = payload.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"turn card field {name} must be a list of strings.")
    return [item for item in value if item.strip()]


def reject_secret_like_text(*values: str | None) -> None:
    for value in values:
        if value and memory_manager.redact_secrets(value) != value:
            raise ValueError("turn card contains secret-like text and was not stored.")


def save_turn_card(card: dict[str, Any], root: Path | None) -> dict[str, Any]:
    category = string_value(card, "category", required=True)
    content = string_value(card, "content", required=True)
    summary = string_value(card, "summary", required=True)
    details = string_value(card, "details")
    status = string_value(card, "status", default="active")
    source = string_value(card, "source", default="finalizer")
    tags = list_value(card, "tags")
    importance = float_value(card, "importance")
    confidence = float_value(card, "confidence")
    reject_secret_like_text(content, summary, details)

    metadata_base: dict[str, Any] = {
        "schema": "recall.turn_card.v1",
        "capture_reason": string_value(card, "capture_reason"),
        "session_id": string_value(card, "session_id"),
        "turn_id": string_value(card, "turn_id"),
        "evidence_ids": list_value(card, "evidence_ids"),
    }
    metadata_base.update(
        memory_manager.provider_metadata(
            origin_provider=string_value(card, "origin_provider"),
            origin_agent=string_value(card, "origin_agent"),
            source_session=string_value(card, "source_session") or string_value(card, "session_id"),
            source_turn=string_value(card, "source_turn") or string_value(card, "turn_id"),
            cwd=string_value(card, "cwd"),
            branch=string_value(card, "branch"),
            commit=string_value(card, "commit"),
            capture_channel=string_value(card, "capture_channel") or source,
            applies_to_provider=string_value(card, "applies_to_provider"),
        )
    )
    metadata = memory_manager.build_card_metadata(
        summary=summary,
        details=details,
        tags=tags,
        source=source,
        status=status,
        importance=importance,
        confidence=confidence,
        base={key: value for key, value in metadata_base.items() if value not in (None, [], "")},
    )
    result = memory_manager.add_record_if_useful(str(category), str(content), metadata, root)
    record = result.get("record")
    payload: dict[str, Any] = {
        "action": "save-turn-card",
        "result": result.get("action"),
        "reason": result.get("reason"),
    }
    if record is not None:
        payload["id"] = record.id
        payload["category"] = record.category
        payload["metadata"] = record.metadata
    if result.get("duplicate_id") is not None:
        payload["duplicate_id"] = result["duplicate_id"]
    return payload


def handle_save_insight(args: argparse.Namespace, root: Path | None) -> None:
    if bool(args.claim_key) != bool(args.claim_value):
        raise ValueError("--claim-key and --claim-value must be provided together.")
    if security.contains_secret(args.content, args.summary, args.details):
        print_json({
            "action": "save-insight",
            "result": "rejected",
            "reason": "secret-like content must not be stored",
            "category": None,
        })
        return
    metadata_base = {}
    if args.source_path:
        metadata_base.update(provenance_service.describe_file(root or Path.cwd(), args.source_path))
    if args.memory_type:
        metadata_base["memory_type"] = args.memory_type
    if args.trust is not None:
        metadata_base["trust"] = memory_manager.clamp_unit_interval(args.trust, "trust")
    if args.claim_key:
        metadata_base.update({"claim_key": args.claim_key, "claim_value": args.claim_value})
    if args.preference_key:
        metadata_base["preference_key"] = args.preference_key
    if args.preference_evidence_type:
        metadata_base["preference_evidence_type"] = args.preference_evidence_type
    if args.decision_id:
        metadata_base["decision_id"] = args.decision_id
    metadata_base.update(
        memory_manager.provider_metadata(
            origin_provider=args.origin_provider,
            origin_agent=args.origin_agent,
            source_session=args.source_session,
            source_turn=args.source_turn,
            cwd=args.cwd,
            branch=args.branch,
            commit=args.commit,
            capture_channel=args.capture_channel or args.source,
            applies_to_provider=args.applies_to_provider,
        )
    )
    outcome = memory_manager.add_record_if_useful(
        args.category,
        args.content,
        memory_manager.build_card_metadata(
            summary=args.summary,
            details=args.details,
            tags=args.tag,
            source=args.source,
            status=args.status,
            importance=args.importance,
            confidence=args.confidence,
            base=metadata_base or None,
        ),
        root,
    )
    record = outcome.get("record")
    payload: dict[str, Any] = {"action": "save-insight", "result": outcome.get("action")}
    if outcome.get("reason"):
        payload["reason"] = outcome["reason"]
    if record is not None:
        payload["id"] = record.id
        payload["category"] = record.category
    if outcome.get("action") == "updated_existing" and record is not None:
        payload["next_action"] = (
            f"Existing memory #{record.id} already covers this; it was confirmed instead of duplicated. "
            f"If the fact changed, run edit-memory {record.id} with the corrected content."
        )
    elif outcome.get("action") == "saved_related" and record is not None:
        related = (record.metadata or {}).get("related_memory_id")
        payload["next_action"] = (
            f"Saved, but memory #{related} is similar. If both describe the same fact, run "
            f"merge-memories {record.id} {related}."
        )
    elif outcome.get("action") == "ignored":
        payload["next_action"] = (
            "Nothing was stored. If this insight is durable and new, rephrase it as a specific, "
            "verifiable fact and retry; otherwise keep it out of memory."
        )
    print_json(payload)


def handle_save_turn_card(args: argparse.Namespace, root: Path | None) -> None:
    print_json(save_turn_card(load_json_card(file_path=args.file, use_stdin=args.stdin), root))


def handle_retrieve_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json(
        memory_manager.query(
            args.query_text,
            categories=args.category,
            exclude_categories=args.exclude_category,
            statuses=args.status,
            limit=args.limit,
            root=root,
            summarize=args.summary,
            verbose=args.verbose,
        )
    )


def handle_define_category(args: argparse.Namespace, root: Path | None) -> None:
    details = recall_config.add_category(
        args.category,
        args.description,
        args.weight,
        root,
        examples=args.example or None,
        non_examples=args.non_example or None,
        update_rule=args.update_rule,
    )
    print_json({"action": "define-category", "category": args.category, "details": details})


def handle_contract(args: argparse.Namespace, root: Path | None) -> None:
    import contract as recall_contract

    cfg = recall_config.load_config_if_present(root)
    print_json(
        {
            "action": "contract",
            "contract": recall_contract.contract_dict(),
            "categories": cfg.get("categories", {}),
        }
    )


def handle_doctor(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "doctor", "report": memory_manager.doctor(root)})


def handle_repair(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "repair", "report": memory_manager.repair(root)})


def handle_export_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "export-memory", "report": recovery_service.export_memory(args.path, root)})


def handle_import_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "import-memory", "report": recovery_service.import_memory(args.path, root, replace=args.replace)})


def handle_backup_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "backup-memory", "report": recovery_service.backup_memory(root)})


def handle_restore_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "restore-memory", "report": recovery_service.restore_memory(args.path, root)})


def handle_list_categories(args: argparse.Namespace, root: Path | None) -> None:
    cfg = recall_config.load_config(root)
    categories = [
        {
            "name": name,
            "description": details["description"],
            "weight": details["weight"],
            **{
                key: details[key]
                for key in ("examples", "non_examples", "update_rule")
                if key in details
            },
        }
        for name, details in sorted(cfg["categories"].items())
    ]
    print_json({"action": "list-categories", "categories": categories})


def handle_configure_capture(args: argparse.Namespace, root: Path | None) -> None:
    cfg = recall_config.set_capture_mode(args.mode, root)
    print_json({"action": "configure-capture", "capture_mode": cfg["capture_mode"]})


def handle_configure_recall(args: argparse.Namespace, root: Path | None) -> None:
    cfg = recall_config.set_recall_mode(args.mode, root)
    print_json({"action": "configure-recall", "recall_mode": cfg["recall_mode"]})


def handle_initialize_project(args: argparse.Namespace, root: Path | None) -> None:
    import contract as recall_contract

    target = (root or Path.cwd()).resolve()
    cfg = recall_config.activate_project(target, activated_by="explicit_initialize")
    gitignore = recall_config.ensure_gitignore_entries(target)
    print_json(
        {
            "action": "initialize-project",
            "root": str(target),
            "activation": cfg["activation"],
            "gitignore": gitignore,
            "categories": sorted(cfg.get("categories", {})),
            "contract": recall_contract.compact_contract_text(),
            "first_workflow": (
                "1) retrieve-memory before starting work; 2) work normally; 3) save-insight only for "
                "durable verified facts; 4) edit/supersede memories when facts change; 5) hygiene-scan periodically."
            ),
        }
    )


def handle_activation_status(args: argparse.Namespace, root: Path | None) -> None:
    target = (root or Path.cwd()).resolve()
    cfg = recall_config.load_config_if_present(target)
    print_json({"action": "activation-status", "root": str(target), "active": recall_config.project_is_active(target), "activation": cfg.get("activation")})


def handle_deactivate_project(args: argparse.Namespace, root: Path | None) -> None:
    target = (root or Path.cwd()).resolve()
    cfg = recall_config.deactivate_project(target)
    print_json({"action": "deactivate-project", "root": str(target), "activation": cfg["activation"]})


def handle_configure_observability(args: argparse.Namespace, root: Path | None) -> None:
    cfg = recall_config.set_observability_mode(args.mode, root)
    print_json({"action": "configure-observability", "observability_mode": cfg["observability_mode"]})


def handle_apply_finalizer_batch(args: argparse.Namespace, root: Path | None) -> None:
    payload = load_stdin_object()
    try:
        print_json(apply_finalizer_batch(payload, root))
    except Exception as exc:
        import observability
        observability.trace(root, "finalizer_failed", {"error": type(exc).__name__, "message": str(exc)})
        raise


def handle_migrate_corpus(args: argparse.Namespace, root: Path | None) -> None:
    report = corpus_migration.apply_migration(root) if args.apply else {"action": "migrate-corpus", "dry_run": True, "plan": corpus_migration.plan_migration(root)}
    print_json(report)


def handle_batch_ingest(args: argparse.Namespace, root: Path | None) -> None:
    payload = load_stdin_object()
    if payload.get("schema") != "recall.batch_ingest.v1" or not isinstance(payload.get("cards"), list):
        raise ValueError("batch-ingest requires recall.batch_ingest.v1 with a cards list.")
    records = memory_manager.add_records_batch(payload["cards"], root)
    print_json({"action": "batch-ingest", "saved": len(records), "ids": [record.id for record in records]})


def handle_debug_tail(args: argparse.Namespace, root: Path | None) -> None:
    import observability
    target = root or Path.cwd()
    lines: list[dict[str, Any]] = []
    for path in sorted(observability.debug_dir(target).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(json.loads(line))
    print_json({"action": "debug-tail", "events": lines[-args.limit:]})


def handle_review_memory(args: argparse.Namespace, root: Path | None) -> None:
    request = ReviewRequest(
        root=root,
        statuses=tuple(args.status or []),
        categories=tuple(args.category or []),
        source=args.source,
        limit=args.limit,
    )
    print_json(
        {
            "action": "review-memory",
            "review": review_memory(request).to_dict(),
        }
    )


def handle_audit_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json(
        {
            "action": "audit-memory",
            "audit": memory_review.audit_memory(
                root,
                statuses=args.status,
                categories=args.category,
                source=args.source,
                limit=args.limit,
            ),
        }
    )


def handle_archive_noise(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_noise.archive_noise(root, apply=args.apply, limit=args.limit))


def handle_hygiene_scan(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_hygiene.hygiene_scan(root, limit=args.limit))


def handle_hygiene_plan(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_hygiene.hygiene_plan(root, limit=args.limit, scope=args.scope))


def handle_hygiene_apply(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_hygiene.hygiene_apply(root, safe=args.safe, limit=args.limit))


def handle_route_memory(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_hygiene.route_memory(args.candidate_fact))


def handle_reconcile_current_truth(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_hygiene.reconcile_current_truth(root, claim_key=args.claim_key))


def handle_refresh_source_backed(args: argparse.Namespace, root: Path | None) -> None:
    print_json(memory_hygiene.refresh_source_backed(root, limit=args.limit))


def handle_confirm_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = memory_manager.confirm_record(args.id, root, args.source_session)
    print_json({"action": "confirm-memory", "id": record.id, "metadata": record.metadata})


def handle_resolve_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = memory_manager.resolve_record(args.id, root, args.note)
    print_json({"action": "resolve-memory", "id": record.id, "metadata": record.metadata})


def handle_stale_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = memory_manager.mark_record_stale(args.id, root, args.note)
    print_json({"action": "stale-memory", "id": record.id, "metadata": record.metadata})


def handle_supersede_memory(args: argparse.Namespace, root: Path | None) -> None:
    result = memory_manager.supersede_record(args.old_id, args.new_id, root, args.note)
    print_json(
        {
            "action": "supersede-memory",
            "old": {"id": result["old"].id, "metadata": result["old"].metadata},
            "new": {"id": result["new"].id, "metadata": result["new"].metadata},
        }
    )


def handle_merge_memories(args: argparse.Namespace, root: Path | None) -> None:
    result = memory_manager.merge_records(args.primary_id, args.secondary_id, root, args.note)
    print_json(
        {
            "action": "merge-memories",
            "primary": {"id": result["primary"].id, "metadata": result["primary"].metadata},
            "merged": [{"id": record.id, "metadata": record.metadata} for record in result["merged"]],
        }
    )


def handle_prune_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = memory_manager.prune_record(args.id, root, args.note)
    print_json({"action": "prune-memory", "id": record.id, "metadata": record.metadata})


def handle_edit_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = memory_manager.edit_record(
        args.id,
        root,
        category=args.category,
        content=args.content,
        summary=args.summary,
        details=args.details,
        tags=args.tag,
        source=args.source,
        status=args.status,
        importance=args.importance,
        confidence=args.confidence,
    )
    print_json(
        {
            "action": "edit-memory",
            "id": record.id,
            "category": record.category,
            "content": record.content,
            "metadata": record.metadata,
        }
    )


def handle_delete_memory(args: argparse.Namespace, root: Path | None) -> None:
    if args.confirm != f"DELETE-{args.id}":
        raise SystemExit(f"delete-memory requires --confirm DELETE-{args.id}")
    record = memory_manager.delete_record(args.id, root)
    print_json({"action": "delete-memory", "id": record.id, "category": record.category})


def handle_invalidate_by_file(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "invalidate-by-file", "result": provenance_service.invalidate_by_file(args.path, root or Path.cwd())})


def handle_refresh_source(args: argparse.Namespace, root: Path | None) -> None:
    record = provenance_service.refresh_source(args.id, root or Path.cwd())
    print_json({"action": "refresh-source", "id": record.id, "metadata": record.metadata})


def handle_reconcile_sources(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "reconcile-sources", "report": provenance_service.reconcile_sources(root or Path.cwd())})


def handle_promote_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = lifecycle_service.promote(args.id, root, args.note)
    print_json({"action": "promote-memory", "id": record.id, "metadata": record.metadata})


def handle_deprecate_memory(args: argparse.Namespace, root: Path | None) -> None:
    record = lifecycle_service.deprecate(args.id, root, args.note)
    print_json({"action": "deprecate-memory", "id": record.id, "metadata": record.metadata})


def handle_list_conflicts(args: argparse.Namespace, root: Path | None) -> None:
    print_json({"action": "list-conflicts", "conflicts": lifecycle_service.find_conflicts(root)})


def handle_resolve_conflict(args: argparse.Namespace, root: Path | None) -> None:
    result = lifecycle_service.resolve_conflict(args.winner_id, args.loser_id, root, args.note)
    print_json(
        {
            "action": "resolve-conflict",
            "winner": {"id": result["winner"].id, "metadata": result["winner"].metadata},
            "losers": [{"id": record.id, "metadata": record.metadata} for record in result["losers"]],
        }
    )


def handle_context_packet(args: argparse.Namespace, root: Path | None) -> None:
    request = ContextPacketRequest(
        args.query_text,
        token_budget=args.token_budget,
        categories=tuple(args.category or []),
        root=root,
    )
    print_json({"action": "context-packet", "packet": build_context_packet(request).to_dict()})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RECALL skill actions against project-local memory.")
    parser.add_argument("--root", help="Project root. Defaults to the current working directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    save = subparsers.add_parser("save-insight")
    save.add_argument("category")
    save.add_argument("content")
    save.add_argument("--summary")
    save.add_argument("--details")
    save.add_argument("--tag", action="append", default=[])
    save.add_argument("--source", default="skill")
    save.add_argument("--origin-provider")
    save.add_argument("--origin-agent")
    save.add_argument("--source-session")
    save.add_argument("--source-turn")
    save.add_argument("--cwd")
    save.add_argument("--branch")
    save.add_argument("--commit")
    save.add_argument("--capture-channel")
    save.add_argument("--applies-to-provider")
    save.add_argument("--source-path")
    save.add_argument("--memory-type")
    save.add_argument("--trust", type=float)
    save.add_argument("--claim-key")
    save.add_argument("--claim-value")
    save.add_argument("--preference-key")
    save.add_argument("--preference-evidence-type")
    save.add_argument("--decision-id")
    save.add_argument("--status", default="active")
    save.add_argument("--importance", type=float)
    save.add_argument("--confidence", type=float)
    save.set_defaults(handler=handle_save_insight)

    turn_card = subparsers.add_parser("save-turn-card")
    source = turn_card.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--stdin", action="store_true")
    turn_card.set_defaults(handler=handle_save_turn_card)

    retrieve = subparsers.add_parser("retrieve-memory")
    retrieve.add_argument("query_text")
    retrieve.add_argument("--category", action="append", default=[])
    retrieve.add_argument("--exclude-category", action="append", default=[])
    retrieve.add_argument("--status", action="append", default=[])
    retrieve.add_argument("--limit", type=int, default=8)
    retrieve.add_argument("--summary", action="store_true")
    retrieve.add_argument(
        "--verbose",
        action="store_true",
        help="Include full metadata per result. Default is compact, token-lean output.",
    )
    retrieve.set_defaults(handler=handle_retrieve_memory)

    define = subparsers.add_parser("define-category")
    define.add_argument("category")
    define.add_argument("--description", required=True)
    define.add_argument("--weight", type=float, default=1.0)
    define.add_argument("--example", action="append", default=[], help="Positive example memory for this category. May be repeated.")
    define.add_argument("--non-example", action="append", default=[], help="Non-example that does NOT belong here. May be repeated.")
    define.add_argument("--update-rule", help="How memories in this category should be updated or aged.")
    define.set_defaults(handler=handle_define_category)

    subparsers.add_parser("contract").set_defaults(handler=handle_contract)

    subparsers.add_parser("doctor").set_defaults(handler=handle_doctor)
    subparsers.add_parser("repair").set_defaults(handler=handle_repair)
    export_memory = subparsers.add_parser("export-memory")
    export_memory.add_argument("path")
    export_memory.set_defaults(handler=handle_export_memory)
    import_memory = subparsers.add_parser("import-memory")
    import_memory.add_argument("path")
    import_memory.add_argument("--replace", action="store_true")
    import_memory.set_defaults(handler=handle_import_memory)
    subparsers.add_parser("backup-memory").set_defaults(handler=handle_backup_memory)
    restore_memory = subparsers.add_parser("restore-memory")
    restore_memory.add_argument("path")
    restore_memory.set_defaults(handler=handle_restore_memory)
    subparsers.add_parser("list-categories").set_defaults(handler=handle_list_categories)
    configure_capture = subparsers.add_parser("configure-capture")
    configure_capture.add_argument("mode", choices=sorted(recall_config.VALID_CAPTURE_MODES))
    configure_capture.set_defaults(handler=handle_configure_capture)
    configure_recall = subparsers.add_parser("configure-recall")
    configure_recall.add_argument("mode", choices=sorted(recall_config.VALID_RECALL_MODES))
    configure_recall.set_defaults(handler=handle_configure_recall)
    subparsers.add_parser("initialize-project").set_defaults(handler=handle_initialize_project)
    subparsers.add_parser("activation-status").set_defaults(handler=handle_activation_status)
    subparsers.add_parser("deactivate-project").set_defaults(handler=handle_deactivate_project)
    configure_observability = subparsers.add_parser("configure-observability")
    configure_observability.add_argument("mode", choices=sorted(recall_config.VALID_OBSERVABILITY_MODES))
    configure_observability.set_defaults(handler=handle_configure_observability)
    finalizer_batch = subparsers.add_parser("apply-finalizer-batch")
    finalizer_batch.add_argument("--stdin", action="store_true", required=True)
    finalizer_batch.set_defaults(handler=handle_apply_finalizer_batch)
    migrate_corpus = subparsers.add_parser("migrate-corpus")
    migrate_mode = migrate_corpus.add_mutually_exclusive_group(required=True)
    migrate_mode.add_argument("--dry-run", action="store_true")
    migrate_mode.add_argument("--apply", action="store_true")
    migrate_corpus.set_defaults(handler=handle_migrate_corpus)
    batch_ingest = subparsers.add_parser("batch-ingest")
    batch_ingest.add_argument("--stdin", action="store_true", required=True)
    batch_ingest.set_defaults(handler=handle_batch_ingest)
    debug_tail = subparsers.add_parser("debug-tail")
    debug_tail.add_argument("--limit", type=int, default=50)
    debug_tail.set_defaults(handler=handle_debug_tail)

    review = subparsers.add_parser("review-memory")
    review.add_argument("--status", action="append", default=[])
    review.add_argument("--category", action="append", default=[])
    review.add_argument("--source")
    review.add_argument("--limit", type=int, default=20)
    review.set_defaults(handler=handle_review_memory)

    audit = subparsers.add_parser("audit-memory")
    audit.add_argument("--status", action="append", default=[])
    audit.add_argument("--category", action="append", default=[])
    audit.add_argument("--source")
    audit.add_argument("--limit", type=int, default=20)
    audit.set_defaults(handler=handle_audit_memory)

    archive_noise = subparsers.add_parser("archive-noise")
    archive_noise.add_argument("--apply", action="store_true", help="Archive matched noise. Omit for dry-run.")
    archive_noise.add_argument("--limit", type=int, help="Maximum matched memories to review or archive.")
    archive_noise.set_defaults(handler=handle_archive_noise)

    hygiene_scan = subparsers.add_parser("hygiene-scan")
    hygiene_scan.add_argument("--limit", type=int)
    hygiene_scan.set_defaults(handler=handle_hygiene_scan)

    hygiene_plan = subparsers.add_parser("hygiene-plan")
    hygiene_plan.add_argument("--scope", default="project", choices=["project"])
    hygiene_plan.add_argument("--limit", type=int)
    hygiene_plan.set_defaults(handler=handle_hygiene_plan)

    hygiene_apply = subparsers.add_parser("hygiene-apply")
    hygiene_apply.add_argument("--safe", action="store_true", required=True)
    hygiene_apply.add_argument("--limit", type=int)
    hygiene_apply.set_defaults(handler=handle_hygiene_apply)

    route_memory = subparsers.add_parser("route-memory")
    route_memory.add_argument("candidate_fact")
    route_memory.set_defaults(handler=handle_route_memory)

    reconcile_current_truth = subparsers.add_parser("reconcile-current-truth")
    reconcile_current_truth.add_argument("--claim-key", required=True)
    reconcile_current_truth.set_defaults(handler=handle_reconcile_current_truth)

    refresh_source_backed = subparsers.add_parser("refresh-source-backed")
    refresh_source_backed.add_argument("--limit", type=int)
    refresh_source_backed.set_defaults(handler=handle_refresh_source_backed)

    confirm = subparsers.add_parser("confirm-memory")
    confirm.add_argument("id", type=int)
    confirm.add_argument("--source-session")
    confirm.set_defaults(handler=handle_confirm_memory)

    resolve = subparsers.add_parser("resolve-memory")
    resolve.add_argument("id", type=int)
    resolve.add_argument("--note")
    resolve.set_defaults(handler=handle_resolve_memory)

    stale = subparsers.add_parser("stale-memory")
    stale.add_argument("id", type=int)
    stale.add_argument("--note")
    stale.set_defaults(handler=handle_stale_memory)

    supersede = subparsers.add_parser("supersede-memory")
    supersede.add_argument("old_id", type=int)
    supersede.add_argument("new_id", type=int)
    supersede.add_argument("--note")
    supersede.set_defaults(handler=handle_supersede_memory)

    merge = subparsers.add_parser("merge-memories")
    merge.add_argument("primary_id", type=int)
    merge.add_argument("secondary_id", nargs="+")
    merge.add_argument("--note")
    merge.set_defaults(handler=handle_merge_memories)

    prune = subparsers.add_parser("prune-memory")
    prune.add_argument("id", type=int)
    prune.add_argument("--note")
    prune.set_defaults(handler=handle_prune_memory)

    edit = subparsers.add_parser("edit-memory")
    edit.add_argument("id", type=int)
    edit.add_argument("--category")
    edit.add_argument("--content")
    edit.add_argument("--summary")
    edit.add_argument("--details")
    edit.add_argument("--tag", action="append", default=[])
    edit.add_argument("--source")
    edit.add_argument("--status")
    edit.add_argument("--importance", type=float)
    edit.add_argument("--confidence", type=float)
    edit.set_defaults(handler=handle_edit_memory)

    delete = subparsers.add_parser("delete-memory")
    delete.add_argument("id", type=int)
    delete.add_argument("--confirm", required=True)
    delete.set_defaults(handler=handle_delete_memory)

    invalidate = subparsers.add_parser("invalidate-by-file")
    invalidate.add_argument("path")
    invalidate.set_defaults(handler=handle_invalidate_by_file)

    refresh = subparsers.add_parser("refresh-source")
    refresh.add_argument("id", type=int)
    refresh.set_defaults(handler=handle_refresh_source)

    subparsers.add_parser("reconcile-sources").set_defaults(handler=handle_reconcile_sources)

    promote = subparsers.add_parser("promote-memory")
    promote.add_argument("id", type=int)
    promote.add_argument("--note")
    promote.set_defaults(handler=handle_promote_memory)

    deprecate = subparsers.add_parser("deprecate-memory")
    deprecate.add_argument("id", type=int)
    deprecate.add_argument("--note")
    deprecate.set_defaults(handler=handle_deprecate_memory)

    subparsers.add_parser("list-conflicts").set_defaults(handler=handle_list_conflicts)

    resolve_conflict = subparsers.add_parser("resolve-conflict")
    resolve_conflict.add_argument("winner_id", type=int)
    resolve_conflict.add_argument("loser_id", nargs="+", type=int)
    resolve_conflict.add_argument("--note")
    resolve_conflict.set_defaults(handler=handle_resolve_conflict)

    context_packet = subparsers.add_parser("context-packet")
    context_packet.add_argument("query_text")
    context_packet.add_argument("--category", action="append", default=[])
    context_packet.add_argument("--token-budget", type=int, default=1200)
    context_packet.set_defaults(handler=handle_context_packet)

    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else None
    args.handler(args, root)


if __name__ == "__main__":
    main()
