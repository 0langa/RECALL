#!/usr/bin/env python3
"""Provider-neutral hook event normalization for RECALL adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import project_context


def _string(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _compact_json(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True)
        except TypeError:
            text = str(value)
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n[truncated]"
    return text


def _message_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).lower()
        if role not in {"assistant", "user", "system", ""}:
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
        elif isinstance(content, list):
            parts = [
                str(part["text"]).strip()
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
            ]
            if parts:
                texts.append("\n".join(parts))
    return texts


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list):
        return ""
    parts = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            text = item["text"].strip()
            if text:
                parts.append(text)
        elif isinstance(item, str) and item.strip():
            parts.append(item.strip())
    return "\n".join(parts)


def _tool_response(payload: dict[str, Any], raw: str, event_name: str) -> dict[str, Any]:
    response = payload.get("tool_response")
    if isinstance(response, dict):
        normalized = dict(response)
    elif response is not None:
        normalized = {"output": response}
    else:
        normalized = {}
    for source_name, target_name in (
        ("tool_output", "output"),
        ("output", "output"),
        ("result", "output"),
        ("stdout", "stdout"),
        ("stderr", "stderr"),
        ("error", "stderr"),
        ("message", "message"),
    ):
        value = payload.get(source_name)
        if value not in (None, "") and target_name not in normalized:
            normalized[target_name] = value
    if "exit_code" not in normalized:
        value = payload.get("exit_code")
        if isinstance(value, int):
            normalized["exit_code"] = value
        elif event_name in {"PostToolUseFailure", "StopFailure"}:
            normalized["exit_code"] = 1
    return normalized


@dataclass(frozen=True)
class HookEvent:
    provider: str
    event_name: str
    raw_payload: dict[str, Any]
    raw_text: str = ""
    cwd: str | None = None
    root: str | None = None
    session_id: str = ""
    turn_id: str = ""
    trigger: str = ""
    prompt: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_response: dict[str, Any] = field(default_factory=dict)
    command: str = ""
    stop_hook_active: bool = False
    transcript_path: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        raw_text: str = "",
        *,
        fallback_event: str,
        provider: str = "codex",
        fallback_root: str | None = None,
    ) -> "HookEvent":
        provider_name = str(payload.get("origin_provider") or payload.get("provider") or provider or "codex").strip().lower()
        event_name = _string(payload, "hook_event_name", "event") or fallback_event
        cwd = _string(payload, "cwd", "workspace", "project_dir")
        resolved_cwd = str(Path(cwd).resolve()) if cwd else None
        root: str | None
        if fallback_root:
            root = str(Path(fallback_root).expanduser().resolve())
        elif resolved_cwd:
            resolved = project_context.resolve_project_root(resolved_cwd)
            root = str(resolved) if resolved is not None else None
        else:
            root = None

        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        command = (
            _string(tool_input, "command", "cmd", "description")
            or _string(payload, "command", "cmd", "tool_command")
        )
        tool_response = _tool_response(payload, raw_text, event_name)
        prompt = (
            _content_text(payload.get("prompt"))
            or _content_text(payload.get("message"))
            or _content_text(payload.get("user_prompt"))
        )
        if not prompt and event_name == "UserPromptSubmit":
            prompt = raw_text.strip()

        return cls(
            provider=provider_name or "codex",
            event_name=event_name,
            raw_payload=payload,
            raw_text=raw_text,
            cwd=resolved_cwd,
            root=root,
            session_id=_string(payload, "session_id", "session"),
            turn_id=_string(payload, "turn_id", "message_id", "turn"),
            trigger=_string(payload, "trigger", "source", "reason", "matcher"),
            prompt=prompt,
            tool_name=_string(payload, "tool_name", "tool", "name"),
            tool_input=dict(tool_input),
            tool_response=tool_response,
            command=command,
            stop_hook_active=payload.get("stop_hook_active") is True,
            transcript_path=_string(payload, "transcript_path") or None,
        )

    def compatibility_payload(self) -> dict[str, Any]:
        payload = dict(self.raw_payload)
        payload.setdefault("hook_event_name", self.event_name)
        payload.setdefault("session_id", self.session_id)
        payload.setdefault("turn_id", self.turn_id)
        if self.cwd:
            payload.setdefault("cwd", self.cwd)
        if self.trigger:
            payload.setdefault("trigger", self.trigger)
        if self.tool_name:
            payload.setdefault("tool_name", self.tool_name)
        if self.tool_input:
            merged_input = dict(self.tool_input)
            if self.command and "command" not in merged_input:
                merged_input["command"] = self.command
            payload["tool_input"] = merged_input
        elif self.command:
            payload["tool_input"] = {"command": self.command}
        if self.tool_response:
            payload["tool_response"] = dict(self.tool_response)
        if self.prompt:
            payload["prompt"] = self.prompt
        payload.setdefault("origin_provider", self.provider)
        return payload

    def output_text(self) -> str:
        return "\n".join(
            part
            for part in [
                _compact_json(self.tool_response.get("stdout"), 1500),
                _compact_json(self.tool_response.get("stderr"), 1500),
                _compact_json(self.tool_response.get("output"), 1500),
                _compact_json(self.tool_response.get("message"), 800),
                f"exit_code: {self.tool_response.get('exit_code')}" if self.tool_response.get("exit_code") is not None else "",
                "success: true" if self.tool_response.get("success") is True else "",
                "success: false" if self.tool_response.get("success") is False else "",
            ]
            if part
        )

    def compaction_text(self) -> str:
        direct = (
            _string(self.raw_payload, "summary", "compaction_summary", "context", "notes")
            or _string(self.raw_payload, "last_assistant_message", "assistant_message")
        )
        if direct:
            return direct
        messages = _message_texts(self.raw_payload.get("messages") or self.raw_payload.get("transcript"))
        return "\n".join(messages[-8:]) if messages else ""

    def stop_text(self) -> str:
        direct = _string(
            self.raw_payload,
            "last_assistant_message",
            "assistant_message",
            "final_assistant_message",
            "summary",
        )
        if direct:
            return direct
        messages = _message_texts(self.raw_payload.get("messages") or self.raw_payload.get("transcript"))
        return messages[-1] if messages else ""

    def idempotency_key(self, fallback_event: str | None = None) -> str | None:
        tool_use_id = _string(self.raw_payload, "tool_use_id")
        if not tool_use_id and not self.turn_id:
            return None
        identity = {
            "provider": self.provider,
            "event": self.event_name or fallback_event or "",
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "tool_use_id": tool_use_id,
            "trigger": self.trigger,
        }
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
        return f"hook:{digest}"

    def provider_metadata(self, *, capture_channel: str) -> dict[str, str]:
        metadata = {
            "origin_provider": self.provider,
            "source_session": self.session_id,
            "source_turn": self.turn_id,
            "cwd": self.cwd or "",
            "capture_channel": capture_channel,
            "applies_to_provider": "all",
        }
        return {key: value for key, value in metadata.items() if value}
