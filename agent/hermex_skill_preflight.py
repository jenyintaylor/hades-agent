"""Deterministic skill preloading for hermex prompt mode.

Hermes normally gives the model a compact skill index and lets the model choose
when to call ``skill_view``. Hermex mode keeps that behavior, but preloads full
skill instructions when the current user message clearly names an installed
skill. This mirrors Codex's stricter "load applicable instructions first"
instinct without adding fuzzy routing or changing default Hermes behavior.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

MAX_HERMEX_PRELOADED_SKILLS = 3
MAX_HERMEX_SKILL_CONTEXT_CHARS = 60_000

_SKILL_TOKEN = r"[A-Za-z0-9][A-Za-z0-9_:/.-]{1,127}"
_NAME_BOUNDARY_CHARS = r"A-Za-z0-9_:/.-"
_PRELOADED_SKILL_PREFIX = "[IMPORTANT: The user has invoked the "
_EXPLICIT_SKILL_PATTERNS = (
    re.compile(rf"(?<!\w)\$({_SKILL_TOKEN})"),
    re.compile(r"(?im)(?:^|\s)/([A-Za-z][A-Za-z0-9_-]{2,127})(?=\s|$|[,.!?;:])"),
    re.compile(rf"(?i)\bskills?\s*[:=]\s*[`'\"]?({_SKILL_TOKEN})"),
    re.compile(rf"(?i)\buse\s+(?:the\s+)?[`'\"]?({_SKILL_TOKEN})[`'\"]?\s+skill\b"),
)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _clean_candidate(raw: str) -> str:
    candidate = (raw or "").strip().strip("`'\".,;:()[]{}<>")
    candidate = candidate.replace("\\", "/")
    if not candidate:
        return ""
    if ".." in candidate or candidate.startswith(("-", "/")):
        return ""
    if re.search(r"\s", candidate):
        return ""
    return candidate


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _load_available_skill_names() -> list[str]:
    try:
        from tools.skills_tool import _find_all_skills

        return [
            str(skill.get("name") or "").strip()
            for skill in _find_all_skills()
            if str(skill.get("name") or "").strip()
        ]
    except Exception:
        logger.debug("Could not load skill index for hermex preflight", exc_info=True)
        return []


def _explicit_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in _EXPLICIT_SKILL_PATTERNS:
        for match in pattern.finditer(text):
            candidate = _clean_candidate(match.group(1))
            if candidate:
                candidates.append(candidate)
    return _ordered_unique(candidates)


def _indexed_candidates(text: str, available_skill_names: Sequence[str]) -> list[str]:
    matches: list[tuple[int, str]] = []
    for raw_name in available_skill_names:
        name = _clean_candidate(str(raw_name))
        # Very short names are too collision-prone for passive exact matching.
        # They can still be loaded through explicit forms such as "$pr".
        if len(name) < 3:
            continue
        pattern = re.compile(
            rf"(?<![{_NAME_BOUNDARY_CHARS}]){re.escape(name)}(?![{_NAME_BOUNDARY_CHARS}])",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            matches.append((match.start(), name))
    return _ordered_unique(name for _, name in sorted(matches, key=lambda item: item[0]))


def find_hermex_skill_candidates(
    user_message: Any,
    *,
    available_skill_names: Sequence[str] | None = None,
    max_skills: int = MAX_HERMEX_PRELOADED_SKILLS,
) -> list[str]:
    """Return high-confidence skill identifiers referenced by *user_message*.

    The matcher is intentionally conservative: explicit forms are always
    candidates, while passive text only matches exact names from the skill
    index. It does not infer by semantic similarity.
    """
    text = _content_to_text(user_message)
    if not text.strip() or max_skills <= 0:
        return []
    if text.startswith(_PRELOADED_SKILL_PREFIX):
        return []

    if available_skill_names is None:
        available_skill_names = _load_available_skill_names()

    merged = _ordered_unique(
        [*_explicit_candidates(text), *_indexed_candidates(text, available_skill_names)]
    )
    return merged[:max_skills]


def _truncate_context(context: str, max_chars: int) -> str:
    if max_chars <= 0 or len(context) <= max_chars:
        return context
    marker = (
        "\n\n[Hermex skill preload truncated because it exceeded the configured "
        "context cap. If more detail is needed, call skill_view for the named skill.]\n"
        "</hermex_preloaded_skills>"
    )
    keep = max(0, max_chars - len(marker))
    return context[:keep].rstrip() + marker


def build_hermex_skill_preload_context(
    user_message: Any,
    *,
    task_id: str | None = None,
    available_skill_names: Sequence[str] | None = None,
    max_skills: int = MAX_HERMEX_PRELOADED_SKILLS,
    max_chars: int = MAX_HERMEX_SKILL_CONTEXT_CHARS,
) -> str:
    """Load and render skill instructions for clear skill references.

    Returns an API-message-only context block, or an empty string when no skill
    should be preloaded.
    """
    candidates = find_hermex_skill_candidates(
        user_message,
        available_skill_names=available_skill_names,
        max_skills=max_skills,
    )
    if not candidates:
        return ""

    try:
        from agent.skill_commands import _build_skill_message, _load_skill_payload
    except Exception:
        logger.debug("Could not import skill loader for hermex preflight", exc_info=True)
        return ""

    blocks: list[str] = []
    for identifier in candidates:
        loaded = _load_skill_payload(identifier, task_id=task_id)
        if not loaded:
            continue
        loaded_skill, skill_dir, skill_name = loaded

        try:
            from tools.skill_usage import bump_use

            bump_use(skill_name)
        except Exception:
            pass

        activation_note = (
            f'[IMPORTANT: Hermex mode preloaded the "{skill_name}" skill because '
            "the current user message clearly referenced it before this model call. "
            "Treat its instructions as active guidance for this turn and follow the "
            "skill content before improvising.]"
        )
        blocks.append(
            _build_skill_message(
                loaded_skill,
                skill_dir,
                activation_note,
                runtime_note=(
                    "Hermex skill preloads are injected into the current API call "
                    "only and are not persisted to session history."
                ),
                session_id=task_id,
            )
        )

    if not blocks:
        return ""

    context = "\n\n".join(
        [
            "<hermex_preloaded_skills>",
            (
                "Hermex mode loaded these skill instructions deterministically from "
                "the current user message. Follow their activation notes and content "
                "when relevant to the user's requested work."
            ),
            *blocks,
            "</hermex_preloaded_skills>",
        ]
    )
    return _truncate_context(context, max_chars)
