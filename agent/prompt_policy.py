"""Prompt policy selection for Hermes system-prompt assembly.

The default policy preserves Hermes' cache-optimized behavior.  ``hermex`` is
an opt-in, stricter coding/development policy that borrows Codex-like
instruction layering and verification expectations without changing the
default path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


DEFAULT_PROMPT_MODE = "default"
HERMEX_PROMPT_MODE = "hermex"

_HERMEX_ALIASES = {
    "hermex",
    "codex",
    "codex-like",
    "codex_like",
    "strict",
    "strict-development",
    "strict_development",
}
_DEFAULT_ALIASES = {"", "default", "hermes", "cache-optimized", "cache_optimized"}


HERMEX_EXECUTION_GUIDANCE = (
    "# Hermex mode\n"
    "<intent_interpretation>\n"
    "- Interpret the user's actual intent before acting. Prefer the most useful "
    "reading of an ambiguous coding/CLI request over a literal-but-unhelpful one.\n"
    "- Preserve every explicit constraint from the user, project instructions, "
    "loaded skills, and tool results. If those conflict, surface the conflict "
    "instead of silently choosing one.\n"
    "</intent_interpretation>\n"
    "\n"
    "<workspace_instincts>\n"
    "- Treat the active workspace as the source of truth. Inspect relevant files, "
    "git state, tests, and project instructions before changing code.\n"
    "- Follow layered project instructions from broadest scope to closest scope; "
    "closer instructions specialize earlier ones.\n"
    "</workspace_instincts>\n"
    "\n"
    "<tool_and_skill_discipline>\n"
    "- Use tools for grounded answers about files, commands, git state, current "
    "runtime state, and verification. Do not answer these from memory.\n"
    "- If a skill is loaded or selected for the task, treat its procedure and "
    "completion contract as binding unless the user overrides it.\n"
    "</tool_and_skill_discipline>\n"
    "\n"
    "<completion_gate>\n"
    "- Before finalizing, check that the result satisfies the user's intent, the "
    "loaded project instructions, any loaded skill contract, and available "
    "verification evidence. If verification is missing or blocked, say exactly "
    "what is missing or blocked.\n"
    "</completion_gate>"
)


@dataclass(frozen=True)
class PromptPolicy:
    """Resolved prompt behavior for one agent/session."""

    mode: str = DEFAULT_PROMPT_MODE

    @property
    def is_hermex(self) -> bool:
        return self.mode == HERMEX_PROMPT_MODE

    @property
    def context_strategy(self) -> str:
        return "layered" if self.is_hermex else "legacy"

    @property
    def force_verify_on_stop(self) -> bool:
        return self.is_hermex


def normalize_prompt_mode(value: Any) -> str:
    """Normalize config/env prompt-mode tokens."""
    if isinstance(value, bool):
        return HERMEX_PROMPT_MODE if value else DEFAULT_PROMPT_MODE
    token = str(value or "").strip().lower()
    if token in _HERMEX_ALIASES:
        return HERMEX_PROMPT_MODE
    if token in _DEFAULT_ALIASES:
        return DEFAULT_PROMPT_MODE
    return DEFAULT_PROMPT_MODE


def resolve_prompt_policy(config: dict[str, Any] | None = None) -> PromptPolicy:
    """Resolve prompt policy from env/config.

    Environment variables are intentionally narrow so gateway, CLI, and tests
    can force the same mode without adding per-surface plumbing:
    ``HERMES_PROMPT_MODE=hermex`` or ``HERMES_HERMEX_MODE=1``.
    """
    env_mode = os.environ.get("HERMES_PROMPT_MODE")
    if env_mode is not None:
        return PromptPolicy(normalize_prompt_mode(env_mode))

    env_hermex = os.environ.get("HERMES_HERMEX_MODE")
    if env_hermex is not None:
        token = env_hermex.strip().lower()
        return PromptPolicy(
            HERMEX_PROMPT_MODE
            if token not in {"0", "false", "no", "off", ""}
            else DEFAULT_PROMPT_MODE
        )

    if config is None:
        try:
            from hermes_cli.config import load_config

            config = load_config()
        except Exception:
            config = {}

    agent_cfg = (config or {}).get("agent") if isinstance(config, dict) else None
    if not isinstance(agent_cfg, dict):
        return PromptPolicy()

    if "hermex_mode" in agent_cfg:
        return PromptPolicy(normalize_prompt_mode(agent_cfg.get("hermex_mode")))

    return PromptPolicy(normalize_prompt_mode(agent_cfg.get("prompt_mode")))


def policy_for_agent(agent: Any) -> PromptPolicy:
    policy = getattr(agent, "_prompt_policy", None)
    if isinstance(policy, PromptPolicy):
        return policy
    mode = getattr(agent, "_prompt_mode", DEFAULT_PROMPT_MODE)
    return PromptPolicy(normalize_prompt_mode(mode))


def hermex_enabled(config: dict[str, Any] | None = None) -> bool:
    return resolve_prompt_policy(config).is_hermex

