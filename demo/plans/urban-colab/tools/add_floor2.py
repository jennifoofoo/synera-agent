"""Add Floor 2 of the Urban Colab to building.json, from the evacuation plan OG2.04 (photos/OG2-04_floor2.jpeg).

Reproducible: run once on a building.json without F2. Pixel positions are read from the photo as displayed upright
(1500 x 2000). The core (IT room to lift) spans the same 23.2 m as on Floor 4, which gives the scale and offset:
    x = 12.9 + (px - 708) * 0.0527,  y = 21.1 - (py - 693) * 0.0527
(facades then land on 27.8 / 4.8, the stairs on -5.9..10.1). Shared lines are snapped to the Floor 3/4 values.
The plan cuts the floor at the IT room on the west, like OG4.04.
Usage: python add_floor2.py demo/buildings/plan-89323a15/building.json
"""

import json
import sys
from pathlib import Path

from shapely.geometry import Point, box
from shapely.ops import unary_union

PATH = Path(sys.argv[1])
B = "plan-89323a15"
F = f"{B}-F2"
W, E, SOUTH, NORTH = -12.1, 39.1, 4.8, 27.6

rooms = {}


def add(key, name, typ, room_type, geom):
    rooms[key] = (name, typ, room_type, geom)


add("side", "Side Room", "room", "office", box(W, 23.4, -7.65, NORTH))
for i, (x0, x1) in enumerate([(-7.65, -3.2), (-3.2, 4.05), (4.05, 11.2), (11.2, 18.4)], 1):
    add(f"mr{i}", f"Meeting Room 2.0{i}", "room", "meeting_room", box(x0, 23.4, x1, NORTH))
add("it", "IT Room", "room", "server_room", box(W, 17.7, -7.3, 21.1))
add("elt", "Electrical Room", "room", "storage", box(-7.3, 17.7, -4.3, 21.1))
add("wc1", "Toilets", "room", "toilet", box(-4.3, 17.7, 2.6, 21.1))
add("wc2", "Toilets", "room", "toilet", box(4.05, 17.7, 9.9, 21.1))
add("lift", "Lift", "lift", "lift", box(9.9, 17.7, 12.9, 21.1))
add("stairs", "Main Stairs", "stair", "stairwell", box(-5.9, 11.35, 10.1, 14.6))
add("void_s", "Void", "room", "outdoor", box(-5.9, SOUTH, 10.1, 11.35))
corridor = unary_union(
    [
        box(W, 21.1, 12.9, 23.4),
        box(2.6, 17.7, 4.05, 21.1),
        box(W, 14.6, 12.9, 17.7),
        box(W, SOUTH, -5.9, 14.6),
        box(10.1, SOUTH, 14.5, 11.9),
        box(10.1, 11.9, 12.9, 14.6),
        box(14.5, 10.2, E, 11.9),
    ]
)
add("corr", "Second Floor Corridor", "corridor", "corridor", corridor)
add("lobby", "Lift Lobby", "corridor", "corridor", box(12.9, 11.9, 14.5, 23.4))
add("terr", "Terrace East", "outdoor", "balcony", box(24.9, 18.1, E, NORTH))
add("tt1", "Think Tank 2.01", "room", "office", box(21.3, 11.9, 23.4, 16.0))
open_area = unary_union([box(14.5, 11.9, E, 18.1), box(14.5, 18.1, 24.9, 23.4), box(18.4, 23.4, 24.9, NORTH)])
add("open", "Open Office", "room", "office", open_area.difference(rooms["tt1"][3]))
for i, (x0, x1) in enumerate([(14.5, 22.9), (22.9, 27.2), (27.2, 30.0), (30.0, 35.7), (35.7, E)], 1):
    add(f"off{i}", f"Office 2.0{i}", "room", "office", box(x0, SOUTH, x1, 10.2))

doors = [
    ("side", "corr", "door", (-10.0, 23.4), 1.0),
    ("mr1", "corr", "door", (-6.0, 23.4), 1.0),
    ("mr2", "corr", "door", (-1.5, 23.4), 1.0),
    ("mr3", "corr", "door", (5.6, 23.4), 1.0),
    ("mr4", "corr", "door", (12.3, 23.4), 1.0),
    ("it", "corr", "door", (-9.5, 17.7), 1.0),
    ("elt", "corr", "door", (-6.0, 21.1), 1.0),
    ("wc1", "corr", "door", (2.6, 18.5), 1.0),
    ("wc2", "corr", "door", (4.05, 18.5), 1.0),
    ("lift", "corr", "door", (11.4, 17.7), 1.2),
    ("stairs", "corr", "opening", (3.0, 14.6), 2.5),
    ("corr", "lobby", "opening", (12.9, 22.2), 2.0),
    ("corr", "lobby", "opening", (12.9, 16.2), 2.5),
    ("corr", "lobby", "opening", (13.7, 11.9), 1.6),
    ("lobby", "open", "opening", (14.5, 15.0), 3.0),
    ("lobby", "open", "opening", (14.5, 20.5), 3.0),
    ("open", "corr", "opening", (19.0, 11.9), 3.0),
    ("open", "corr", "opening", (32.0, 11.9), 3.0),
    ("terr", "open", "door", (24.9, 20.5), 1.0),
    ("tt1", "open", "door", (21.3, 14.3), 0.9),
    ("off1", "corr", "door", (16.0, 10.2), 1.0),
    ("off1", "corr", "door", (20.0, 10.2), 1.0),
    ("off2", "corr", "door", (24.4, 10.2), 1.0),
    ("off3", "corr", "door", (28.5, 10.2), 1.0),
    ("off4", "corr", "door", (32.0, 10.2), 1.0),
    ("off5", "corr", "door", (37.2, 10.2), 1.0),
]

devices = [
    ("fire_extinguisher", "corr", (-9.1, 22.6)),
    ("fire_extinguisher", "it", (-9.6, 20.3)),
    ("fire_extinguisher", "corr", (0.0, 21.25)),
    ("fire_extinguisher", "lobby", (14.4, 18.0)),
    ("fire_extinguisher", "corr", (33.6, 11.0)),
    ("manual_call_point", "lobby", (14.4, 15.1)),
]


def polygon(geom):
    geom = geom.buffer(0)
    assert geom.geom_type == "Polygon" and not geom.interiors, geom.geom_type
    return [[round(x, 3), round(y, 3)] for x, y in list(geom.exterior.coords)[:-1]]


b = json.loads(PATH.read_text())
assert all(f["id"] != F for f in b["floors"]), "F2 already there"
b["floors"].append({"id": F, "level": 2, "name": "Floor 2", "elevation_m": 6.0, "height_m": 3.0})
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
names = {"fire_extinguisher": "Fire extinguisher", "manual_call_point": "Fire alarm call point"}
size = {"fire_extinguisher": (0.3, 0.3), "manual_call_point": (0.15, 0.1)}
next_id = max(int(a["id"].split("-A")[1]) for a in b["assets"]) + 1
count = {}
for typ, key, (x, y) in devices:
    assert shape[key].buffer(0.05).contains(Point(x, y)), (typ, key)
    count[typ] = count.get(typ, 0) + 1
    b["assets"].append(
        {
            "id": f"{B}-A{next_id:05d}",
            "name": f"{names[typ]} 2.{count[typ]:02d}",
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
level = {f["id"]: f["level"] for f in b["floors"]}
for vc in b["vertical_connectors"]:
    pairs = list(zip(vc["floor_ids"], vc["space_ids"])) + [(F, ids["lift" if vc["kind"] == "lift" else "stairs"])]
    pairs.sort(key=lambda p: level[p[0]])
    vc["floor_ids"], vc["space_ids"] = [p[0] for p in pairs], [p[1] for p in pairs]
PATH.write_text(json.dumps(b, indent=1, ensure_ascii=False))
print("F2:", len(rooms), "spaces,", len(doors), "openings,", count)
