import inspect


def test_task_capsule_frames_situation_report_requests():
    from agent.hermex_task_capsule import build_hermex_task_capsule

    capsule = build_hermex_task_capsule(
        "Give me a situation report on this codebase and recent changes."
    )

    assert "<hermex_task_capsule>" in capsule
    assert "Task kind: situation_report" in capsule
    assert "Objective: Give me a situation report" in capsule
    assert "Context sufficiency gate:" in capsule
    assert "Evidence plan:" in capsule
    assert "Stop criteria:" in capsule
    assert "avoid redundant reads" in capsule


def test_task_capsule_frames_code_change_requests():
    from agent.hermex_task_capsule import build_hermex_task_capsule

    capsule = build_hermex_task_capsule("Fix the failing tests in agent/turn_context.py")

    assert "Task kind: code_change" in capsule
    assert "inspect the relevant files" in capsule
    assert "run targeted verification" in capsule


def test_task_capsule_returns_empty_without_user_text():
    from agent.hermex_task_capsule import build_hermex_task_capsule

    assert build_hermex_task_capsule("") == ""
    assert build_hermex_task_capsule(None) == ""


def test_task_capsule_respects_max_chars():
    from agent.hermex_task_capsule import build_hermex_task_capsule

    capsule = build_hermex_task_capsule("review " + ("very long request " * 200), max_chars=700)

    assert len(capsule) <= 700
    assert capsule.endswith("</hermex_task_capsule>")


def test_conversation_loop_injects_hermex_task_capsule():
    from agent.conversation_loop import run_conversation

    source = inspect.getsource(run_conversation)

    assert "build_hermex_task_capsule" in source
    assert "_hermex_task_capsule" in source
