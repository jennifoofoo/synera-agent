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

    def __init__(self, building_dir: Path, building_map: BuildingMap, level4=None, campus_source=None) -> None:
        self.building_dir = building_dir
        self.map = building_map
        self.level4 = level4  # web.level4_api.PlanStudio: the page's floor plan draft, shared with the agent
        self.campus_source = campus_source  # callable returning the page's CampusHolder (or None): one campus for both
        self.starter = None
        self.session = None
        self.saved_paths: list[Path] = []  # buildings the agent saved during the current turn (Level 4 save_building)
        self.lock = threading.Lock()

    def ask(self, text: str, selection=None, here=None, voice: bool = False) -> dict:
        """selection: a validated web.selection.Selection, valid for this one turn only.
        here: a validated web.selection.HereCheck ("I'm here" click or clear), applied before the turn.
        voice: request-level spoken-reply flag."""
        if not chat_available():
            return {"reply": NO_KEY_MESSAGE, "backend": None, "error": "no_api_key"}
        backend = backend_name()
        try:
            with self.lock:  # one conversation per building: never two turns at once
                self.saved_paths = []
                if backend == "building_agent":
                    result = {"reply": self.ask_building_agent(text, selection, here, voice), "backend": backend}
                else:
                    result = {"reply": self.ask_starter(text), "backend": backend}
                if self.saved_paths:
                    result["saved_path"] = str(self.saved_paths[-1])
                return result
        except Exception as error:  # noqa: BLE001 - the page must keep working whatever the API does
            return {"reply": f"The agent failed: {type(error).__name__}: {error}", "backend": backend, "error": "agent"}

    def ask_building_agent(self, text: str, selection=None, here=None, voice: bool = False) -> str:
        self.ensure_session()
        if self.level4 is not None:
            self.level4.begin_turn()
            note = self.level4.chat_context()
            if note:
                text = f"{note}\n{text}"
        if here is not None and here.ok:
            self.apply_here(here)
        self.session.guide.selection = selection
        try:
            return self.session.ask(text, **({"voice": True} if voice else {}))
        finally:
            self.session.guide.selection = None  # one-shot: never leaks into the next message

    def add_level4_tools(self) -> None:
        if self.level4 is not None and not any(tool.name == "build_from_plan" for tool in self.session.tools):
            self.session.tools = [*self.session.tools, *self.level4.chat_tools]

    def ensure_session(self):
        """The agent session, created on first use. It holds the SAME CampusHolder as the page; if the page loaded
        a campus later, the tools and rules are rebuilt (position and walk are kept)."""
        from building_agent.agent import Session

        campus = self.campus_source() if self.campus_source else None
        if self.session is None:
            self.session = Session(
                self.map, OUTPUT_DIRECTORY / self.building_dir.name, **({"campus": campus} if campus else {})
            )
            self.watch_saves(self.session)
            self.add_level4_tools()
        elif campus is not getattr(self.session, "campus", None):
            guide = self.session.guide
            position, walk = guide.position, guide.walk
            self.session.campus = campus
            self.session.install_building(self.map)
            guide.position, guide.walk = position, walk
            self.add_level4_tools()
        if campus is not None:
            campus.bm = self.map  # next_steps compares against the map the tools were built with
        return self.session

    def apply_here(self, here) -> None:
        """The page's validated click sets the position (source click); the next message is the next turn."""
        from building_agent import walk as walking
        from building_agent.position import make_position

        guide, bm = self.session.guide, self.session.map
        guide.session = None
        if here.clear:
            guide.position = guide.walk = None
            return
        guide.position = make_position(bm, here.space_id, here.point, "click", guide.turn + 1)
        walking.follow(bm, guide, here.space_id)  # with a walk: what is left is recomputed from this room
        guide.position = make_position(bm, here.space_id, here.point, "click", guide.turn + 1)

    def guide_info(self) -> dict | None:
        """The current leg while guiding (rooms only; the page side draws it), else None."""
        from building_agent import walk as walking

        walk = getattr(self.session.guide, "walk", None) if self.session is not None else None
        return walking.guide_info(walk)

    def position_view(self) -> dict | None:
        """What state_view shows: {space_id, floor_id, point, source} or None."""
        position = getattr(self.session.guide, "position", None) if self.session is not None else None
        return position.view() if position is not None else None

    def watch_saves(self, session) -> None:
        """Note every building the agent saves, so the page can open it (the agent's own tools call swap_building)."""
        original = session.swap_building

        def swap_and_note(path) -> None:
            original(path)
            self.saved_paths.append(Path(path))

        session.swap_building = swap_and_note
        session.install_building(session.map)  # the tools were built with the unwrapped method

    def move_to(self, building_dir: Path, building_map: BuildingMap) -> "ChatAdapter":
        """The conversation continues on another building (the one just saved); this adapter starts over."""
        moved = ChatAdapter(building_dir, building_map, self.level4, self.campus_source)
        moved.session, self.session = self.session, None
        if moved.session is not None:
            moved.session.install_building(building_map)
            moved.watch_saves(moved.session)
        return moved

    def ask_starter(self, text: str) -> str:
        if self.starter is None:
            from starter_agent.agent import BuildingAgent

            OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
            self.starter = BuildingAgent(self.map, OUTPUT_DIRECTORY)
        return self.starter.ask(text)
