"""Add the Urban Colab basement (car park and core) to building.json, from the evacuation plan U.02.

Reproducible: run once on a building.json without B1. U.02 hangs turned by 90 degrees against the other plans (its
compass points up-right, E.05's down-right), so the photo's left edge is north and its top edge is east:
    x = 11.24 - (py - 318) * 0.048,  y = 19.25 - (px - 522) * 0.048      (px, py = pixel in crops/U02_basement.jpg)
Anchor is the lift (same shaft on every floor, centre F0 11.24/19.25; the box gives 2.6 x 3.0 m at this scale).
The green stair beside the lift overlaps the main stairs above in plan and is the escape route, so it joins V02.
Only the visible part of the car park is drawn (the photo cuts it on three sides).
Usage: python add_basement.py demo/buildings/plan-89323a15/building.json
"""

import json
import sys
from pathlib import Path

from shapely.geometry import Point, box
from shapely.ops import unary_union

PATH = Path(sys.argv[1])
B = "plan-89323a15"
F = f"{B}-B1"


def tx(px, py):
    return [round(11.24 - (py - 318) * 0.048, 3), round(19.25 - (px - 522) * 0.048, 3)]


def pbox(px0, py0, px1, py1):
    return box(px0, py0, px1, py1)


rooms = {}


def add(key, name, typ, room_type, geom):
    rooms[key] = (name, typ, room_type, geom)


R = 885  # car park wall on the right of the photo (south)
add("lift", "Lift", "lift", "lift", pbox(476, 288, 562, 350))
add("stairs", "Main Stairs", "stair", "stairwell", pbox(628, 288, 718, 490))
add("st1", "Storage B.01", "room", "storage", pbox(476, 350, 562, 595))
add("st2", "Storage B.02", "room", "storage", pbox(476, 595, 562, 800))
add("srv1", "Server Room 1", "room", "server_room", pbox(718, 240, R, 360))
add("srv2", "Server Room 2", "room", "server_room", pbox(718, 360, R, 490))
add("bma", "Fire Alarm Panel", "room", "storage", pbox(628, 490, 718, 545))
add("bos", "Emergency Radio", "room", "storage", pbox(628, 545, 718, 598))
add("st3", "Storage B.03", "room", "storage", unary_union([pbox(718, 490, R, 598), pbox(800, 598, R, 645)]))
add("st4", "Storage B.04", "room", "storage", pbox(628, 645, 758, 768))
add("nshv", "Main Switchboard", "room", "storage", pbox(758, 645, R, 768))
corridor = unary_union([pbox(476, 240, 718, 288), pbox(562, 288, 628, 768), pbox(562, 598, 800, 645)])
add("corr", "Basement Corridor", "corridor", "corridor", corridor)
core = unary_union([g for _, _, _, g in rooms.values()])
add("park", "Car Park", "hall", "parking", pbox(30, 20, R, 1225).difference(core))

doors = [
    ("corr", "park", "door", (500, 240), 1.0),
    ("corr", "park", "door", (670, 240), 1.0),
    ("corr", "park", "door", (595, 768), 1.0),
    ("lift", "corr", "door", (562, 320), 1.2),
    ("stairs", "corr", "opening", (628, 330), 1.5),
    ("st1", "corr", "door", (562, 375), 1.0),
    ("st2", "corr", "door", (562, 625), 1.0),
    ("bma", "corr", "door", (628, 515), 0.9),
    ("bos", "corr", "door", (628, 570), 0.9),
    ("st3", "corr", "door", (760, 598), 1.0),
    ("st4", "corr", "door", (720, 645), 1.0),
    ("nshv", "corr", "door", (785, 645), 1.0),
    ("srv1", "corr", "door", (718, 265), 1.0),
    ("srv2", "srv1", "door", (780, 360), 1.0),
]

devices = [
    ("fire_extinguisher", "corr", (575, 462)),
    ("fire_extinguisher", "corr", (612, 625)),
    ("fire_extinguisher", "park", (180, 655)),
    ("fire_extinguisher", "park", (590, 985)),
    ("manual_call_point", "park", (627, 200)),
]


def polygon(geom):
    geom = geom.buffer(0)
    assert geom.geom_type == "Polygon" and not geom.interiors, geom.geom_type
    return [tx(px, py) for px, py in list(geom.exterior.coords)[:-1]]


b = json.loads(PATH.read_text())
assert all(f["id"] != F for f in b["floors"]), "B1 already there"
b["floors"].append({"id": F, "level": -1, "name": "Basement", "elevation_m": -3.0, "height_m": 3.0})
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
for n, (a, c, kind, (px, py), w) in enumerate(doors, 1):
    wall = shape[a].boundary.intersection(shape[c].buffer(0.5))
    assert not wall.is_empty and wall.distance(Point(px, py)) < 3, (a, c)
    b["openings"].append(
        {
            "id": f"{F}-O{n:04d}",
            "floor_id": F,
            "space_ids": [ids[a], ids[c]],
            "kind": kind,
            "position": tx(px, py),
            "width_m": w,
            "step_free": True,
            "synthetic": False,
        }
    )
names = {"fire_extinguisher": "Fire extinguisher", "manual_call_point": "Fire alarm call point"}
size = {"fire_extinguisher": (0.3, 0.3), "manual_call_point": (0.15, 0.1)}
next_id = max(int(a["id"].split("-A")[1]) for a in b["assets"]) + 1
count = {}
for typ, key, (px, py) in devices:
    assert shape[key].buffer(1).contains(Point(px, py)), (typ, key)
    count[typ] = count.get(typ, 0) + 1
    b["assets"].append(
        {
            "id": f"{B}-A{next_id:05d}",
            "name": f"{names[typ]} B.{count[typ]:02d}",
            "category": "equipment",
            "type": typ,
            "space_id": ids[key],
            "floor_id": F,
            "position": tx(px, py),
            "footprint": {"width_m": size[typ][0], "depth_m": size[typ][1], "rotation_deg": 0.0},
            "source": "evacuation_plan",
        }
    )
    next_id += 1
for vc in b["vertical_connectors"]:
    vc["floor_ids"].insert(0, F)
    vc["space_ids"].insert(0, ids["lift" if vc["kind"] == "lift" else "stairs"])
PATH.write_text(json.dumps(b, indent=1, ensure_ascii=False))
print("B1:", len(rooms), "spaces,", len(doors), "openings,", count)
