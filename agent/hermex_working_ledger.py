"""Compact Hermex working ledger derived from completed tool calls.

The ledger is API-call-only context. It does not persist state and does not
summarize tool contents; it only reminds the model which expensive grounding
steps already happened in the current visible history.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterable


DEFAULT_HERMEX_LEDGER_MAX_ITEMS = 12
DEFAULT_HERMEX_LEDGER_MAX_CHARS = 3000

_FILE_READ_TOOLS = frozenset({"read_file"})
_SKILL_LOAD_TOOLS = frozenset({"skill_view"})


def _ordered_add(values: list[str], seen: set[str], value: Any) -> None:
    text = str(value or "").strip()
    if not text:
        return
    key = text.casefold()
    if key in seen:
        return
    seen.add(key)
    values.append(text)


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tool_call_fields(tool_call: Any) -> tuple[str, str, dict[str, Any]]:
    if isinstance(tool_call, dict):
        call_id = str(tool_call.get("id") or "")
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        name = str(function.get("name") or tool_call.get("name") or "")
        args = _parse_tool_args(function.get("arguments", tool_call.get("arguments")))
        return call_id, name, args

    call_id = str(getattr(tool_call, "id", "") or "")
    function = getattr(tool_call, "function", None)
    name = str(getattr(function, "name", "") or getattr(tool_call, "name", "") or "")
    args = _parse_tool_args(getattr(function, "arguments", None))
    return call_id, name, args


def _completed_tool_call_ids(messages: Iterable[dict[str, Any]]) -> set[str]:
    completed: set[str] = set()
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        call_id = str(msg.get("tool_call_id") or "")
        if call_id:
            completed.add(call_id)
    return completed


def _truncate_ledger(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    closing = "\n[ledger truncated]\n</hermex_working_ledger>"
    keep = max(0, max_chars - len(closing))
    return text[:keep].rstrip() + closing


def build_hermex_working_ledger(
    messages: Iterable[dict[str, Any]],
    *,
    max_items: int = DEFAULT_HERMEX_LEDGER_MAX_ITEMS,
    max_chars: int = DEFAULT_HERMEX_LEDGER_MAX_CHARS,
) -> str:
    """Return a bounded reminder of completed grounding work, or ``""``."""
    message_list = [msg for msg in messages if isinstance(msg, dict)]
    completed_ids = _completed_tool_call_ids(message_list)
    if not completed_ids:
        return ""

    inspected_files: list[str] = []
    inspected_seen: set[str] = set()
    loaded_skills: list[str] = []
    skill_seen: set[str] = set()
    completed_tool_counts: Counter[str] = Counter()

    for msg in message_list:
        if msg.get("role") != "assistant":
            continue
        for tool_call in msg.get("tool_calls") or []:
            call_id, name, args = _tool_call_fields(tool_call)
            if call_id and call_id not in completed_ids:
                continue
            if not name:
                continue
            completed_tool_counts[name] += 1
            if name in _FILE_READ_TOOLS:
                _ordered_add(inspected_files, inspected_seen, args.get("path"))
            elif name in _SKILL_LOAD_TOOLS:
                skill_name = args.get("name") or args.get("skill") or args.get("skill_name")
                file_path = args.get("file_path")
                if skill_name and file_path:
                    skill_name = f"{skill_name} ({file_path})"
                _ordered_add(loaded_skills, skill_seen, skill_name)

    if not inspected_files and not loaded_skills and not completed_tool_counts:
        return ""

    lines = [
        "<hermex_working_ledger>",
        (
            "Use this ledger to avoid redundant tool calls. Tool results already "
            "present in the conversation are the source of truth; re-read or "
            "reload only when checking changed content, exact line references, "
            "or missing detail."
        ),
    ]
    if loaded_skills:
        lines.append("Already loaded skills:")
        lines.extend(f"- {name}" for name in loaded_skills[:max_items])
    if inspected_files:
        lines.append("Already inspected files:")
        lines.extend(f"- {path}" for path in inspected_files[:max_items])
    if completed_tool_counts:
        lines.append("Completed tool calls this turn/history:")
        for name, count in sorted(completed_tool_counts.items()):
            suffix = f" x{count}" if count > 1 else ""
            lines.append(f"- {name}{suffix}")
    lines.append("</hermex_working_ledger>")
    return _truncate_ledger("\n".join(lines), max_chars)
