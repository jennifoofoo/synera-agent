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
"""

import argparse
import json
import os
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from starter_agent.building_map import BuildingMap, MapError
from web import api
from web.chat import ChatAdapter, chat_available
from web.chat import backend_name as chat_backend_name

STATIC = Path(__file__).parent / "static"
DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
MAX_BODY_BYTES = 1_000_000


class App:
    """All loaded buildings. The page is a single-user demo, so state lives in memory per building key."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.sessions: dict[str, api.Session] = {}
        self.chats: dict[str, ChatAdapter] = {}
        self.lock = threading.RLock()

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
            return 200, {"chat_available": chat_available(), "chat_backend": chat_backend_name()}
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

        def do_POST(self) -> None:
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Body too large."})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Body is not JSON."})
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
