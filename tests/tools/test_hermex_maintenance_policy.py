import json
from contextlib import contextmanager
from unittest.mock import patch

from agent.background_review import summarize_background_review_actions
from tools.skill_manager_tool import SKILL_MANAGE_SCHEMA, skill_manage
from tools.skills_tool import skills_list, skill_view


def _skill_content(name: str, body: str = "Step 1: Do the thing.") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {name} workflow.\n"
        "---\n\n"
        f"# {name}\n\n"
        f"{body}\n"
    )


@contextmanager
def _hermex_background_skills(tmp_path, monkeypatch):
    from agent.hermex_maintenance_policy import reset_maintenance_marks

    home = tmp_path / ".hermes"
    skills_root = home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_PROMPT_MODE", "hermex")
    reset_maintenance_marks()
    with (
        patch("tools.skill_manager_tool.SKILLS_DIR", skills_root),
        patch("tools.skills_tool.SKILLS_DIR", skills_root),
        patch("agent.skill_utils.get_all_skills_dirs", return_value=[skills_root]),
        patch("tools.skill_provenance.is_background_review", return_value=True),
    ):
        yield skills_root
    reset_maintenance_marks()


@contextmanager
def _default_background_skills(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    skills_root = home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_PROMPT_MODE", raising=False)
    monkeypatch.delenv("HERMES_HERMEX_MODE", raising=False)
    with (
        patch("tools.skill_manager_tool.SKILLS_DIR", skills_root),
        patch("tools.skills_tool.SKILLS_DIR", skills_root),
        patch("agent.skill_utils.get_all_skills_dirs", return_value=[skills_root]),
        patch("tools.skill_provenance.is_background_review", return_value=True),
    ):
        yield skills_root


def test_default_background_create_without_evidence_is_unchanged(tmp_path, monkeypatch):
    with _default_background_skills(tmp_path, monkeypatch):
        result = json.loads(
            skill_manage(
                action="create",
                name="new-skill",
                content=_skill_content("new-skill"),
            )
        )

    assert result["success"] is True, result


def test_skill_manage_schema_exposes_hermex_maintenance_fields():
    properties = SKILL_MANAGE_SCHEMA["parameters"]["properties"]

    assert "evidence" in properties
    assert "support_files_preserved" in properties


def test_hermex_background_create_requires_evidence(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        json.loads(skills_list())
        result = json.loads(
            skill_manage(
                action="create",
                name="new-skill",
                content=_skill_content("new-skill"),
            )
        )

    assert result["success"] is False
    assert result.get("_hermex_maintenance_required") is True
    assert "evidence" in result["error"].lower()


def test_hermex_background_create_requires_skill_index_scan(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        result = json.loads(
            skill_manage(
                action="create",
                name="new-skill",
                content=_skill_content("new-skill"),
                evidence="Confirmed this is a reusable workflow from the completed task.",
            )
        )

    assert result["success"] is False
    assert result.get("_hermex_maintenance_required") is True
    assert "skills_list" in result["error"]


def test_hermex_background_create_rejects_obvious_existing_umbrella(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        assert json.loads(
            skill_manage(
                action="create",
                name="devops-deploy",
                content=_skill_content("devops-deploy"),
                evidence="Initial fixture skill for the maintenance policy test.",
            )
        )["success"] is False
        # Seed the existing skill directly through the default path so the test
        # focuses on overlap detection for the second create.
        (tmp_path / ".hermes" / "skills" / "devops-deploy").mkdir(parents=True, exist_ok=True)
        (
            tmp_path / ".hermes" / "skills" / "devops-deploy" / "SKILL.md"
        ).write_text(_skill_content("devops-deploy"), encoding="utf-8")

        json.loads(skills_list())
        result = json.loads(
            skill_manage(
                action="create",
                name="devops-deploy-timeout",
                content=_skill_content("devops-deploy-timeout"),
                evidence="A deployment timeout lesson was observed and should be retained.",
            )
        )

    assert result["success"] is False
    assert result.get("_hermex_maintenance_required") is True
    assert "devops-deploy" in result["error"]
    assert "patch" in result["error"].lower()


def test_hermex_background_create_allows_new_class_after_scan_and_evidence(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        json.loads(skills_list())
        result = json.loads(
            skill_manage(
                action="create",
                name="release-coordination",
                content=_skill_content("release-coordination"),
                evidence="No existing skill covers release handoff coordination; the completed task exposed a reusable workflow.",
            )
        )

    assert result["success"] is True, result


def test_hermex_new_support_file_requires_parent_skill_read(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        json.loads(skills_list())
        assert json.loads(
            skill_manage(
                action="create",
                name="reviewed",
                content=_skill_content("reviewed"),
                evidence="Seed skill for support-file policy test after scanning existing skills.",
            )
        )["success"] is True

        blocked = json.loads(
            skill_manage(
                action="write_file",
                name="reviewed",
                file_path="references/workflow.md",
                file_content="Workflow evidence.\n",
                evidence="The new reference captures reusable verification details from the task.",
            )
        )
        assert blocked["success"] is False
        assert blocked.get("_read_before_write_required") is True

        assert json.loads(skill_view("reviewed"))["success"] is True
        allowed = json.loads(
            skill_manage(
                action="write_file",
                name="reviewed",
                file_path="references/workflow.md",
                file_content="Workflow evidence.\n",
                evidence="The new reference captures reusable verification details from the task.",
            )
        )

    assert allowed["success"] is True, allowed


def test_hermex_consolidation_with_support_files_requires_preservation_flag(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        json.loads(skills_list())
        for name in ("umbrella", "narrow"):
            assert json.loads(
                skill_manage(
                    action="create",
                    name=name,
                    content=_skill_content(name),
                    evidence=f"Seed {name} for consolidation policy test after scanning existing skills.",
                )
            )["success"] is True
        assert json.loads(skill_view("narrow"))["success"] is True
        assert json.loads(
            skill_manage(
                action="write_file",
                name="narrow",
                file_path="references/detail.md",
                file_content="Important supporting detail.\n",
                evidence="The source skill has support details that must be preserved in consolidation.",
            )
        )["success"] is True
        assert json.loads(skill_view("umbrella"))["success"] is True

        blocked = json.loads(
            skill_manage(
                action="delete",
                name="narrow",
                absorbed_into="umbrella",
                evidence="Merged the narrow workflow into umbrella.",
            )
        )

        assert blocked["success"] is False
        assert blocked.get("_hermex_maintenance_required") is True
        assert "support" in blocked["error"].lower()

        allowed = json.loads(
            skill_manage(
                action="delete",
                name="narrow",
                absorbed_into="umbrella",
                evidence="Merged the narrow workflow and moved supporting details into the umbrella package.",
                support_files_preserved=True,
            )
        )

    assert allowed["success"] is True, allowed


def test_hermex_reference_validation_rolls_back_broken_skill_links(tmp_path, monkeypatch):
    with _hermex_background_skills(tmp_path, monkeypatch):
        json.loads(skills_list())
        assert json.loads(
            skill_manage(
                action="create",
                name="reviewed",
                content=_skill_content("reviewed"),
                evidence="Seed skill for reference validation policy test after scanning existing skills.",
            )
        )["success"] is True
        assert json.loads(skill_view("reviewed"))["success"] is True

        result = json.loads(
            skill_manage(
                action="patch",
                name="reviewed",
                old_string="Step 1: Do the thing.",
                new_string="Step 1: Do the thing.\n\nSee `references/missing.md`.",
                evidence="The task suggested a reusable missing-reference workflow.",
            )
        )

        skill_md = tmp_path / ".hermes" / "skills" / "reviewed" / "SKILL.md"

    assert result["success"] is False
    assert result.get("_hermex_reference_validation") is True
    assert "references/missing.md" not in skill_md.read_text(encoding="utf-8")


def test_background_review_summary_includes_skill_evidence():
    review_messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {
                        "name": "skill_manage",
                        "arguments": json.dumps(
                            {
                                "action": "patch",
                                "name": "reviewed",
                                "old_string": "old",
                                "new_string": "new",
                                "evidence": "fixture reproduced and patch corrected the reusable workflow",
                            }
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": json.dumps(
                {"success": True, "message": "Patched SKILL.md in skill 'reviewed' (1 replacement)."}
            ),
        },
    ]

    actions = summarize_background_review_actions(
        review_messages,
        prior_snapshot=[],
        notification_mode="on",
    )

    assert actions == [
        "Patched SKILL.md in skill 'reviewed' (1 replacement). Evidence: fixture reproduced and patch corrected the reusable workflow"
    ]
