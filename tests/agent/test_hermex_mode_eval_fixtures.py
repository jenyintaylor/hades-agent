import json
from pathlib import Path

import pytest

from agent.hermex_skill_preflight import find_hermex_skill_candidates
from agent.prompt_policy import resolve_prompt_policy


CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "hermex_mode" / "cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", [c for c in CASES if c["kind"] == "prompt_policy"])
def test_hermex_prompt_policy_eval_cases(case, monkeypatch):
    monkeypatch.delenv("HERMES_PROMPT_MODE", raising=False)
    monkeypatch.delenv("HERMES_HERMEX_MODE", raising=False)

    policy = resolve_prompt_policy(case["config"])

    assert policy.mode == case["expected_mode"]
    assert policy.is_hermex is case["expected_is_hermex"]


@pytest.mark.parametrize("case", [c for c in CASES if c["kind"] == "skill_candidates"])
def test_hermex_skill_candidate_eval_cases(case):
    candidates = find_hermex_skill_candidates(
        case["user_message"],
        available_skill_names=case["available_skill_names"],
    )

    assert candidates == case["expected_candidates"]
