"""Seed the demo story on a running page server: the night shift's note at a ground-floor fire extinguisher.

    uv run python scripts/demo_seed.py user/plan-89323a15 [--port 8798] [--photo bracket.jpg]

The round is planned by the server (POST /api/round, the same plan_round as the chat and the page) from the main
entrance room (the page's default start: the room behind the first entrance, by id) over every fire extinguisher on
the ground floor. The note goes on the extinguisher at the 2nd stop (the 1st if the round has only one stop) via
POST /api/facts. Running it again adds nothing when the same note is already there. The drawn round is cleared
afterwards, so the page starts clean. A building without fire extinguishers is not an error: it says so and exits 0.
"""

import argparse
import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

NOTE_TEXT = "Bracket is loose, always check it first."
NOTE_AUTHOR = "Night shift"
DEVICE = "fire extinguisher"
AREA = "Ground floor"


def call(base: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def is_extinguisher(asset: dict) -> bool:
    return asset["type"].lower().replace("-", "_").replace(" ", "_").rstrip("s") == "fire_extinguisher"


def main_entrance_room(building: dict) -> str | None:
    """Same rule as the page (twin/src/round/choices.ts entranceRoom): the room behind the first entrance, by id."""
    rooms = [o["space_ids"][0] for o in building["openings"] if o["kind"] == "entrance" and o["space_ids"]]
    return min(rooms) if rooms else None


def seed(base: str, key: str, kind: str = "issue", photo: Path | None = None) -> int:
    building = call(base, "/api/building?" + urllib.parse.urlencode({"key": key}))
    ground = {floor["id"] for floor in building["floors"] if floor["level"] == 0}
    extinguishers = [a for a in building["assets"] if is_extinguisher(a) and a["floor_id"] in ground]
    if not extinguishers:
        print(f"{building['name']} ({key}) has no fire extinguishers on the ground floor yet: nothing to seed.")
        return 0
    start = main_entrance_room(building)
    if start is None:
        print(f"{building['name']} ({key}) has no entrance, so the round has no start: nothing to seed.")
        return 0
    names = {space["id"]: space["name"] for space in building["spaces"]}
    reply = call(base, "/api/round", {"building": key, "type": DEVICE, "area": AREA, "start": start})
    call(base, "/api/route/clear", {"building": key})
    planned = reply["round"]
    if not planned.get("ok"):
        print(f"No round: {planned.get('error') or planned.get('question')}", file=sys.stderr)
        return 1

    print(f"Round: {planned['devices']} {DEVICE}s on the {AREA.lower()} of {building['name']}, from {names[start]}")
    for stop in planned["stops"]:
        print(f"  {stop['n']}. {stop['room']:<28} {stop['leg_m']:>6.1f} m   {', '.join(stop['devices'])}")
    print(f"  total {planned['total_m']:.1f} m, about {planned['about_minutes']} min")

    stop = planned["info"]["stops"][1 if len(planned["info"]["stops"]) > 1 else 0]
    asset_id = stop["asset_ids"][0]
    asset_name = next(a["name"] for a in extinguishers if a["id"] == asset_id)
    there = call(base, "/api/facts?" + urllib.parse.urlencode({"key": key, "asset_id": asset_id}))["facts"]
    if any(fact["text"] == NOTE_TEXT and fact.get("author") == NOTE_AUTHOR for fact in there):
        print(f"Note already at {asset_name} ({names[stop['space_id']]}): nothing added.")
        return 0
    body = {
        "building": key,
        "kind": kind,
        "anchor": {"asset_id": asset_id},
        "text": NOTE_TEXT,
        "author": NOTE_AUTHOR,
    }
    if photo is not None:
        body["photo_base64"] = base64.b64encode(photo.read_bytes()).decode()
    fact = call(base, "/api/facts", body)["fact"]
    print(f"Added {kind} {fact['id']} at {asset_name} ({names[stop['space_id']]}): {NOTE_TEXT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("building", help="building key, e.g. user/plan-89323a15")
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--kind", choices=("issue", "note"), default="issue")
    parser.add_argument("--photo", type=Path, help="optional JPEG/PNG for the note")
    arguments = parser.parse_args()
    return seed(f"http://{arguments.host}:{arguments.port}", arguments.building, arguments.kind, arguments.photo)


if __name__ == "__main__":
    sys.exit(main())
