from unittest.mock import patch

from agent.hermex_skill_preflight import (
    build_hermex_skill_preload_context,
    find_hermex_skill_candidates,
)


def _make_skill(skills_dir, name, body="Follow the contract block exactly."):
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""\
---
name: {name}
description: Description for {name}.
---

# {name}

{body}
""",
        encoding="utf-8",
    )
    return skill_dir


def test_find_candidates_from_exact_indexed_skill_name():
    candidates = find_hermex_skill_candidates(
        "Please use development-operating-procedure for this change.",
        available_skill_names=[
            "development-operating-procedure",
            "kanban-task-executor",
        ],
    )

    assert candidates == ["development-operating-procedure"]


def test_find_candidates_from_explicit_dollar_qualified_skill():
    candidates = find_hermex_skill_candidates(
        "Use $superpowers:writing-plans and then continue.",
        available_skill_names=[],
    )

    assert candidates == ["superpowers:writing-plans"]


def test_find_candidates_ignores_short_substring_skill_names():
    candidates = find_hermex_skill_candidates(
        "Please improve the project.",
        available_skill_names=["pr"],
    )

    assert candidates == []


def test_find_candidates_skips_already_expanded_skill_invocations():
    candidates = find_hermex_skill_candidates(
        '[IMPORTANT: The user has invoked the "test-skill" skill, indicating '
        "they want you to follow its instructions. The full skill content is loaded below.]\n\n"
        "# test-skill\n\nUse development-operating-procedure only as an example.",
        available_skill_names=["test-skill", "development-operating-procedure"],
    )

    assert candidates == []


def test_build_context_loads_referenced_skill(tmp_path):
    with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
        _make_skill(tmp_path, "development-operating-procedure")
        context = build_hermex_skill_preload_context(
            "Use development-operating-procedure for this.",
            available_skill_names=["development-operating-procedure"],
        )

    assert "<hermex_preloaded_skills>" in context
    assert 'Hermex mode preloaded the "development-operating-procedure" skill' in context
    assert "Follow the contract block exactly." in context


def test_build_context_returns_empty_without_candidates(tmp_path):
    with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
        _make_skill(tmp_path, "development-operating-procedure")
        context = build_hermex_skill_preload_context(
            "Just answer normally.",
            available_skill_names=["development-operating-procedure"],
        )

    assert context == ""


def test_build_context_caps_loaded_skills(tmp_path):
    with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
        _make_skill(tmp_path, "first-skill")
        _make_skill(tmp_path, "second-skill")
        _make_skill(tmp_path, "third-skill")
        context = build_hermex_skill_preload_context(
            "Use first-skill, second-skill, and third-skill.",
            available_skill_names=["first-skill", "second-skill", "third-skill"],
            max_skills=2,
        )

    assert "first-skill" in context
    assert "second-skill" in context
    assert "third-skill" not in context
