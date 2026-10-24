"""Chat adapter for the 2D page: which agent answers the chat box.

One-line switch: BACKEND below.
- "starter": starter_agent.BuildingAgent bound to the SAME BuildingMap the page draws. It keeps the
  conversation, and its closures, new doors and routes show up on the map right away.
- "building_agent": building_agent.agent.Session bound to the SAME BuildingMap the page draws: it keeps the
  conversation (next/again, confirm cards) and its changes show up on the map.
- "auto": building_agent if it imports and answers, otherwise starter.
"""

import os
import threading
from pathlib import Path

from starter_agent.building_map import BuildingMap

BACKEND = "auto"
OUTPUT_DIRECTORY = Path("agent_output") / "web"
NO_KEY_MESSAGE = (
    "Chat is off: ANTHROPIC_API_KEY is not set. Put it into .env (see .env.example) and restart the server. "
    "The map, routes and closures work without it."
)


def chat_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def backend_name() -> str:
    """The backend the chat will use right now ("auto" resolved)."""
    if BACKEND != "auto":
        return BACKEND
    try:
        from building_agent.agent import answer  # noqa: F401
    except ImportError:
        return "starter"
    return "building_agent"


class ChatAdapter:
    """One per loaded building. ask() returns {'reply', 'backend'} and never raises."""

    def __init__(self, building_dir: Path, building_map: BuildingMap, level4=None) -> None:
        self.building_dir = building_dir
        self.map = building_map
        self.level4 = level4  # web.level4_api.PlanStudio: the page's floor plan draft, shared with the agent
        self.starter = None
        self.session = None
        self.lock = threading.Lock()

    def ask(self, text: str) -> dict:
        if not chat_available():
            return {"reply": NO_KEY_MESSAGE, "backend": None, "error": "no_api_key"}
        backend = backend_name()
        try:
            with self.lock:  # one conversation per building: never two turns at once
                if backend == "building_agent":
                    return {"reply": self.ask_building_agent(text), "backend": backend}
                return {"reply": self.ask_starter(text), "backend": backend}
        except Exception as error:  # noqa: BLE001 - the page must keep working whatever the API does
            return {"reply": f"The agent failed: {type(error).__name__}: {error}", "backend": backend, "error": "agent"}

    def ask_building_agent(self, text: str) -> str:
        from building_agent.agent import Session

        if self.session is None:
            self.session = Session(self.map, OUTPUT_DIRECTORY / self.building_dir.name)
            if self.level4 is not None and not any(tool.name == "build_from_plan" for tool in self.session.tools):
                self.session.tools = [*self.session.tools, *self.level4.chat_tools]
        if self.level4 is not None:
            self.level4.begin_turn()
            note = self.level4.chat_context()
            if note:
                text = f"{note}\n{text}"
        return self.session.ask(text)

    def ask_starter(self, text: str) -> str:
        if self.starter is None:
            from starter_agent.agent import BuildingAgent

            OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
            self.starter = BuildingAgent(self.map, OUTPUT_DIRECTORY)
        return self.starter.ask(text)
