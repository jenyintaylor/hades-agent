"""Small Hermex task capsule for using reasoning budget deliberately."""

from __future__ import annotations

from typing import Any


DEFAULT_HERMEX_TASK_CAPSULE_MAX_CHARS = 1600
_OBJECTIVE_MAX_CHARS = 360


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return ""


def _truncate_text(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    marker = "..."
    keep = max(0, max_chars - len(marker))
    return text[:keep].rstrip() + marker


def _classify_task_kind(user_text: str) -> str:
    lower = user_text.lower()
    if any(term in lower for term in ("situation report", "scope out", "codebase overview", "status report")):
        return "situation_report"
    if any(term in lower for term in ("review", "diff", "changes", "pr ", "pull request")):
        return "review"
    if any(term in lower for term in ("fix", "implement", "add ", "change", "update", "remove", "refactor")):
        return "code_change"
    if any(term in lower for term in ("debug", "failing", "failure", "error", "traceback", "bug")):
        return "debugging"
    if any(term in lower for term in ("plan", "design", "approach", "strategy")):
        return "planning"
    return "answer"


def _evidence_plan(task_kind: str) -> str:
    if task_kind == "situation_report":
        return (
            "start from git status/diff/log and project manifests, then inspect only "
            "files needed to explain current state; avoid redundant reads."
        )
    if task_kind == "review":
        return (
            "inspect changed files and relevant tests/configuration before judging "
            "risk; avoid rereading files already covered by the working ledger."
        )
    if task_kind == "code_change":
        return (
            "inspect the relevant files, make the smallest coherent change, and run "
            "targeted verification."
        )
    if task_kind == "debugging":
        return (
            "reproduce or inspect the failing path first, identify the causal branch, "
            "then verify the fix with a targeted check."
        )
    if task_kind == "planning":
        return "ground the plan in repo facts and constraints before proposing work."
    return "answer directly when enough context is already available; use tools only for specific missing facts."


def build_hermex_task_capsule(
    user_message: Any,
    *,
    max_chars: int = DEFAULT_HERMEX_TASK_CAPSULE_MAX_CHARS,
) -> str:
    """Return a compact per-turn operating frame for Hermex, or ``""``."""
    user_text = _content_to_text(user_message)
    if not user_text:
        return ""

    task_kind = _classify_task_kind(user_text)
    objective = _truncate_text(user_text, _OBJECTIVE_MAX_CHARS)
    lines = [
        "<hermex_task_capsule>",
        f"Task kind: {task_kind}",
        f"Objective: {objective}",
        "Context sufficiency gate:",
        (
            "- Before reading files, loading skills, or querying LCM/memory, check "
            "the working ledger and already injected context. Use a tool only for "
            "a specific missing fact, changed content, or exact citation."
        ),
        "Evidence plan:",
        f"- {_evidence_plan(task_kind)}",
        "Stop criteria:",
        (
            "- Stop gathering context when the objective can be answered or acted on "
            "with available evidence; then synthesize known facts, open gaps, and "
            "verification status."
        ),
        "</hermex_task_capsule>",
    ]
    capsule = "\n".join(lines)
    if max_chars <= 0 or len(capsule) <= max_chars:
        return capsule
    closing = "\n[capsule truncated]\n</hermex_task_capsule>"
    keep = max(0, max_chars - len(closing))
    return capsule[:keep].rstrip() + closing
