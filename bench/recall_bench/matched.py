"""Offline controller for matched agent trials; never launches a model or host.

The controller owns this module, the fixture and the evidence root. Subjects get
only their workspace and the current phase's prompt. Directory separation is
not a security sandbox: the host must enforce the exported access boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ARMS = ("candidate", "memory_off", "docs_only", "native_memory")
FAMILIES = ("recurring_failure", "stale_fact", "small_task", "no_memory", "interrupted_task")
CRITICAL = {"data_loss": "P0", "secret_exposure": "P0", "destructive_change": "P0",
            "cross_project_memory": "P0", "wrong_current_truth": "P1", "host_load_failure": "P1",
            "broken_public_rule": "P1", "unrecoverable_store": "P1"}
AUDIT_SURFACES = {"session_start", "prompt", "tools", "stop", "finalizer"}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, encoding="utf-8").strip()


def candidate_identity(repo: Path, commit: str, zip_path: Path | None = None) -> dict:
    repo = repo.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or git(repo, "rev-parse", "HEAD") != commit:
        raise ValueError("Candidate must be the full, current commit SHA")
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Freeze a clean candidate checkout, including untracked source")
    artifact = zip_path or repo / "dist" / "recall.zip"
    if zip_path is not None and not artifact.is_file():
        raise ValueError("Named ZIP does not exist")
    return {"repo": str(repo), "commit": commit, "zip_path": str(artifact.resolve()),
            "zip_sha256": sha256(artifact) if artifact.is_file() else None}


def disjoint(paths: list[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    for i, left in enumerate(resolved):
        for right in resolved[i + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError(f"Roots overlap: {left} and {right}")


def safe_relative(name: str) -> Path:
    part = PurePosixPath(name)
    if not name or not part.parts or "\\" in name or ":" in name or part.is_absolute() or ".." in part.parts:
        raise ValueError(f"Unsafe fixture path: {name}")
    if part.parts[0] in {".recall", ".codex_memory", ".native-memory", ".host", ".git"}:
        raise ValueError("Fixture cannot populate a store or host configuration")
    return Path(*part.parts)


def load_fixture(path: Path) -> dict:
    fixture = read_json(path)
    tasks = fixture.get("tasks", [])
    if [task.get("id") for task in tasks] != list(FAMILIES):
        raise ValueError("Expected the five frozen task families in order")
    for task in tasks:
        if set(task) != {"id", "subject", "judge"}:
            raise ValueError("Task fields must separate subject from judge")
        subject = task["subject"]
        if set(subject) != {"files", "phases", "history_document"}:
            raise ValueError("Subject fields are an explicit allowlist")
        for name, content in subject["files"].items():
            safe_relative(name)
            if not isinstance(content, str):
                raise ValueError("Fixture files must contain text")
        phases = subject["phases"]
        if not phases or len({phase["id"] for phase in phases}) != len(phases):
            raise ValueError("Unique, non-empty phases are required")
        for phase in phases:
            if set(phase) != {"id", "prompt", "new_session", "interrupt_after"}:
                raise ValueError("Phase fields are an explicit allowlist")
            if not isinstance(phase["prompt"], str) or not phase["prompt"].strip():
                raise ValueError("Each phase needs a task prompt")
            if type(phase["new_session"]) is not bool or type(phase["interrupt_after"]) is not bool:
                raise ValueError("Phase controls must be boolean")
    return fixture


def prepare(repo: Path, commit: str, fixture_path: Path, evidence: Path, subjects: Path,
            host: dict, models: dict, zip_path: Path | None = None) -> dict:
    evidence, subjects = evidence.resolve(), subjects.resolve()
    disjoint([repo, evidence, subjects])
    if evidence.exists() or subjects.exists():
        raise ValueError("New matrix requires two new roots; nothing is overwritten")
    load_fixture(fixture_path)
    identity = candidate_identity(repo, commit, zip_path)
    if set(models) != set(ARMS) or any(not isinstance(v, str) or not v.strip() for v in models.values()):
        raise ValueError("Record one non-empty requested model name per arm")
    if len(set(models.values())) != 1:
        raise ValueError("A matched matrix needs the same model in all four arms")
    if not all(isinstance(host.get(key), str) and host[key].strip() for key in ("name", "version")):
        raise ValueError("Record host name and version")
    manifest = {"schema_version": 1, "run_id": str(uuid.uuid4()), "created_at": now(),
                "candidate": identity, "host": host, "models": models,
                "environment": {"python": sys.version, "executable": sys.executable,
                                "platform": platform.platform(), "git": git(repo, "--version")},
                "fixture_sha256": sha256(fixture_path), "subjects_root": str(subjects),
                "arms": list(ARMS), "families": list(FAMILIES), "max_attempts": 2}
    evidence.mkdir(parents=True)
    subjects.mkdir(parents=True)
    shutil.copyfile(fixture_path, evidence / "fixture.json")
    write_new(evidence / "manifest.json", manifest)
    (evidence / "manifest.sha256").write_text(canonical_hash(manifest), encoding="ascii")
    return manifest


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_run(evidence: Path, *, verify_candidate: bool = True) -> tuple[dict, dict]:
    manifest = read_json(evidence / "manifest.json")
    if canonical_hash(manifest) != (evidence / "manifest.sha256").read_text(encoding="ascii"):
        raise ValueError("Frozen manifest changed")
    if sha256(evidence / "fixture.json") != manifest["fixture_sha256"]:
        raise ValueError("Frozen fixture changed")
    identity = manifest["candidate"]
    if verify_candidate and candidate_identity(Path(identity["repo"]), identity["commit"],
                                               Path(identity["zip_path"]) if identity["zip_sha256"] else None) != identity:
        raise ValueError("Candidate ZIP changed; start a new matrix")
    disjoint([evidence, Path(manifest["subjects_root"]), Path(identity["repo"])])
    return manifest, load_fixture(evidence / "fixture.json")


def attempt_dirs(evidence: Path) -> list[Path]:
    return sorted((evidence / "attempts").glob("*"))


def attempt(evidence: Path, attempt_id: str) -> Path:
    if not re.fullmatch(r"[a-z_]+--(?:candidate|memory_off|docs_only|native_memory)--[12]", attempt_id):
        raise ValueError("Invalid attempt ID")
    path = evidence / "attempts" / attempt_id
    if not path.is_dir():
        raise ValueError("Attempt does not exist")
    return path


def check_isolation(evidence: Path, manifest: dict) -> list[str]:
    problems = []
    roots = []
    for path in attempt_dirs(evidence):
        launch = read_json(path / "launch.json")
        workspace = Path(launch["workspace"])
        expected = Path(manifest["subjects_root"]) / path.name
        if workspace != expected or workspace.resolve() != expected.absolute():
            problems.append(f"Workspace redirected: {path.name}")
        roots.append(workspace)
        for name in (".recall", ".native-memory", ".host"):
            child = workspace / name
            if child.resolve().parent != workspace.absolute() or not child.is_dir():
                problems.append(f"Store/config redirected or missing: {path.name}/{name}")
    try:
        disjoint([*roots, evidence, Path(manifest["candidate"]["repo"])])
    except ValueError as exc:
        problems.append(str(exc))
    return problems


def begin(evidence: Path, family: str, arm: str) -> dict:
    manifest, fixture = load_run(evidence)
    if family not in FAMILIES or arm not in ARMS:
        raise ValueError("Unknown family or arm")
    summary = summarize(evidence)
    if summary["critical_faults"] or summary["isolation_errors"]:
        raise ValueError("Run halted by a P0/P1 fault or broken isolation")
    # A single controller runs one attempt at a time. An abandoned attempt must
    # be sealed as unknown before moving on, retaining whatever trace exists.
    if any(not (path / "receipt.json").exists() for path in attempt_dirs(evidence)):
        raise ValueError("Seal the pending attempt before starting another")
    previous = [r for r in summary["attempts"] if r["family"] == family and r["arm"] == arm]
    if len(previous) >= 2 or (previous and previous[-1]["status"] == "pass"):
        raise ValueError("Only one rerun of a failed or unclear case is allowed")
    number = len(previous) + 1
    attempt_id = f"{family}--{arm}--{number}"
    task = next(t for t in fixture["tasks"] if t["id"] == family)
    workspace = Path(manifest["subjects_root"]) / attempt_id
    workspace.mkdir(exist_ok=False)
    for name in (".recall", ".native-memory", ".host"):
        (workspace / name).mkdir()
    files = dict(task["subject"]["files"])
    if arm == "docs_only" and task["subject"]["history_document"]:
        files["docs/project-history.md"] = task["subject"]["history_document"]
    for name, content in files.items():
        target = workspace / safe_relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    launch = {"attempt_id": attempt_id, "family": family, "arm": arm,
              "workspace": str(workspace), "requested_model": manifest["models"][arm],
              "host": manifest["host"], "candidate": manifest["candidate"],
              "created_at": now(), "initial_files": {name: sha256(workspace / name) for name in files},
              "initial_stores_empty": True,
              "runtime_policy": {"recall_enabled": arm == "candidate", "native_memory_enabled": arm == "native_memory",
                                 "project_docs_enabled": arm == "docs_only", "fresh_host_config": True},
              "required_boundary": "Subject may access only workspace; no controller, repo, judge or sibling roots."}
    write_new(evidence / "attempts" / attempt_id / "launch.json", launch)
    return launch


def subject_input(evidence: Path, attempt_id: str, phase_id: str) -> dict:
    """Allowlisted delivery payload, without rubric, expected answer or paths to evidence."""
    _, fixture = load_run(evidence)
    launch = read_json(attempt(evidence, attempt_id) / "launch.json")
    task = next(t for t in fixture["tasks"] if t["id"] == launch["family"])
    phase = next((p for p in task["subject"]["phases"] if p["id"] == phase_id), None)
    if phase is None:
        raise ValueError("Unknown phase")
    return {"prompt": phase["prompt"]}


def trace_events(path: Path) -> tuple[list[dict], list[str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return [], ["missing trace"]
    events, errors = [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeError:
        return [], ["trace is not UTF-8"]
    for line_no, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("not an object")
            events.append(event)
        except (ValueError, TypeError):
            errors.append(f"malformed trace line {line_no}")
    return events, errors


def critical_faults(events: list[dict], assessment: dict) -> list[dict]:
    found = []
    harms = assessment.get("harms", [])
    for item in [*events, *(harms if isinstance(harms, list) else [])]:
        if not isinstance(item, dict):
            continue
        kind = item.get("fault")
        severity = CRITICAL.get(kind, item.get("severity")) if isinstance(kind, str) else item.get("severity")
        if isinstance(severity, str) and severity in {"P0", "P1"}:
            found.append({"severity": severity, "fault": kind, "evidence": item.get("evidence", item.get("seq"))})
    return found


def trace_check(events: list[dict], launch: dict, task: dict) -> list[str]:
    errors = []
    if not events:
        return ["missing trace"]
    if [e.get("seq") for e in events] != list(range(1, len(events) + 1)):
        errors.append("trace sequence gap or duplicate")
    if events[0].get("kind") != "run_start" or events[-1].get("kind") != "run_end":
        errors.append("missing trace boundary")
    if sum(e.get("kind") == "run_start" for e in events) != 1 or sum(e.get("kind") == "run_end" for e in events) != 1:
        errors.append("duplicate or missing run boundary")
    if any(e.get("attempt_id") != launch["attempt_id"] for e in events):
        errors.append("trace attempt mismatch")
    if events[0].get("model") != launch["requested_model"] or events[0].get("host") != launch["host"]:
        errors.append("observed model/host missing or different")
    if events[0].get("candidate") != launch["candidate"]:
        errors.append("observed candidate identity missing or different")
    if events[-1].get("complete") is not True or type(events[-1].get("exit_code")) is not int:
        errors.append("trace completion unknown")
    calls, results = [], []
    for event in events:
        if event.get("kind") == "tool_call":
            calls.append(event.get("call_id"))
            if not isinstance(event.get("name"), str) or "arguments" not in event:
                errors.append("tool call payload missing")
        if event.get("kind") == "tool_result":
            results.append(event.get("call_id"))
            if event.get("call_id") not in calls:
                errors.append("tool result precedes its call")
            if "output" not in event or type(event.get("is_error")) is not bool:
                errors.append("tool result payload missing")
    if any(not isinstance(x, str) or not x for x in calls + results):
        errors.append("invalid tool call IDs")
    elif len(set(calls)) != len(calls) or sorted(calls) != sorted(results):
        errors.append("unpaired or duplicate tool calls")
    phases = [e for e in events if e.get("kind") == "phase_start"]
    if [e.get("phase_id") for e in phases] != [p["id"] for p in task["subject"]["phases"]]:
        errors.append("missing or out-of-order task phase")
    sessions = set()
    for expected, actual in zip(task["subject"]["phases"], phases, strict=False):
        session = actual.get("session_id")
        if not isinstance(session, str) or not session:
            errors.append("fresh session not evidenced")
        else:
            if expected["new_session"] and session in sessions:
                errors.append("fresh session not evidenced")
            sessions.add(session)
        if actual.get("prompt") != expected["prompt"]:
            errors.append("subject prompt mismatch")
        if expected["interrupt_after"] and not any(e.get("kind") == "interruption" and e.get("phase_id") == expected["id"] for e in events):
            errors.append("interruption not evidenced")
    if not any(e.get("kind") == "assistant_message" and isinstance(e.get("content"), str) for e in events):
        errors.append("subject answer missing")
    return errors


def seal(evidence: Path, attempt_id: str, trace: Path | None = None, raw: Path | None = None,
         observation: Path | None = None, assessment: Path | None = None) -> dict:
    """Retain supplied bytes even when malformed. Sealing without files records unknown."""
    load_run(evidence, verify_candidate=False)
    target = attempt(evidence, attempt_id)
    if (target / "receipt.json").exists():
        raise ValueError("Attempt already sealed; evidence is append-only")
    sources = {"trace.jsonl": trace, "raw-trace.bin": raw, "observation.json": observation, "assessment.json": assessment}
    if any(source is not None and not source.is_file() for source in sources.values()):
        raise ValueError("Supplied evidence path does not exist; omit unavailable evidence")
    hashes = {}
    for name, source in sources.items():
        if source is not None:
            with source.open("rb") as src, (target / name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
            hashes[name] = sha256(target / name)
    write_new(target / "receipt.json", {"sealed_at": now(), "files": hashes})
    return summarize(evidence)


def optional_json(path: Path, errors: list[str]) -> dict:
    try:
        return read_json(path)
    except (OSError, ValueError):
        errors.append(f"missing or malformed {path.name}")
        return {}


def grade_attempt(path: Path, manifest: dict, task: dict) -> dict:
    launch = read_json(path / "launch.json")
    events, errors = trace_events(path / "trace.jsonl")
    if (launch.get("candidate") != manifest["candidate"] or launch.get("host") != manifest["host"]
            or launch.get("requested_model") != manifest["models"].get(launch.get("arm"))
            or launch.get("attempt_id") != path.name
            or not path.name.startswith(f"{launch.get('family')}--{launch.get('arm')}--")):
        errors.append("launch identity differs from frozen matrix")
    errors.extend(trace_check(events, launch, task))
    receipt = optional_json(path / "receipt.json", errors)
    receipt_files = receipt.get("files")
    if not isinstance(receipt_files, dict):
        receipt_files = {}
    for name in ("trace.jsonl", "raw-trace.bin", "observation.json", "assessment.json"):
        artifact = path / name
        if not artifact.is_file() or artifact.stat().st_size == 0 or sha256(artifact) != receipt_files.get(name):
            errors.append(f"missing or changed {name}")
    observation = optional_json(path / "observation.json", errors)
    assessment = optional_json(path / "assessment.json", errors)
    required = ("fresh_context", "workspace_only", "controller_context_absent", "judge_context_absent",
                "fresh_store", "full_trace", "runtime_policy_verified")
    if any(observation.get(key) is not True for key in required) or not observation.get("evidence"):
        errors.append("host isolation/full trace not attested with evidence")
    if not assessment.get("judge") or not assessment.get("evidence"):
        errors.append("judge identity/evidence missing")
    if assessment.get("trace_sha256") != receipt_files.get("trace.jsonl") or not assessment.get("trace_sha256"):
        errors.append("assessment not bound to trace")
    harms = assessment.get("harms")
    if not isinstance(harms, list) or any(not isinstance(h, dict) or h.get("severity") not in ("P0", "P1", "P2", "P3") or not h.get("evidence") for h in harms):
        errors.append("harm review unknown")
    faults = critical_faults(events, assessment)
    result = assessment.get("task_result", "unknown")
    if not isinstance(result, str) or result not in {"pass", "fail", "unknown"}:
        result = "unknown"
        errors.append("invalid task result")
    wrong, stale = assessment.get("wrong_action"), assessment.get("stale_memory_use")
    if type(wrong) is not bool or type(stale) is not bool:
        errors.append("action/stale review unknown")
    all_memory = [e for e in events if e.get("kind") == "memory_access"]
    phase_ids = [p["id"] for p in task["subject"]["phases"]]
    for event in all_memory:
        if event.get("phase_id") not in phase_ids or event.get("operation") not in ("read", "write"):
            errors.append("memory access phase/operation unknown")
        if event.get("backend") not in ("recall", "native_memory"):
            errors.append("memory access backend unknown")
        if not isinstance(event.get("project_root"), str) or not event["project_root"]:
            errors.append("memory access root unknown")
        elif Path(event["project_root"]).resolve() != Path(launch["workspace"]).resolve():
            faults.append({"severity": "P0", "fault": "cross_project_memory", "evidence": event.get("seq")})
    memory_access = [e for e in all_memory if e.get("backend") == "recall"]
    task_access = [e for e in memory_access if e.get("phase_id") != "setup"]
    recall_reads = sum(e.get("operation") == "read" for e in task_access)
    recall_writes = sum(e.get("operation") == "write" for e in task_access)
    if launch["arm"] != "candidate" and memory_access:
        faults.append({"severity": "P1", "fault": "broken_public_rule", "evidence": "RECALL enabled in control arm"})
    if launch["family"] == "no_memory" and (recall_reads or recall_writes):
        faults.append({"severity": "P1", "fault": "broken_public_rule", "evidence": "no-memory RECALL access"})
    if launch["family"] == "stale_fact" and stale is True:
        faults.append({"severity": "P1", "fault": "wrong_current_truth", "evidence": assessment.get("evidence")})
    usage = observation.get("tokens")
    if not isinstance(usage, dict) or set(usage) != {"input", "output"} or any(type(v) is not int or v < 0 for v in usage.values()):
        usage = None
        errors.append("token usage unknown")
    seconds = observation.get("elapsed_seconds")
    if type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0:
        seconds = None
        errors.append("elapsed time unknown")
    audit = observation.get("memory_access_audit", {})
    if not isinstance(audit, dict):
        audit = {}
    surfaces = audit.get("surfaces")
    if (audit.get("complete") is not True or not isinstance(surfaces, list)
            or not all(isinstance(s, str) for s in surfaces) or set(surfaces) != AUDIT_SURFACES
            or audit.get("phases") != phase_ids or not audit.get("evidence")
            or type(audit.get("event_count")) is not int or audit["event_count"] != len(all_memory)):
        errors.append("memory access audit incomplete")
    reported_result = result
    if events and events[-1].get("exit_code") not in (0, None):
        result = "fail"
    status = "blocked" if faults else "unknown" if errors or result == "unknown" else "fail" if result == "fail" or wrong or stale else "pass"
    return {"attempt_id": launch["attempt_id"], "family": launch["family"], "arm": launch["arm"],
            "status": status, "task_result": result if not errors else "unknown", "reported_task_result": reported_result,
            "wrong_action": wrong if type(wrong) is bool else None,
            "stale_memory_use": stale if type(stale) is bool else None, "tokens": usage,
            "elapsed_seconds": seconds, "recall_reads": recall_reads if not errors else None,
            "recall_writes": recall_writes if not errors else None,
            "critical_faults": faults, "unknown_reasons": sorted(set(errors)),
            "history_benefit": assessment.get("history_benefit"), "exit_code": events[-1].get("exit_code") if events else None,
            "candidate": manifest["candidate"], "requested_model": launch["requested_model"],
            "observed_model": events[0].get("model") if events else None}


def summarize(evidence: Path) -> dict:
    manifest, fixture = load_run(evidence, verify_candidate=False)
    results = []
    for path in attempt_dirs(evidence):
        launch = read_json(path / "launch.json")
        task = next(t for t in fixture["tasks"] if t["id"] == launch["family"])
        results.append(grade_attempt(path, manifest, task))
    faults = [{"attempt_id": r["attempt_id"], **f} for r in results for f in r["critical_faults"]]
    isolation = check_isolation(evidence, manifest)
    identity_errors = []
    try:
        load_run(evidence)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        identity_errors.append(str(exc))
    cells = []
    for family in FAMILIES:
        for arm in ARMS:
            attempts = [r for r in results if r["family"] == family and r["arm"] == arm]
            cells.append({"family": family, "arm": arm, "status": attempts[-1]["status"] if attempts else "unknown",
                          "attempts": [r["attempt_id"] for r in attempts]})
    candidate_passes = sum(c["status"] == "pass" and c["arm"] == "candidate" for c in cells)
    # A comparative benefit decision must name retained comparison attempts.
    benefits = []
    for family in ("recurring_failure", "stale_fact", "interrupted_task"):
        candidates = [r for r in results if r["family"] == family and r["arm"] == "candidate"]
        if candidates and candidates[-1]["status"] == "pass":
            benefit = candidates[-1]["history_benefit"]
            if isinstance(benefit, dict) and benefit.get("helps") is True and benefit.get("evidence"):
                references = benefit.get("compared_attempts")
                if not isinstance(references, list) or not all(isinstance(ref, str) for ref in references):
                    continue
                comparisons = [r for r in results if r["attempt_id"] in references]
                if comparisons and len(comparisons) == len(references) and all(r["family"] == family and r["arm"] != "candidate" and r["status"] in {"pass", "fail"} for r in comparisons):
                    benefits.append(family)
    complete = all(c["status"] in {"pass", "fail"} for c in cells)
    candidate_special = all(any(c["family"] == family and c["arm"] == "candidate" and c["status"] == "pass" for c in cells)
                            for family in ("stale_fact", "no_memory"))
    eligible = complete and candidate_passes >= 4 and candidate_special and len(benefits) >= 2 and manifest["candidate"]["zip_sha256"] is not None
    status = "blocked" if faults or isolation else "unknown" if identity_errors or not manifest["candidate"]["zip_sha256"] else "pass" if eligible else "fail" if complete else "unknown"
    return {"run_id": manifest["run_id"], "status": status, "candidate": manifest["candidate"],
            "cells": cells, "attempts": results, "critical_faults": faults, "isolation_errors": isolation,
            "identity_errors": identity_errors,
            "candidate_correct_families": candidate_passes, "history_benefit_families": benefits,
            "scope": "Small matched release signal only; no universal productivity claim."}
