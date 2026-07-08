import inspect
import json


def _assistant_tool_call(call_id, name, args):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args),
        },
    }


def _tool_result(call_id, name, content="ok"):
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "tool_name": name,
        "content": content,
    }


def test_working_ledger_tracks_completed_file_reads_and_skill_loads():
    from agent.hermex_working_ledger import build_hermex_working_ledger

    messages = [
        {"role": "user", "content": "review this"},
        {
            "role": "assistant",
            "tool_calls": [
                _assistant_tool_call("read-1", "read_file", {"path": "agent/turn_context.py"}),
                _assistant_tool_call("skill-1", "skill_view", {"name": "development-operating-procedure"}),
            ],
        },
        _tool_result("read-1", "read_file", "file contents"),
        _tool_result("skill-1", "skill_view", "skill contents"),
    ]

    ledger = build_hermex_working_ledger(messages)

    assert "<hermex_working_ledger>" in ledger
    assert "Already inspected files:" in ledger
    assert "- agent/turn_context.py" in ledger
    assert "Already loaded skills:" in ledger
    assert "- development-operating-procedure" in ledger
    assert "avoid redundant tool calls" in ledger


def test_working_ledger_ignores_unfinished_tool_calls_and_dedupes():
    from agent.hermex_working_ledger import build_hermex_working_ledger

    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                _assistant_tool_call("read-1", "read_file", {"path": "agent/turn_context.py"}),
                _assistant_tool_call("read-2", "read_file", {"path": "agent/turn_context.py"}),
                _assistant_tool_call("read-unfinished", "read_file", {"path": "agent/system_prompt.py"}),
            ],
        },
        _tool_result("read-1", "read_file"),
        _tool_result("read-2", "read_file"),
    ]

    ledger = build_hermex_working_ledger(messages)

    assert ledger.count("agent/turn_context.py") == 1
    assert "agent/system_prompt.py" not in ledger


def test_working_ledger_returns_empty_without_relevant_completed_tools():
    from agent.hermex_working_ledger import build_hermex_working_ledger

    assert build_hermex_working_ledger([{"role": "user", "content": "hello"}]) == ""


def test_working_ledger_respects_max_chars():
    from agent.hermex_working_ledger import build_hermex_working_ledger

    messages = []
    tool_calls = []
    for idx in range(30):
        call_id = f"read-{idx}"
        tool_calls.append(
            _assistant_tool_call(call_id, "read_file", {"path": f"very/long/path/{idx}/file.py"})
        )
        messages.append(_tool_result(call_id, "read_file"))
    messages.insert(0, {"role": "assistant", "tool_calls": tool_calls})

    ledger = build_hermex_working_ledger(messages, max_chars=500)

    assert len(ledger) <= 500
    assert ledger.endswith("</hermex_working_ledger>")


def test_conversation_loop_injects_hermex_working_ledger():
    from agent.conversation_loop import run_conversation

    source = inspect.getsource(run_conversation)

    assert "build_hermex_working_ledger" in source
    assert "_hermex_working_ledger" in source
