from agent.prompt_policy import (
    DEFAULT_PROMPT_MODE,
    HERMEX_PROMPT_MODE,
    normalize_prompt_mode,
    resolve_prompt_policy,
)


def test_normalize_prompt_mode_defaults_unknown_values():
    assert normalize_prompt_mode(None) == DEFAULT_PROMPT_MODE
    assert normalize_prompt_mode("") == DEFAULT_PROMPT_MODE
    assert normalize_prompt_mode("unknown") == DEFAULT_PROMPT_MODE


def test_normalize_prompt_mode_accepts_hermex_aliases():
    assert normalize_prompt_mode("hermex") == HERMEX_PROMPT_MODE
    assert normalize_prompt_mode("codex-like") == HERMEX_PROMPT_MODE
    assert normalize_prompt_mode("strict_development") == HERMEX_PROMPT_MODE
    assert normalize_prompt_mode(True) == HERMEX_PROMPT_MODE


def test_resolve_prompt_policy_from_config_prompt_mode(monkeypatch):
    monkeypatch.delenv("HERMES_PROMPT_MODE", raising=False)
    monkeypatch.delenv("HERMES_HERMEX_MODE", raising=False)

    policy = resolve_prompt_policy({"agent": {"prompt_mode": "hermex"}})

    assert policy.mode == HERMEX_PROMPT_MODE
    assert policy.is_hermex
    assert policy.context_strategy == "layered"


def test_legacy_hermex_mode_config_alias(monkeypatch):
    monkeypatch.delenv("HERMES_PROMPT_MODE", raising=False)
    monkeypatch.delenv("HERMES_HERMEX_MODE", raising=False)

    assert resolve_prompt_policy({"agent": {"hermex_mode": True}}).is_hermex


def test_env_prompt_mode_wins(monkeypatch):
    monkeypatch.setenv("HERMES_PROMPT_MODE", "hermex")

    assert resolve_prompt_policy({"agent": {"prompt_mode": "default"}}).is_hermex


def test_env_hermex_mode_wins(monkeypatch):
    monkeypatch.delenv("HERMES_PROMPT_MODE", raising=False)
    monkeypatch.delenv("HERMEX_MODE", raising=False)
    monkeypatch.setenv("HERMES_HERMEX_MODE", "1")

    assert resolve_prompt_policy({"agent": {"prompt_mode": "default"}}).is_hermex


def test_env_short_hermex_mode_alias_wins(monkeypatch):
    monkeypatch.delenv("HERMES_PROMPT_MODE", raising=False)
    monkeypatch.delenv("HERMES_HERMEX_MODE", raising=False)
    monkeypatch.setenv("HERMEX_MODE", "1")

    assert resolve_prompt_policy({"agent": {"prompt_mode": "default"}}).is_hermex
