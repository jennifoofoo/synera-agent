"""Small stdlib HTTP server for the 2D page: static files from web/static plus a JSON API.

Start:  uv run python -m web            (then open http://127.0.0.1:8765)
        uv run python -m web --data data --port 8765 --env-file .env

API (all JSON; POST bodies carry "building": "<split>/<building_id>"):
  GET  /api/status                      chat availability and backend
  GET  /api/buildings                   every directory under --data with a building.json
  GET  /api/building?key=dev/...        floors, spaces, openings, connectors, assets, state
  POST /api/route    {start, destination, step_free, via: []}
  POST /api/route/clear
  POST /api/close    {element, closed: true|false}       lift/stairs/door/room id or name
  POST /api/door     {first, second, step_free}
  POST /api/reset                       reload the building from disk (drops closures, doors, route)
  POST /api/chat     {message, voice?: true, context?: {space_id, asset_id, point, floor_id}}   click selection, validated
                     context.here: {space_id, point?, floor_id?} or {clear: true}, "I'm here", validated, see docs/specs/position.md
  POST /api/speak    {text, lang?, voice_id?}                  audio/mpeg (ElevenLabs), see docs/specs/voice-spike.md

Level 4, new building from floor plans (web/level4_api.py; POSTs need a same-origin page):
  POST /api/level4/upload               raw PNG/JPG body (<= 10 MB) -> {upload_id, width, height}
  POST /api/level4/attach?upload_id=plan-...&kind=svg|building_json   raw svg (image/svg+xml) or building.json
                                        (application/json) body of an uploaded plan -> {upload_id, kind, bytes}
  POST /api/level4/build  {floors: [{upload_id, level, known_length_m | scale_bar, along}], name?}
  GET  /api/level4/status               background reading progress
  GET  /api/level4/preview              draft in the building_view shape + findings + red spots
  POST /api/level4/fix    {action: add_door|remove_door|set_room_type|set_scale, ref, other_ref, room_type, ...}
  POST /api/level4/card                 the understanding card; the very next action must be the answer
  POST /api/level4/save   {answer: "yes"|"no", accept_problems?}  -> {saved, key: "user/<id>"}
  POST /api/level4/reset                start a new draft
"""

import argparse
import json
import os
import re
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from building_agent.structured import located_entries
from building_agent.voice_rules import voice_kwargs
from starter_agent.building_map import MapError
from web import api, level4_api, speech
from web.chat import ChatAdapter, chat_available
from web.chat import backend_name as chat_backend_name
from web.selection import check_here, check_selection

STATIC = Path(__file__).parent / "static"
DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
MAX_BODY_BYTES = 1_000_000
VOICE_ID = re.compile(r"[A-Za-z0-9]{10,40}")
SPEAK_MIN_GAP_SECONDS = 1.0
SPEAK_MAX_PER_MINUTE = 30


def speech_available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID"))


class App:
    """All loaded buildings. The page is a single-user demo, so state lives in memory per building key."""

    def __init__(
        self,
        data_root: Path,
        uploads_root: Path = level4_api.DEFAULT_ALLOWED_ROOT,
        buildings_root: Path = level4_api.BUILDINGS_ROOT,
    ) -> None:
        self.data_root = data_root
        self.buildings_root = buildings_root
        self.level4 = level4_api.PlanStudio(uploads_root, buildings_root)
        self.sessions: dict[str, api.Session] = {}
        self.chats: dict[str, ChatAdapter] = {}
        self.lock = threading.RLock()
        self.synthesize = speech.synthesize  # replaced in tests
        self.clock = time.monotonic  # replaced in tests
        self.speak_times: deque[float] = deque()

    def allow_speak(self) -> bool:
        """At most 1 request per second and 30 per minute (each call to /api/speak can cost money)."""
        now = self.clock()
        with self.lock:
            while self.speak_times and now - self.speak_times[0] > 60:
                self.speak_times.popleft()
            if self.speak_times and now - self.speak_times[-1] < SPEAK_MIN_GAP_SECONDS:
                return False
            if len(self.speak_times) >= SPEAK_MAX_PER_MINUTE:
                return False
            self.speak_times.append(now)
            return True

    def speak(self, body: dict) -> tuple[int, bytes | dict]:
        """Shorten the text for speaking and return MP3 bytes, or (status, error payload)."""
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "") or str(body.get("voice_id") or "")
        if not (os.environ.get("ELEVENLABS_API_KEY") and voice_id):
            return 503, {"error": "Speech is not configured (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)."}
        if not VOICE_ID.fullmatch(voice_id):
            return 400, {"error": "Invalid voice id."}
        if not self.allow_speak():
            return 429, {"error": "Too many speech requests, wait a moment."}
        lang = "de" if str(body.get("lang", "en")).lower().startswith("de") else "en"
        text = speech.spoken_version(str(body.get("text", "")), lang=lang)
        if not text:
            return 400, {"error": "Nothing to say."}
        try:
            return 200, self.synthesize(text, voice_id)
        except speech.SpeechError as error:
            return 502, {"error": str(error), "fallback": "browser_voice_or_text"}

    def session(self, key: str) -> api.Session:
        with self.lock:
            if key not in self.sessions:
                if key.startswith(level4_api.USER_PREFIX):  # saved from floor plans on this page
                    directory = api.resolve_building_dir(self.buildings_root, key[len(level4_api.USER_PREFIX) :])
                else:
                    directory = api.resolve_building_dir(self.data_root, key)
                self.sessions[key] = api.Session(key, directory, api.RecordingMap.load(directory))
            return self.sessions[key]

    def reset(self, key: str) -> api.Session:
        with self.lock:
            self.sessions.pop(key, None)
            self.chats.pop(key, None)
            return self.session(key)

    def chat(self, key: str) -> ChatAdapter:
        with self.lock:
            session = self.session(key)
            if key not in self.chats:
                self.chats[key] = ChatAdapter(session.directory, session.map, self.level4)
            return self.chats[key]

    def open_saved(self, chat: ChatAdapter, saved_path: str) -> str | None:
        """The agent saved a building into our buildings folder: return its key (user/<id>) and move the chat there."""
        path = Path(saved_path)
        if path.parent.parent.resolve() != self.buildings_root.resolve():
            return None
        key = level4_api.USER_PREFIX + path.parent.name
        self.sessions.pop(key, None)  # saving again under the same id must not show an old copy
        self.chats.pop(key, None)
        try:
            session = self.session(key)
        except (MapError, OSError, ValueError, KeyError):
            return None
        self.chats[key] = chat.move_to(session.directory, session.map)
        return key

    # ---------- request handling (returns status, payload) ----------

    def get(self, path: str, query: dict) -> tuple[int, dict]:
        if path == "/api/status":
            return 200, {
                "chat_available": chat_available(),
                "chat_backend": chat_backend_name(),
                "speech_available": speech_available(),
            }
        if path == "/api/buildings":
            saved = level4_api.saved_buildings(self.buildings_root)
            return 200, {"buildings": api.list_buildings(self.data_root) + saved}
        if path == "/api/level4/status":
            return 200, self.level4.status()
        if path == "/api/level4/preview":
            return 200, self.level4.preview()
        if path == "/api/building":
            key = (query.get("key") or [""])[0]
            with self.lock:
                return 200, api.building_view(self.session(key))
        return 404, {"error": f"Unknown endpoint {path}"}

    def upload(self, data: bytes) -> tuple[int, dict]:
        return 200, self.level4.upload(data)

    def attach(self, query: dict, data: bytes) -> tuple[int, dict]:
        return 200, self.level4.attach((query.get("upload_id") or [""])[0], (query.get("kind") or [""])[0], data)

    def post_level4(self, path: str, body: dict) -> tuple[int, dict]:
        studio = self.level4
        if path == "/api/level4/build":
            return 200, studio.start_build(body)
        if path == "/api/level4/fix":
            return 200, studio.fix(body)
        if path == "/api/level4/card":
            return 200, studio.card()
        if path == "/api/level4/save":
            result = studio.save(body)
            if result.get("saved"):
                with self.lock:  # saving again under the same id must not show an old copy
                    self.sessions.pop(result["key"], None)
                    self.chats.pop(result["key"], None)
            return 200, result
        if path == "/api/level4/reset":
            studio.new_draft(forget_uploads=True)
            return 200, studio.status()
        return 404, {"error": f"Unknown endpoint {path}"}

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        if path.startswith("/api/level4/"):
            return self.post_level4(path, body)
        key = body.get("building", "")
        if path == "/api/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                return 400, {"error": "Empty message."}
            with self.lock:  # session and chat together, so a reset cannot pair a new map with an old chat
                session, chat = self.session(key), self.chat(key)
                previous_route, version = session.map.last_route, session.route_version
            session.map.located_asset_ids = []  # so `located` below only holds what this turn found
            # Not under the lock: an API call takes seconds and must not freeze the map.
            context = body.get("context")
            here_raw = None
            if isinstance(context, dict) and "here" in context:  # "I'm here" travels beside the click selection
                here_raw = context["here"]
                context = {key: value for key, value in context.items() if key != "here"} or None
            check = check_selection(context, session.map)
            here = check_here(here_raw, session.map)
            extra = {"here": here} if here.ok else {}
            extra.update(voice_kwargs(body))  # request-level spoken-reply flag, never read from the message text
            result = (
                chat.ask(message, selection=check.selection, **extra) if check.selection else chat.ask(message, **extra)
            )
            if context is not None and not check.selection:
                result = {**result, "selection_ignored": check.reason}
            if here_raw is not None and not here.ok:
                result = {**result, "here_ignored": here.reason}
            elif here.note:
                result = {**result, "here_note": here.note}
            session.position = chat.position_view()
            session.guide_info = chat.guide_info()
            saved_path = result.pop("saved_path", None)
            with self.lock:
                current = self.session(key)
                level4 = self.level4.chat_info()
                if current is not session:  # the building was reset while the agent was thinking
                    return 200, {**result, "stale": True, "state": api.state_view(current), "level4": level4}
                session.adopt_agent_route(previous_route, version)
                opened = self.open_saved(chat, saved_path) if saved_path else None
                if opened:  # the page switches to the new building and fetches it from /api/building
                    return 200, {
                        **result,
                        "opened": opened,
                        "located": [],
                        "state": api.state_view(session),
                        "level4": level4,
                    }
                located = [] if result.get("error") else located_entries(session.map, result.get("reply", ""))
                return 200, {**result, "located": located, "state": api.state_view(session), "level4": level4}
        with self.lock:
            session = self.session(key)
            if path == "/api/route":
                try:
                    return 200, {
                        "route": api.route_view(
                            session,
                            str(body.get("start", "")),
                            str(body.get("destination", "")),
                            bool(body.get("step_free", False)),
                            [str(stop) for stop in body.get("via") or []],
                        ),
                        "state": api.state_view(session),
                    }
                except MapError as error:
                    return 200, {"route": {"ok": False, "error": str(error)}, "state": api.state_view(session)}
            if path == "/api/route/clear":
                return 200, api.clear_route(session)
            if path == "/api/close":
                return 200, api.set_closed(session, str(body.get("element", "")), bool(body.get("closed", True)))
            if path == "/api/door":
                return 200, api.add_door(
                    session, str(body.get("first", "")), str(body.get("second", "")), bool(body.get("step_free", True))
                )
            if path == "/api/reset":
                return 200, api.building_view(self.reset(key))
        return 404, {"error": f"Unknown endpoint {path}"}


def make_handler(app: App) -> type:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(STATIC), **kwargs)

        def log_message(self, format: str, *args) -> None:  # keep the console quiet except for errors
            if args and str(args[1]).startswith(("4", "5")):
                super().log_message(format, *args)

        def send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def run_speak(self, body: dict) -> None:
            try:
                status, payload = app.speak(body)
            except Exception:  # noqa: BLE001 - report it, don't kill the server
                status, payload = 500, {"error": "Speech failed."}  # never the exception text
            if isinstance(payload, bytes):
                self.send_response(status)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_json(status, payload)

        def run(self, action) -> None:
            try:
                status, payload = action()
            except MapError as error:
                status, payload = 400, {"error": str(error)}
            except level4_api.Level4Error as error:
                status, payload = error.status, {"error": str(error)}
            except Exception as error:  # noqa: BLE001 - report it, don't kill the server
                status, payload = 500, {"error": f"{type(error).__name__}: {error}"}
            self.send_json(status, payload)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path.startswith("/api/"):
                self.run(lambda: app.get(url.path, parse_qs(url.query)))
            else:
                super().do_GET()

        def speak_request_allowed(self, content_types: tuple[str, ...] = ("application/json",)) -> bool:
            """Browser-origin guard for costly or writing endpoints: same-origin page only, expected body type."""
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            host = self.headers.get("Host")
            if (origin is not None and origin not in {f"http://{name}" for name in allowed}) or (
                host is not None and host not in allowed
            ):
                self.send_json(403, {"error": "Forbidden origin."})
                return False
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() not in content_types:
                self.send_json(415, {"error": f"Content-Type must be {' or '.join(content_types)}."})
                return False
            return True

        def run_upload(self) -> None:
            """Raw image body. Size is checked before reading; the name and path are made on the server."""
            if not self.speak_request_allowed(("image/png", "image/jpeg")):
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length <= 0:
                self.send_json(411, {"error": "The upload needs a Content-Length."})
                return
            if length > level4_api.MAX_FILE_BYTES:
                self.close_connection = True  # the body is not read
                self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "The image is larger than 10 MB."})
                return
            data = self.rfile.read(length)
            self.run(lambda: app.upload(data))

        def run_attach(self, query: dict) -> None:
            """Raw svg or building.json body for an uploaded plan (named by its id, never by a path)."""
            kind = (query.get("kind") or [""])[0]
            wanted = level4_api.ATTACHMENTS.get(kind)
            if wanted is None:
                self.send_json(400, {"error": f"kind must be one of {', '.join(level4_api.ATTACHMENTS)}."})
                return
            if not self.speak_request_allowed((wanted[1],)):
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length <= 0:
                self.send_json(411, {"error": "The upload needs a Content-Length."})
                return
            if length > wanted[2]:
                self.close_connection = True  # the body is not read
                self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "The file is too large."})
                return
            data = self.rfile.read(length)
            self.run(lambda: app.attach(query, data))

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path == "/api/level4/upload":
                self.run_upload()
                return
            if url.path == "/api/level4/attach":
                self.run_attach(parse_qs(url.query))
                return
            if url.path.startswith(("/api/speak", "/api/level4/")) and not self.speak_request_allowed():
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Body too large."})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Body is not JSON."})
                return
            if url.path == "/api/speak":
                self.run_speak(body if isinstance(body, dict) else {})
                return
            self.run(lambda: app.post(url.path, body))

        def end_headers(self) -> None:
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

    return Handler


def load_env_file(path: Path) -> None:
    """Minimal .env reader (KEY=value lines) so `python -m web` finds ANTHROPIC_API_KEY without extra tools."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and name.strip() not in os.environ:
            os.environ[name.strip()] = value


def main() -> None:
    parser = argparse.ArgumentParser(prog="web", description="2D floor plan + chat for any kit building.")
    parser.add_argument("--data", type=Path, default=Path("data"), help="folder searched for */building.json")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="read ANTHROPIC_API_KEY from here")
    parser.add_argument(
        "--fake-plans",
        type=Path,
        metavar="BUILDING_DIR",
        help="offline demo: read every uploaded plan as this building's floor (no vision call, no cost)",
    )
    arguments = parser.parse_args()
    load_env_file(arguments.env_file)
    app = App(arguments.data)
    if arguments.fake_plans:
        level4_api.use_fake_extraction(app.level4, arguments.fake_plans)
        print(f"Floor plans are faked from {arguments.fake_plans} (no vision call).")
    server = ThreadingHTTPServer((arguments.host, arguments.port), make_handler(app))
    chat_state = f"chat via {chat_backend_name()}" if chat_available() else "chat off (no ANTHROPIC_API_KEY)"
    print(
        f"2D page on http://{arguments.host}:{arguments.port}  ({len(api.list_buildings(arguments.data))} buildings, {chat_state})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
