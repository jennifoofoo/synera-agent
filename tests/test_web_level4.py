"""Level 4 on the 2D page (web/level4_api.py and its routes in web/server.py). No API calls: the vision step is
replaced by an artificial extraction of a real dev floor at a known scale, minus the door of one room."""

import io
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image

from building_agent.level4 import tools as level4_tools
from web import level4_api
from web.level4_api import Level4Error, PlanStudio
from web.server import App, make_handler

DATA = Path("data")
SOURCE = DATA / "dev" / "proc-campus-dev-000"


def png_bytes(size: tuple[int, int] = (400, 300)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def jpg_bytes(size: tuple[int, int] = (400, 300)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def app(tmp_path, monkeypatch) -> App:
    monkeypatch.setattr(level4_tools, "extract_floor", level4_tools.extract_floor)  # restored after the test
    app = App(DATA, tmp_path / "uploads", tmp_path / "buildings")
    level4_api.use_fake_extraction(app.level4, SOURCE, delay_seconds=0.0)
    return app


def build(app: App, levels=(0,), run_async: bool = False) -> dict:
    floors = []
    for level in levels:
        upload = app.level4.upload(png_bytes())
        floors.append({"upload_id": upload["upload_id"], "level": level, "scale_bar": True})
    return app.level4.start_build({"floors": floors, "name": "Test plan"}, run_async=run_async)


def wait_done(studio: PlanStudio, timeout: float = 30.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        status = studio.status()
        if status["state"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("build did not finish")


def missing_doors(app: App) -> list[tuple[str, str]]:
    """Each red room (its door was dropped by the fake) with the room behind its original door."""
    preview = app.level4.preview()
    draft = preview["draft"]
    source = json.loads((SOURCE / "building.json").read_text(encoding="utf-8"))
    level_of = {floor["id"]: floor["level"] for floor in source["floors"] + draft["floors"]}
    label = lambda space: space.get("ref") or space["name"]
    pairs = []
    for lonely in preview["suspect_spaces"]:
        space = next(s for s in draft["spaces"] if s["id"] == lonely)
        level = level_of[space["floor_id"]]
        original = next(s for s in source["spaces"] if label(s) == label(space) and level_of[s["floor_id"]] == level)
        door = next(o for o in source["openings"] if original["id"] in o["space_ids"])
        other = next(s for s in source["spaces"] if s["id"] in door["space_ids"] and s["id"] != original["id"])
        target = next(
            s["id"] for s in draft["spaces"] if s["floor_id"] == space["floor_id"] and label(s) == label(other)
        )
        pairs.append((lonely, target))
    return pairs


def unreachable_and_neighbour(app: App) -> tuple[str, str]:
    return missing_doors(app)[0]


def add_missing_doors(app: App) -> None:
    for lonely, neighbour in missing_doors(app):
        app.level4.fix({"action": "add_door", "ref": lonely, "other_ref": neighbour})


# ---------- upload limits ----------


def test_upload_stores_png_and_jpg_under_a_server_name(app, tmp_path):
    for data, suffix in ((png_bytes(), ".png"), (jpg_bytes(), ".jpg")):
        result = app.level4.upload(data)
        assert result["width"] == 400 and result["height"] == 300
        stored = tmp_path / "uploads" / f"{result['upload_id']}{suffix}"
        assert stored.read_bytes() == data
    assert sorted(p.parent for p in (tmp_path / "uploads").iterdir()) == [tmp_path / "uploads"] * 2


@pytest.mark.parametrize(
    ("data", "status"),
    [
        (b"", 400),
        (b"GIF89a" + b"\x00" * 600, 415),  # wrong type
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", 415),
        (b"%PDF-1.7 " + b"x" * 500, 415),
        (b"\x89PNG\r\n\x1a\n" + b"not really a png" * 40, 415),  # right magic, broken body
        (png_bytes((150, 150)), 400),  # too small to read
    ],
)
def test_upload_refuses_bad_files(app, tmp_path, data, status):
    with pytest.raises(Level4Error) as error:
        app.level4.upload(data)
    assert error.value.status == status
    assert not (tmp_path / "uploads").exists() or not any((tmp_path / "uploads").iterdir())


def test_upload_refuses_more_than_10_mb(app):
    big = png_bytes()[:100] + b"\x00" * (level4_api.MAX_FILE_BYTES + 1)
    with pytest.raises(Level4Error) as error:
        app.level4.upload(big)
    assert error.value.status == 413


@pytest.mark.parametrize(
    "upload_id", ["../../etc/passwd", "/etc/passwd", "plan-000000000000", "data/dev/x/floor_0.png", None, 7]
)
def test_build_only_accepts_known_upload_ids_never_paths(app, upload_id):
    with pytest.raises(Level4Error, match="Unknown upload"):
        app.level4.start_build({"floors": [{"upload_id": upload_id, "level": 0, "scale_bar": True}]}, False)


@pytest.mark.parametrize(
    ("floor", "message"),
    [
        ({"level": 0}, "length you know"),
        ({"level": 0, "known_length_m": -3}, "more than 0"),
        ({"level": 0, "known_length_m": "nan"}, "number"),
        ({"level": 1.5, "scale_bar": True}, "whole number"),
        ({"level": 0, "known_length_m": 40, "along": "diagonal"}, "along"),
    ],
)
def test_build_asks_for_level_and_scale(app, floor, message):
    upload = app.level4.upload(png_bytes())
    with pytest.raises(Level4Error, match=message):
        app.level4.start_build({"floors": [{"upload_id": upload["upload_id"], **floor}]}, run_async=False)


# ---------- status, preview, fix ----------


def test_background_build_reports_progress_then_a_preview(app):
    started = build(app, levels=(0, 1), run_async=True)
    assert started["state"] in ("running", "done") and started["floors_total"] == 2
    status = wait_done(app.level4)
    assert status["state"] == "done" and not status["errors"]
    assert [result["level"] for result in status["results"]] == [0, 1]

    preview = app.level4.preview()
    view = preview["draft"]
    assert {"floors", "spaces", "openings", "connectors", "assets", "state"} <= set(view)
    assert [floor["level"] for floor in view["floors"]] == [0, 1]
    assert view["connectors"], "stairs or lifts found on both floors are linked"
    space = view["spaces"][0]
    assert {"id", "floor_id", "polygon", "anchor", "area_m2", "name", "room_type"} <= set(space)
    assert preview["summary"].startswith(f"{len(view['spaces'])} rooms")
    codes = {finding["code"] for finding in preview["findings"]}
    assert "room_unreachable" in codes and not preview["can_save"]
    assert preview["suspect_spaces"] and set(preview["suspect_spaces"]) <= {s["id"] for s in view["spaces"]}
    assert "printed bar" in preview["scales"][0]["note"]


def test_missing_scale_bar_is_asked_for_in_plain_words(app, monkeypatch):
    real = level4_tools.extract_floor

    def no_bar(*args, **kwargs):
        result = real(*args, **kwargs)
        result.extraction.scale_bar_px = result.extraction.scale_bar_m = None
        return result

    monkeypatch.setattr(level4_tools, "extract_floor", no_bar)
    status = build(app)
    assert status["state"] == "error"
    assert "length you know" in status["errors"][0]["error"]


def test_fix_adds_the_missing_door_and_clears_the_red(app):
    build(app)
    lonely, neighbour = unreachable_and_neighbour(app)
    result = app.level4.fix({"action": "add_door", "ref": lonely, "other_ref": neighbour})
    assert result["done"].startswith("Door added")
    assert lonely not in result["suspect_spaces"]
    assert result["can_save"], result["problems"]


def test_fix_room_type_and_scale(app):
    build(app)
    space = app.level4.preview()["draft"]["spaces"][0]
    typed = app.level4.fix({"action": "set_room_type", "ref": space["id"], "room_type": "Meeting room"})
    assert next(s for s in typed["draft"]["spaces"] if s["id"] == space["id"])["room_type"] == "meeting_room"
    before = sum(s["area_m2"] for s in typed["draft"]["spaces"])
    xs = [x for s in typed["draft"]["spaces"] for x, _ in s["polygon"]]
    width = max(xs) - min(xs)
    doubled = app.level4.fix({"action": "set_scale", "known_length_m": 2 * width, "level": 0})
    after = sum(s["area_m2"] for s in doubled["draft"]["spaces"])
    assert after == pytest.approx(4 * before, rel=0.02)
    with pytest.raises(Level4Error):
        app.level4.fix({"action": "add_door", "ref": space["id"], "other_ref": "no such room"})
    with pytest.raises(Level4Error):
        app.level4.fix({"action": "delete_everything"})


# ---------- confirm and save ----------


def test_save_is_refused_without_a_card_and_a_yes(app, tmp_path):
    build(app)
    lonely, neighbour = unreachable_and_neighbour(app)
    app.level4.fix({"action": "add_door", "ref": lonely, "other_ref": neighbour})
    with pytest.raises(Level4Error, match="No card"):
        app.level4.save({"answer": "yes"})
    app.level4.card()
    assert app.level4.save({"answer": "no"})["saved"] is False
    with pytest.raises(Level4Error, match="No card"):
        app.level4.save({"answer": "yes"})  # the card was used up by the no
    app.level4.card()
    app.level4.fix({"action": "set_room_type", "ref": lonely, "room_type": "office"})
    with pytest.raises(Level4Error):
        app.level4.save({"answer": "yes"})  # the draft changed after the card
    assert not (tmp_path / "buildings").exists()


def test_blocking_problems_need_an_explicit_save_anyway(app):
    build(app)
    card = app.level4.card()["card"]
    assert card["can be saved"] is False
    with pytest.raises(Level4Error, match="block saving"):
        app.level4.save({"answer": "yes"})
    app.level4.card()
    assert app.level4.save({"answer": "yes", "accept_problems": True})["saved"] is True


def test_saved_building_is_listed_loaded_and_routes(app, tmp_path):
    build(app, levels=(0, 1))
    lonely, _ = unreachable_and_neighbour(app)
    add_missing_doors(app)
    app.level4.card()
    saved = app.post("/api/level4/save", {"answer": "yes"})[1]
    assert saved["saved"] is True and saved["key"].startswith("user/plan-")
    assert (tmp_path / "buildings" / saved["key"].split("/")[1] / "building.json").exists()

    keys = {b["key"]: b for b in app.get("/api/buildings", {})[1]["buildings"]}
    assert keys[saved["key"]]["name"] == "Test plan" and keys[saved["key"]]["floors"] == 2
    view = app.get("/api/building", {"key": [saved["key"]]})[1]
    rooms = [s["id"] for s in view["spaces"] if s["floor_id"].endswith("F0")]
    upstairs = [s["id"] for s in view["spaces"] if s["floor_id"].endswith("F1") and s["type"] == "room"]
    route = app.post("/api/route", {"building": saved["key"], "start": lonely, "destination": upstairs[0]})[1]
    assert route["route"]["ok"] and route["route"]["length_m"] > 0
    assert len(route["route"]["floors"]) == 2 and lonely in rooms

    with pytest.raises(ValueError):
        app.get("/api/building", {"key": ["user/../../etc"]})


def test_reset_starts_a_new_draft(app):
    build(app)
    old_id = app.level4.draft.building_id
    app.post("/api/level4/reset", {})
    assert app.level4.preview()["draft"] is None and app.level4.uploads == {}
    assert app.level4.draft.building_id != old_id


# ---------- HTTP ----------


@pytest.fixture
def server(app):
    httpd = __import__("http.server").server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def http(url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST" if data is not None else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def test_http_upload_checks_origin_type_and_ignores_names(server, tmp_path):
    good = {"Content-Type": "image/png", "Content-Disposition": 'attachment; filename="../../evil.png"'}
    status, payload = http(f"{server}/api/level4/upload?path=../../x.png", png_bytes(), good)
    assert status == 200 and level4_api.UPLOAD_ID.match(payload["upload_id"])
    assert [p.name for p in (tmp_path / "uploads").iterdir()] == [payload["upload_id"] + ".png"]

    assert http(f"{server}/api/level4/upload", png_bytes(), {"Content-Type": "text/plain"})[0] == 415
    foreign = {"Content-Type": "image/png", "Origin": "http://evil.example"}
    assert http(f"{server}/api/level4/upload", png_bytes(), foreign)[0] == 403
    assert http(f"{server}/api/level4/upload", b"GIF89a" + b"0" * 400, {"Content-Type": "image/png"})[0] == 415
    json_post = {"Content-Type": "application/json", "Origin": "http://evil.example"}
    assert http(f"{server}/api/level4/save", b'{"answer": "yes"}', json_post)[0] == 403


def test_http_full_flow(server):
    upload = http(f"{server}/api/level4/upload", png_bytes(), {"Content-Type": "image/png"})[1]
    body = {"floors": [{"upload_id": upload["upload_id"], "level": 0, "known_length_m": 60}]}
    headers = {"Content-Type": "application/json"}
    status, started = http(f"{server}/api/level4/build", json.dumps(body).encode(), headers)
    assert status == 200 and started["floors_total"] == 1
    for _ in range(200):
        status_now = http(f"{server}/api/level4/status")[1]
        if status_now["state"] != "running":
            break
        time.sleep(0.05)
    assert status_now["state"] == "done"
    preview = http(f"{server}/api/level4/preview")[1]
    assert preview["draft"]["spaces"] and "60 m taken as the building width" in preview["scales"][0]["note"]
    status, error = http(f"{server}/api/level4/save", b'{"answer": "yes"}', headers)
    assert status == 400 and "card" in error["error"]


# ---------- vector file and building.json next to an upload ----------

PLAN_SVG = Path("data/dev/resplan-439/floor_0.svg")


def test_attach_svg_and_building_json_are_stored_next_to_the_image(app, tmp_path):
    if not PLAN_SVG.exists():
        pytest.skip("kit data missing")
    upload = app.level4.upload(png_bytes())["upload_id"]
    done = app.level4.attach(upload, "svg", PLAN_SVG.read_bytes())
    assert done["rooms"] > 0 and done["kind"] == "svg"
    app.level4.attach(upload, "building_json", b'{"px_per_m": 20}')
    assert sorted(p.name for p in (tmp_path / "uploads").iterdir()) == sorted(
        [f"{upload}.png", f"{upload}.svg", f"{upload}.building.json"]
    )


@pytest.mark.parametrize(
    ("kind", "data", "status"),
    [
        ("svg", b"<svg>nothing</svg>", 415),
        ("svg", b"", 400),
        ("building_json", b"{broken", 415),
        ("building_json", b"[1, 2", 415),
        ("exe", b"MZ", 400),
        (None, b"x", 400),
    ],
)
def test_attach_refuses_bad_files_and_kinds(app, tmp_path, kind, data, status):
    upload = app.level4.upload(png_bytes())["upload_id"]
    with pytest.raises(Level4Error) as error:
        app.level4.attach(upload, kind, data)
    assert error.value.status == status
    assert [p.name for p in (tmp_path / "uploads").iterdir()] == [f"{upload}.png"]  # nothing left behind


@pytest.mark.parametrize("upload_id", ["plan-000000000000", "../../x", "", None])
def test_attach_only_knows_upload_ids_never_paths(app, upload_id):
    with pytest.raises(Level4Error, match="Unknown upload"):
        app.level4.attach(upload_id, "building_json", b"{}")


def test_building_json_makes_the_scale_optional_on_the_page(app):
    upload = app.level4.upload(png_bytes())["upload_id"]
    floor = {"upload_id": upload, "level": 0}
    with pytest.raises(Level4Error, match="length you know"):
        app.level4.start_build({"floors": [floor]}, run_async=False)
    app.level4.attach(upload, "building_json", b'{"px_per_m": 20}')
    assert app.level4.start_build({"floors": [floor]}, run_async=False)["floors_total"] == 1


def test_http_attach_checks_origin_type_and_kind(server):
    upload = http(f"{server}/api/level4/upload", png_bytes(), {"Content-Type": "image/png"})[1]["upload_id"]
    url = f"{server}/api/level4/attach?upload_id={upload}&kind=building_json"
    good = {"Content-Type": "application/json"}
    status, payload = http(url, b'{"mpp": 0.05}', good)
    assert status == 200 and payload["kind"] == "building_json"
    assert http(url, b'{"mpp": 0.05}', {"Content-Type": "text/plain"})[0] == 415
    assert http(url, b'{"mpp": 0.05}', {**good, "Origin": "http://evil.example"})[0] == 403
    assert http(f"{server}/api/level4/attach?upload_id={upload}&kind=exe", b"x", good)[0] == 400
    assert http(f"{server}/api/level4/attach?upload_id=../../x&kind=building_json", b"{}", good)[0] == 400
