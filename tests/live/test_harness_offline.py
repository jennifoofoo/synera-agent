import json

from tests.live.harness import Transcript, Turn, calls_in


def fake_messages():
    return [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "propose_change", "input": {"action": "close"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "card", "is_error": False}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "confirm_change", "input": {"confirmed": True}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": json.dumps({"applied": True})}]}]},
    ]


def test_calls_are_paired_with_their_results():
    calls = calls_in(fake_messages())
    assert [call.name for call in calls] == ["propose_change", "confirm_change"]
    assert calls[0].result == "card"
    assert json.loads(calls[1].result) == {"applied": True}


def test_applied_changes_reports_the_turn_of_the_confirmation():
    transcript = Transcript([Turn("sperr", "karte", calls_in(fake_messages()[:2])), Turn("ja", "ok", calls_in(fake_messages()[2:]))])
    assert transcript.applied_changes() == [1]
    assert transcript.calls("propose_change")[0][0] == 0
