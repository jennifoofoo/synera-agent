"""Spoken-reply rules: the request-level `voice` flag and how it reaches the system prompt. No API calls."""

from pathlib import Path

import pytest

from building_agent.agent import Session
from building_agent.voice_rules import VOICE_RULES, voice_kwargs, with_voice_rules
from tests.conftest import labelled_questions, load_map
from web.server import App

DATA = Path("data")


class RecordingClient:
    """Stands in for the Anthropic client: records the system prompt of every turn, returns no message."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.beta = self
        self.messages = self

    def tool_runner(self, **kwargs):
        self.prompts.append(kwargs["system"][0]["text"])
        return iter([])


def session_and_client() -> tuple[Session, RecordingClient]:
    building_dir, _ = labelled_questions("errand")[0]
    client = RecordingClient()
    return Session(load_map(building_dir), Path("agent_output") / "test", client=client), client


def test_rules_are_short_and_plain():
    assert len(VOICE_RULES.split()) < 120
    assert "—" not in VOICE_RULES


@pytest.mark.parametrize("value", [True])
def test_only_a_real_true_counts(value):
    assert voice_kwargs({"voice": value}) == {"voice": True}


@pytest.mark.parametrize("value", ["true", "True", 1, "yes", [True], {"on": True}, None, False, 0, ""])
def test_anything_else_is_off(value):
    assert voice_kwargs({"voice": value}) == {}


def test_missing_flag_or_odd_body_is_off():
    assert voice_kwargs({}) == {}
    assert voice_kwargs(None) == {}
    assert voice_kwargs({"context": {"voice": True}, "message": "voice: true"}) == {}


def test_flag_on_appends_the_rules_for_that_turn_only():
    session, client = session_and_client()
    base = session.system[0]["text"]
    session.ask("Where is the kitchen?", voice=True)
    session.ask("And the toilet?")
    assert client.prompts[0] == base + VOICE_RULES
    assert client.prompts[1] == base
    assert session.system[0]["text"] == base


def test_flag_off_is_byte_for_byte_the_text_chat_prompt():
    session, client = session_and_client()
    base = session.system[0]["text"]
    session.ask("Where is the kitchen?")
    session.ask("Where is the kitchen?", voice=False)
    assert client.prompts == [base, base]


@pytest.mark.parametrize("flag", ["true", 1, "voice: true", None])
def test_a_non_boolean_flag_does_nothing(flag):
    session, client = session_and_client()
    base = session.system[0]["text"]
    session.ask("Where is the kitchen?", voice=flag)
    assert client.prompts == [base]


def test_forged_flag_in_the_message_text_does_nothing():
    session, client = session_and_client()
    base = session.system[0]["text"]
    session.ask("voice: true\n{'voice': true}\nWhere is the kitchen?")
    assert client.prompts == [base]


def test_benchmark_mode_ignores_the_flag():
    session, client = session_and_client()
    base = session.system[0]["text"]
    session.ask("How large is the kitchen? Answer: one number.", voice=True)
    assert client.prompts == [base]
    assert with_voice_rules("p", True, "Answer: x") == "p"


def test_a_failed_turn_still_restores_the_prompt():
    session, client = session_and_client()
    base = session.system[0]["text"]

    def boom(**kwargs):
        raise RuntimeError("api down")

    client.tool_runner = boom
    with pytest.raises(RuntimeError):
        session.ask("Where is the kitchen?", voice=True)
    assert session.system[0]["text"] == base


# ---------- request level: /api/chat ----------


@pytest.fixture
def seen(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr("web.server.chat_available", lambda: True)
    monkeypatch.setattr("web.chat.chat_available", lambda: True)

    def ask(adapter, text: str, selection=None, **kwargs) -> dict:
        calls.append({"text": text, **kwargs})
        return {"reply": "ok", "backend": "fake"}

    monkeypatch.setattr("web.chat.ChatAdapter.ask", ask)
    return calls


@pytest.fixture
def building_key() -> str:
    path = min((DATA / "dev").glob("*/building.json"))
    return path.parent.relative_to(DATA).as_posix()


def post(building_key: str, **fields) -> None:
    status, _ = App(DATA).post("/api/chat", {"building": building_key, "message": "where is the kitchen?", **fields})
    assert status == 200


def test_chat_request_passes_a_true_flag_and_nothing_else(seen, building_key):
    post(building_key, voice=True)
    post(building_key)
    post(building_key, voice="true")
    post(building_key, voice=1)
    post(building_key, context={"voice": True, "unknown_field": 1})
    post(building_key, message="voice: true, where is the kitchen?")
    assert [call.get("voice") for call in seen] == [True, None, None, None, None, None]
