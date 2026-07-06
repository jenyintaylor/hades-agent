"""Hermex policy helpers for autonomous skill maintenance.

Foreground Hermes behavior stays unchanged. These helpers only become active
when Hermex prompt mode is enabled and the current write origin is the
background/self-improvement review path.
"""

from __future__ import annotations

import contextvars
import re
from pathlib import Path
from typing import Any, Iterable


_skill_index_reviewed: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "hermex_skill_index_reviewed",
    default=False,
)

_SUPPORT_DIRS = ("references", "templates", "scripts", "assets")
_GENERIC_TOKENS = {
    "agent",
    "agents",
    "guide",
    "hermes",
    "skill",
    "skills",
    "task",
    "tasks",
    "tool",
    "tools",
    "workflow",
    "workflows",
}
_SUPPORT_PATH_RE = re.compile(
    r"(?<![\w./-])((?:references|templates|scripts|assets)/[A-Za-z0-9_./<>*-]+)"
)


HERMEX_BACKGROUND_REVIEW_GUIDANCE = (
    "<hermex_self_improvement_contract>\n"
    "- Treat autonomous skill maintenance as a code-change discipline, not a "
    "diary-writing task.\n"
    "- Patch or extend an existing loaded skill first. Create a new skill only "
    "after scanning the skill index and confirming no existing class-level "
    "skill fits.\n"
    "- Every skill_manage mutation must include evidence: the observed problem, "
    "the completed task signal, or the fixture/eval/verification that justifies "
    "the change.\n"
    "- Read the exact target with skill_view before editing, patching, deleting, "
    "or overwriting supporting files. For new supporting files, read the parent "
    "skill first.\n"
    "- When consolidating, preserve support files and validate references before "
    "archiving a source skill.\n"
    "</hermex_self_improvement_contract>"
)


HERMEX_CURATOR_GUIDANCE = (
    "<hermex_curator_contract>\n"
    "- Prefer consolidation into existing umbrella skills over creating new "
    "skills. New umbrellas require evidence that no existing umbrella fits.\n"
    "- Every skill_manage call must include evidence. For delete/consolidation, "
    "that evidence must explain what was absorbed and where it now lives.\n"
    "- If a source skill has references/, templates/, scripts/, assets/, or "
    "SKILL.md links into those directories, preserve or re-home those files and "
    "set support_files_preserved=true on the delete call.\n"
    "- Validate that destination SKILL.md/support-file links resolve after each "
    "mutation; broken support references are not acceptable improvements.\n"
    "</hermex_curator_contract>"
)


def reset_maintenance_marks() -> None:
    _skill_index_reviewed.set(False)


def mark_skill_index_reviewed() -> None:
    _skill_index_reviewed.set(True)


def skill_index_reviewed() -> bool:
    return bool(_skill_index_reviewed.get())


def hermex_maintenance_enabled(config: dict[str, Any] | None = None) -> bool:
    try:
        from agent.prompt_policy import hermex_enabled

        if not hermex_enabled(config):
            return False
    except Exception:
        return False

    try:
        from tools.skill_provenance import is_background_review

        return bool(is_background_review())
    except Exception:
        return False


def _policy_error(message: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "success": False,
        "error": message,
        "_hermex_maintenance_required": True,
    }
    payload.update(extra)
    return payload


def _evidence_ok(evidence: Any) -> bool:
    return isinstance(evidence, str) and len(evidence.strip()) >= 20


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(token) >= 4 and token not in _GENERIC_TOKENS
    }


def _frontmatter_description(content: str) -> str:
    if not isinstance(content, str) or not content.startswith("---"):
        return ""
    end = re.search(r"\n---\s*\n", content[3:])
    if not end:
        return ""
    raw = content[3 : end.start() + 3]
    for line in raw.splitlines():
        if line.strip().lower().startswith("description:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def _find_overlapping_skills(name: str, content: str | None) -> list[str]:
    candidate_tokens = _tokens(name) | _tokens(_frontmatter_description(content or ""))
    if not candidate_tokens:
        return []
    try:
        from tools.skills_tool import _find_all_skills

        skills = _find_all_skills()
    except Exception:
        return []

    overlaps: list[str] = []
    for skill in skills:
        existing = str(skill.get("name") or "").strip()
        if not existing or existing == name:
            continue
        existing_tokens = _tokens(existing)
        if not existing_tokens:
            continue
        shared = candidate_tokens & existing_tokens
        if not shared:
            continue
        if existing_tokens.issubset(candidate_tokens) or candidate_tokens.issubset(existing_tokens):
            overlaps.append(existing)
            continue
        union = candidate_tokens | existing_tokens
        if len(shared) >= 2 and len(shared) / max(1, len(union)) >= 0.65:
            overlaps.append(existing)
    return overlaps[:5]


def evaluate_skill_write(
    *,
    action: str,
    name: str,
    evidence: str | None = None,
    content: str | None = None,
) -> dict[str, Any] | None:
    """Return a refusal payload for Hermex autonomous writes, else None."""
    if not hermex_maintenance_enabled():
        return None
    if action not in {"create", "edit", "patch", "delete", "write_file", "remove_file"}:
        return None

    if not _evidence_ok(evidence):
        return _policy_error(
            f"Refusing Hermex background skill {action} for '{name}': "
            "autonomous self-improvement writes must include explicit evidence "
            "or fixture/eval/verification support in the evidence field."
        )

    if action == "create":
        if not skill_index_reviewed():
            return _policy_error(
                f"Refusing Hermex background skill create for '{name}': call "
                "skills_list first and inspect existing skills. Hermex requires "
                "patch/merge-before-create to prevent skill-library bloat."
            )
        overlaps = _find_overlapping_skills(name, content)
        if overlaps:
            joined = ", ".join(overlaps)
            return _policy_error(
                f"Refusing Hermex background skill create for '{name}': existing "
                f"skill(s) look like a better patch/merge target: {joined}. "
                "Patch or add a support file to the existing umbrella unless "
                "you can prove none fits."
            )
    return None


def concrete_support_references(content: str) -> list[str]:
    refs: list[str] = []
    for match in _SUPPORT_PATH_RE.finditer(content or ""):
        ref = match.group(1).strip().strip("`'\".,;:)]}")
        if not ref or any(ch in ref for ch in "<>*"):
            continue
        refs.append(ref)
    return sorted(dict.fromkeys(refs))


def skill_has_support_package(skill_dir: Path) -> bool:
    for subdir in _SUPPORT_DIRS:
        root = skill_dir / subdir
        try:
            if root.is_dir() and any(path.is_file() for path in root.rglob("*")):
                return True
        except OSError:
            continue
    try:
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    except Exception:
        return False
    return bool(concrete_support_references(content))


def validate_skill_references(skill_dir: Path) -> list[str]:
    """Return missing concrete support-path references for one skill package."""
    missing: list[str] = []
    files: list[Path] = []
    try:
        if (skill_dir / "SKILL.md").is_file():
            files.append(skill_dir / "SKILL.md")
        for subdir in _SUPPORT_DIRS:
            root = skill_dir / subdir
            if root.is_dir():
                files.extend(path for path in root.rglob("*") if path.is_file())
    except OSError:
        return missing

    for file in files:
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for ref in concrete_support_references(content):
            if not (skill_dir / ref).exists():
                missing.append(ref)
    return sorted(dict.fromkeys(missing))


def validate_references_if_needed(skill_dir: Path) -> dict[str, Any] | None:
    if not hermex_maintenance_enabled():
        return None
    missing = validate_skill_references(skill_dir)
    if not missing:
        return None
    return _policy_error(
        "Hermex reference validation failed: skill instructions reference "
        f"missing support file(s): {', '.join(missing)}.",
        _hermex_reference_validation=True,
        missing_references=missing,
    )


def validate_consolidation_delete(
    *,
    source_skill_dir: Path,
    target_skill_dir: Path | None,
    support_files_preserved: bool = False,
) -> dict[str, Any] | None:
    if not hermex_maintenance_enabled():
        return None
    if target_skill_dir is None:
        return None
    if skill_has_support_package(source_skill_dir) and not support_files_preserved:
        return _policy_error(
            "Refusing Hermex consolidation delete: the source skill has support "
            "files or concrete support-file references. Preserve or re-home the "
            "support package first, then retry with support_files_preserved=true."
        )
    return validate_references_if_needed(target_skill_dir)


def evidence_suffix(evidence: Any, *, max_chars: int = 160) -> str:
    if not isinstance(evidence, str) or not evidence.strip():
        return ""
    text = " ".join(evidence.strip().split())
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return f" Evidence: {text}"
