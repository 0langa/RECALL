"""Benchmark run orchestration: phases over scenarios, probes, and long runs."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import store_fabricator
from .drivers import PLUGIN_ROOT, AdapterDriver, HookDriver, McpClient
from .recorder import Recorder, Timer


def _project_signal(root: Path) -> None:
    (root / "pyproject.toml").write_text("[project]\nname='bench-fixture'\nversion='0.0.1'\n", encoding="utf-8")


def _hook_payload(root: Path, session: int, turn: int, event: str, **extra: Any) -> dict[str, Any]:
    return {
        "cwd": str(root),
        "session_id": f"bench-s{session}",
        "turn_id": f"bench-t{turn}",
        "hook_event_name": event,
        **extra,
    }


def _emit_hook_output(recorder: Recorder, output: dict[str, Any], *, channel: str, scenario: str, session: int, turn: int | None, surface: str, duration_ms: float) -> None:
    context = str((output.get("hookSpecificOutput") or {}).get("additionalContext") or "")
    if context:
        recorder.record(channel=channel, text=context, scenario=scenario, session=session, turn=turn, surface=surface, duration_ms=duration_ms)
    system_message = str(output.get("systemMessage") or "")
    if system_message:
        recorder.record(channel="stop_system_message" if surface == "stop" else "hook_error_message", text=system_message, scenario=scenario, session=session, turn=turn, surface=surface)
    if output.get("decision") == "block":
        recorder.record(channel="stop_finalizer_prompt", text=str(output.get("reason") or ""), scenario=scenario, session=session, turn=turn, surface=surface)


class BenchEngine:
    def __init__(self, recorder: Recorder, *, seed: int, keep_dirs: bool = False) -> None:
        self.recorder = recorder
        self.seed = seed
        self.keep_dirs = keep_dirs
        self.hooks = HookDriver()
        self.adapter = AdapterDriver()
        self._temp_dirs: list[Path] = []

    # ---------- phase: static fixed-cost surfaces ----------

    def measure_static_surfaces(self) -> None:
        mcp = McpClient()
        try:
            with Timer() as timer:
                init, _ = mcp.initialize()
            self.recorder.record(
                channel="mcp_initialize_instructions",
                text=str(init["result"].get("instructions") or ""),
                scenario="static", session=0, surface="mcp_initialize", duration_ms=timer.duration_ms,
            )
            tools, duration_ms = mcp.tools_list()
            self.recorder.record(
                channel="mcp_tools_list",
                text=json.dumps(tools["result"]["tools"], sort_keys=True),
                scenario="static", session=0, surface="mcp_tools_list", duration_ms=duration_ms,
            )
        finally:
            mcp.close()

        skills_dir = PLUGIN_ROOT / "skills"
        frontmatter_parts: list[str] = []
        for skill_path in sorted(skills_dir.glob("*/SKILL.md")):
            text = skill_path.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1] if text.startswith("---") else ""
            frontmatter_parts.append(frontmatter)
            self.recorder.record(
                channel="skill_body_invoked", text=text, scenario="static", session=0,
                surface=f"skill:{skill_path.parent.name}",
            )
        self.recorder.record(
            channel="skill_registry_metadata", text="\n".join(frontmatter_parts),
            scenario="static", session=0, surface="skill_frontmatter",
        )
        using_recall = (skills_dir / "using-recall" / "SKILL.md").read_text(encoding="utf-8")
        self.recorder.record(
            channel="skill_body_autoload", text=using_recall, scenario="static", session=0,
            surface="using-recall_sessionstart",
        )

    # ---------- phase: scenario turn simulation ----------

    def make_project(self, store: dict[str, Any], *, label: str) -> tuple[Path, dict[str, Any]]:
        root = Path(tempfile.mkdtemp(prefix=f"recall-bench-{label}-"))
        self._temp_dirs.append(root)
        _project_signal(root)
        manifest = store_fabricator.fabricate(
            root,
            tier=store["tier"],
            seed=self.seed,
            golden=store.get("golden", True),
            flagged=store.get("flagged", True),
            conflicts=store.get("conflicts", False),
            bad_pack=store.get("bad_pack", False),
        )
        return root, manifest

    def run_scenario(self, scenario: dict[str, Any], *, sessions: int, turn_limit: int | None) -> dict[str, Any]:
        name = scenario["name"]
        root, manifest = self.make_project(scenario["store"], label=name)
        turns = scenario["turns"]
        if turn_limit is not None:
            turns = turns[:turn_limit]
        labels: list[dict[str, Any]] = []
        self._snapshot_store(root, scenario=name, session=0)
        for session in range(1, sessions + 1):
            output, duration_ms = self.hooks.run(
                "session_start.py", _hook_payload(root, session, 0, "SessionStart", source="startup"),
            )
            self.recorder.latency(operation="hook.session_start", duration_ms=duration_ms, scenario=name, session=session)
            _emit_hook_output(self.recorder, output, channel="session_start_context", scenario=name, session=session, turn=None, surface="session_start", duration_ms=duration_ms)

            for position, turn in enumerate(turns, start=1):
                prompt = turn["prompt"]
                output, duration_ms = self.hooks.run(
                    "prompt_inspector.py", _hook_payload(root, session, position, "UserPromptSubmit", prompt=prompt),
                )
                self.recorder.latency(operation="hook.prompt_inspector", duration_ms=duration_ms, scenario=name, session=session, turn=position)
                context = str((output.get("hookSpecificOutput") or {}).get("additionalContext") or "")
                # Short single-line service messages (saved/defined/warnings) are
                # hook messages; anything longer is injected memory context.
                is_service_message = bool(context) and len(context) < 200 and "\n" not in context
                injected = bool(context) and not is_service_message
                if context:
                    channel = "prompt_hook_message" if is_service_message else "prompt_injection"
                    self.recorder.record(channel=channel, text=context, scenario=name, session=session, turn=position, surface="prompt_inspector", duration_ms=duration_ms)
                    if "conflict" in context.lower():
                        self.recorder.event("conflict_alert_seen", {"scenario": name, "session": session, "turn": position})
                # should_inject labels are ground truth against the FABRICATED
                # store only. From session 2 on (and in long-run replays) the
                # store has legitimately learned the repeated prompts, so
                # injecting on a turn labeled false is correct behavior, not a
                # gate error. Grade session 1 of normal scenarios only.
                if "should_inject" in turn and session == 1 and not name.startswith("longrun_"):
                    labels.append({
                        "scenario": name, "session": session, "turn": position,
                        "should_inject": turn["should_inject"], "injected": injected,
                    })
                    self.recorder.event("injection_decision", labels[-1])

                for tool in turn.get("tools", []):
                    output, duration_ms = self.hooks.run(
                        "post_tool_use.py",
                        _hook_payload(
                            root, session, position, "PostToolUse",
                            tool_name=tool.get("tool_name", "Bash"),
                            tool_input={"command": tool.get("command", "")},
                            tool_response={"output": tool.get("output", "")},
                        ),
                    )
                    self.recorder.latency(operation="hook.post_tool_use", duration_ms=duration_ms, scenario=name, session=session, turn=position)
                    _emit_hook_output(self.recorder, output, channel="hook_error_message", scenario=name, session=session, turn=position, surface="post_tool_use", duration_ms=duration_ms)

                if turn.get("precompact"):
                    output, duration_ms = self.hooks.run(
                        "pre_compact.py",
                        _hook_payload(root, session, position, "PreCompact", trigger="auto", transcript_summary=turn.get("stop_text", prompt)),
                    )
                    self.recorder.latency(operation="hook.pre_compact", duration_ms=duration_ms, scenario=name, session=session, turn=position)

                output, duration_ms = self.hooks.run(
                    "stop.py",
                    _hook_payload(root, session, position, "Stop", last_assistant_message=turn.get("stop_text", "")),
                )
                self.recorder.latency(operation="hook.stop", duration_ms=duration_ms, scenario=name, session=session, turn=position)
                _emit_hook_output(self.recorder, output, channel="stop_system_message", scenario=name, session=session, turn=position, surface="stop", duration_ms=duration_ms)

            self._snapshot_store(root, scenario=name, session=session)
        return {"root": root, "manifest": manifest, "labels": labels}

    def _snapshot_store(self, root: Path, *, scenario: str, session: int) -> None:
        import sqlite3

        db = root / ".recall" / "memory.sqlite"
        counts: dict[str, int] = {}
        statuses: dict[str, int] = {}
        total = 0
        if db.exists():
            connection = sqlite3.connect(db)
            try:
                for category, status, count in connection.execute(
                    "SELECT category, COALESCE(status, 'active'), COUNT(*) FROM memories GROUP BY category, COALESCE(status, 'active')"
                ):
                    counts[category] = counts.get(category, 0) + count
                    statuses[status] = statuses.get(status, 0) + count
                    total += count
            finally:
                connection.close()
        self.recorder.event(
            "store_snapshot",
            {
                "scenario": scenario, "session": session, "total": total,
                "categories": counts, "statuses": statuses,
                "db_bytes": db.stat().st_size if db.exists() else 0,
            },
        )

    def cleanup(self) -> None:
        if self.keep_dirs:
            return
        for path in self._temp_dirs:
            shutil.rmtree(path, ignore_errors=True)
