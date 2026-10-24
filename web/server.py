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
  POST /api/chat     {message}
  POST /api/speak    {text, voice_id?}                   audio/mpeg (ElevenLabs), see docs/specs/voice-spike.md
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

from starter_agent.building_map import BuildingMap, MapError
from web import api, speech
from web.chat import ChatAdapter, chat_available
from web.chat import backend_name as chat_backend_name

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

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
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
        text = speech.spoken_version(str(body.get("text", "")))
        if not text:
            return 400, {"error": "Nothing to say."}
        try:
            return 200, self.synthesize(text, voice_id)
        except speech.SpeechError as error:
            return 502, {"error": str(error), "fallback": "browser_voice_or_text"}

    def session(self, key: str) -> api.Session:
        with self.lock:
            if key not in self.sessions:
                directory = api.resolve_building_dir(self.data_root, key)
                self.sessions[key] = api.Session(key, directory, BuildingMap.load(directory))
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
                self.chats[key] = ChatAdapter(session.directory, session.map)
            return self.chats[key]

    # ---------- request handling (returns status, payload) ----------

    def get(self, path: str, query: dict) -> tuple[int, dict]:
        if path == "/api/status":
            return 200, {
                "chat_available": chat_available(),
                "chat_backend": chat_backend_name(),
                "speech_available": speech_available(),
            }
        if path == "/api/buildings":
            return 200, {"buildings": api.list_buildings(self.data_root)}
        if path == "/api/building":
            key = (query.get("key") or [""])[0]
            with self.lock:
                return 200, api.building_view(self.session(key))
        return 404, {"error": f"Unknown endpoint {path}"}

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        key = body.get("building", "")
        if path == "/api/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                return 400, {"error": "Empty message."}
            session = self.session(key)
            previous_route = session.map.last_route
            # Not under the lock: an API call takes seconds and must not freeze the map.
            result = self.chat(key).ask(message)
            with self.lock:
                session.adopt_agent_route(previous_route)
                return 200, {**result, "state": api.state_view(session)}
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
            except Exception as error:  # noqa: BLE001 - report it, don't kill the server
                status, payload = 500, {"error": f"{type(error).__name__}: {error}"}
            self.send_json(status, payload)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path.startswith("/api/"):
                self.run(lambda: app.get(url.path, parse_qs(url.query)))
            else:
                super().do_GET()

        def speak_request_allowed(self) -> bool:
            """Browser-origin guard for the costly endpoint: same-origin page only, JSON only."""
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            host = self.headers.get("Host")
            if (origin is not None and origin not in {f"http://{name}" for name in allowed}) or (
                host is not None and host not in allowed
            ):
                self.send_json(403, {"error": "Forbidden origin."})
                return False
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                self.send_json(415, {"error": "Content-Type must be application/json."})
                return False
            return True

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path == "/api/speak" and not self.speak_request_allowed():
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
    arguments = parser.parse_args()
    load_env_file(arguments.env_file)
    app = App(arguments.data)
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
