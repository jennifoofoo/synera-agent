"""Add Floor 4 of the Urban Colab to building.json, from the evacuation plan OG4.04.

Reproducible: run on a building.json that has Floor 3 but no F4 yet. The photo is taken at a slight angle, so the
rooms are given in building metres: x from the photo with the lift as anchor (x = 11.4 + (px - 540) * 0.0435, the
stairs then land on -6.0..8.6 as on Floor 3), y from the lines Floor 3 shares (facades 4.8/27.6, core 17.7..21.1,
corridor 14.9..23.4, stairs 11.5..14.9). The core (IT, electrical, toilets, lift) and stairs sit where they sit on F3.
The plan shows no west wing; the floor ends at the photo's west edge (x -12.1).
Usage: python add_floor4.py demo/buildings/plan-89323a15/building.json
"""

import json
import sys
from pathlib import Path

from shapely.geometry import Point, box
from shapely.ops import unary_union

PATH = Path(sys.argv[1])
B = "plan-89323a15"
F = f"{B}-F4"
W, E, SOUTH, NORTH = -12.1, 34.7, 4.8, 27.6

rooms = {}


def add(key, name, typ, room_type, geom):
    rooms[key] = (name, typ, room_type, geom)


add("kitchen", "Kitchen", "room", "kitchen", box(W, 23.4, -7.1, NORTH))
add("lib", "Activity Room / Library", "room", "library", box(-7.1, 23.4, -0.1, NORTH))
for i, (x0, x1) in enumerate([(-0.1, 4.1), (4.1, 8.1), (8.1, 12.1), (12.1, 16.4)], 1):
    add(f"mr{i}", f"Meeting Room 4.0{i}", "room", "meeting_room", box(x0, 23.4, x1, NORTH))
add("it", "IT Room", "room", "server_room", box(W, 17.7, -7.4, 21.1))
add("elt", "Electrical Room", "room", "storage", box(-7.4, 17.7, -4.7, 21.1))
add("shaft", "Service Shaft", "room", "storage", box(-4.7, 17.7, -2.4, 21.1))
add("wc1", "Toilets", "room", "toilet", box(-2.4, 17.7, 2.3, 21.1))
add("wc2", "Toilets", "room", "toilet", box(3.7, 17.7, 9.9, 21.1))
add("lift", "Lift", "lift", "lift", box(9.9, 17.7, 12.9, 21.1))
add("stairs", "Main Stairs", "stair", "stairwell", box(-6.0, 11.5, 8.6, 14.9))
add("void_s", "Void", "room", "outdoor", box(-6.0, SOUTH, 8.6, 11.5))
add("void_sw", "Void", "room", "outdoor", box(W, SOUTH, -6.0, 10.6))
add("void_se", "Void", "room", "outdoor", box(8.6, SOUTH, 12.5, 10.2))
corridor = unary_union(
    [
        box(W, 21.1, 12.9, 23.4),
        box(2.3, 17.7, 3.7, 21.1),
        box(W, 14.9, 12.9, 17.7),
        box(W, 10.6, -6.0, 14.9),
        box(8.6, 10.2, 12.5, 14.9),
    ]
)
add("corr", "Fourth Floor Corridor", "corridor", "corridor", corridor)
add("lobby", "Lift Lobby", "corridor", "corridor", box(12.9, 14.9, 16.4, 23.4))
add("terr", "Terrace", "outdoor", "balcony", box(16.4, 11.9, 22.5, NORTH))
add("void_e", "Void", "room", "outdoor", box(22.5, 11.9, E, NORTH))
add("tt1", "Think Tank 4.01", "room", "office", box(21.8, SOUTH, 23.8, 10.4))
open_office = unary_union([box(12.5, SOUTH, E, 11.9), box(12.5, 11.9, 16.4, 14.9)]).difference(rooms["tt1"][3])
add("open", "Open Office", "room", "office", open_office)

doors = [
    ("kitchen", "corr", "door", (-8.5, 23.4), 1.0),
    ("lib", "corr", "door", (-2.7, 23.4), 1.0),
    ("mr1", "corr", "door", (1.8, 23.4), 1.0),
    ("mr2", "corr", "door", (6.0, 23.4), 1.0),
    ("mr3", "corr", "door", (10.0, 23.4), 1.0),
    ("mr4", "lobby", "door", (15.5, 23.4), 1.0),
    ("it", "corr", "door", (-10.0, 17.7), 1.0),
    ("elt", "corr", "door", (-5.8, 21.1), 1.0),
    ("shaft", "corr", "door", (-3.5, 21.1), 0.8),
    ("wc1", "corr", "door", (2.3, 19.0), 1.0),
    ("wc2", "corr", "door", (3.7, 18.5), 1.0),
    ("lift", "corr", "door", (11.4, 17.7), 1.2),
    ("stairs", "corr", "opening", (1.3, 14.9), 2.5),
    ("corr", "lobby", "opening", (12.9, 22.2), 2.0),
    ("corr", "lobby", "opening", (12.9, 16.3), 2.5),
    ("lobby", "open", "opening", (14.6, 14.9), 3.0),
    ("terr", "open", "door", (16.4, 13.0), 1.0),
    ("tt1", "open", "door", (22.8, 10.4), 0.9),
]

devices = [
    ("fire_extinguisher", "it", (-9.8, 20.6)),
    ("fire_extinguisher", "corr", (1.0, 21.3)),
    ("fire_extinguisher", "lobby", (14.8, 15.6)),
    ("fire_extinguisher", "corr", (-11.9, 16.0)),
    ("fire_extinguisher", "open", (28.5, 5.0)),
    ("manual_call_point", "corr", (-4.9, 23.2)),
    ("manual_call_point", "open", (14.8, 14.6)),
    ("manual_call_point", "corr", (-11.9, 14.4)),
    ("first_aid_kit", "kitchen", (-10.6, 26.0)),
]


def polygon(geom):
    geom = geom.buffer(0)
    assert geom.geom_type == "Polygon" and not geom.interiors, geom.geom_type
    return [[round(x, 3), round(y, 3)] for x, y in list(geom.exterior.coords)[:-1]]


b = json.loads(PATH.read_text())
assert all(f["id"] != F for f in b["floors"]), "F4 already there"
b["floors"].append({"id": F, "level": 4, "name": "Floor 4", "elevation_m": 12.0, "height_m": 3.0})
b["floors"].sort(key=lambda f: f["level"])
ids = {}
for n, (key, (name, typ, room_type, geom)) in enumerate(rooms.items(), 1):
    ids[key] = f"{F}-S{n:03d}"
    b["spaces"].append(
        {
            "id": ids[key],
            "floor_id": F,
            "type": typ,
            "name": name,
            "polygon": polygon(geom),
            "room_type": room_type,
            "ref": None,
            "synthetic": False,
        }
    )
shape = {k: g for k, (_, _, _, g) in rooms.items()}
for n, (a, c, kind, (x, y), w) in enumerate(doors, 1):
    wall = shape[a].boundary.intersection(shape[c].buffer(0.05))
    assert not wall.is_empty and wall.distance(Point(x, y)) < 0.3, (a, c)
    b["openings"].append(
        {
            "id": f"{F}-O{n:04d}",
            "floor_id": F,
            "space_ids": [ids[a], ids[c]],
            "kind": kind,
            "position": [x, y],
            "width_m": w,
            "step_free": True,
            "synthetic": False,
        }
    )
names = {
    "fire_extinguisher": "Fire extinguisher",
    "manual_call_point": "Fire alarm call point",
    "first_aid_kit": "First aid kit",
}
size = {"fire_extinguisher": (0.3, 0.3), "manual_call_point": (0.15, 0.1), "first_aid_kit": (0.4, 0.2)}
next_id = max(int(a["id"].split("-A")[1]) for a in b["assets"]) + 1
count = {}
for typ, key, (x, y) in devices:
    assert shape[key].buffer(0.05).contains(Point(x, y)), (typ, key)
    count[typ] = count.get(typ, 0) + 1
    b["assets"].append(
        {
            "id": f"{B}-A{next_id:05d}",
            "name": f"{names[typ]} 4.{count[typ]:02d}",
            "category": "equipment",
            "type": typ,
            "space_id": ids[key],
            "floor_id": F,
            "position": [x, y],
            "footprint": {"width_m": size[typ][0], "depth_m": size[typ][1], "rotation_deg": 0.0},
            "source": "evacuation_plan",
        }
    )
    next_id += 1
for vc in b["vertical_connectors"]:
    vc["floor_ids"].append(F)
    vc["space_ids"].append(ids["lift" if vc["kind"] == "lift" else "stairs"])
PATH.write_text(json.dumps(b, indent=1, ensure_ascii=False))
print("F4:", len(rooms), "spaces,", len(doors), "openings,", count)
