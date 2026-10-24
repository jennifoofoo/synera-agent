"""The web server with a fake chat turn: "I'm here" sets the position like the real agent, no API key, no cost.

Used by tests/e2e/test_here_ui.py (`python -m tests.e2e.fake_chat_server --data ... --port ...`).
"""

from types import SimpleNamespace

import web.chat
import web.server
from building_agent.guide_tools import GuideState


def fake_ask(adapter, text: str, selection=None, here=None, **_ignored) -> dict:
    if here is not None and here.ok:
        adapter.session = SimpleNamespace(guide=GuideState(), map=adapter.map)
        adapter.apply_here(here)
    return {"reply": "ok", "backend": "fake"}


web.server.chat_available = lambda: True
web.chat.chat_available = lambda: True
web.chat.ChatAdapter.ask = fake_ask

if __name__ == "__main__":
    web.server.main()
