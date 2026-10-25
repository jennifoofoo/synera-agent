"""Add Floor 3 of the Urban Colab to building.json, from the two evacuation plans OG3.04 (east) and OG3.08 (west).

Reproducible: run on a building.json that has no F3 yet. Everything is drawn in the pixel frame of
crops/OG3-04_floor3_east.jpg ("U" frame, y down). OG3.08 is photographed rotated by 90 degrees (its top is west);
it shares the kitchen, cleaning room and IT room with OG3.04, which gives the join:
    X = py - 1290, Y = 840 - px          (px, py = pixel in crops/OG3-08_floor3_west.jpg)
The U frame goes into the building frame with the lift centre and the main stairs as anchors
(lift centre F0 11.24/19.25, F1 11.55/19.06; the stairs' east end lands on 9.1, the core walls on y 17.7/21.1):
    x = 11.4 + (X - 795) * 0.031,  y = 19.15 - (Y - 302) * 0.031
Usage: python add_floor3.py demo/buildings/plan-89323a15/building.json
"""

import json
import sys

from shapely.geometry import Point, box
from shapely.ops import unary_union

PATH = sys.argv[1]
B = "plan-89323a15"
F = f"{B}-F3"
S = 0.031


def tx(X, Y):
    return [round(11.4 + (X - 795) * S, 3), round(19.15 - (Y - 302) * S, 3)]


def ubox(x0, y0, x1, y1):
    return box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def to_polygon(geom):
    geom = geom.buffer(0)
    assert geom.geom_type == "Polygon", geom.geom_type
    assert not geom.interiors, "hole"
    pts = list(geom.exterior.coords)[:-1]
    return [tx(X, Y) for X, Y in pts]


def oo8(px0, px1, py0, py1):
    """A box given in OG3.08 pixels, returned in U."""
    return ubox(py0 - 1290, 840 - px0, py1 - 1290, 840 - px1)


# ---- rooms in the U frame ------------------------------------------------------------------------------------------
NORTH, SOUTH = 30, 765  # facades of the main part; the west office strip reaches north to -160
rooms = {}  # key -> (name, type, room_type, geometry)


def add(key, name, typ, room_type, geom):
    rooms[key] = (name, typ, room_type, geom)


add("kitchen", "Kitchen", "room", "kitchen", ubox(-45, NORTH, 185, 185))
for i, (x0, x1) in enumerate([(185, 410), (410, 545), (545, 680), (680, 810), (810, 985)], 1):
    add(f"mr{i}", f"Meeting Room 3.0{i}", "room", "meeting_room", ubox(x0, NORTH, x1, 185))
add("clean", "Cleaning Room", "room", "storage", ubox(20, 240, 95, 350))
add("it", "IT Room", "room", "server_room", ubox(95, 240, 185, 350))
add("elt", "Electrical Room", "room", "storage", ubox(185, 240, 272, 350))
add("wc1", "Toilets", "room", "toilet", ubox(272, 240, 352, 350))
add("wc2", "Toilets", "room", "toilet", ubox(352, 240, 490, 350))
add("wc3", "Toilets", "room", "toilet", ubox(540, 240, 760, 350))
add("lift", "Lift", "lift", "lift", ubox(760, 240, 855, 350))
add("stairs", "Main Stairs", "stair", "stairwell", ubox(235, 440, 720, 548))
add("void_s", "Void", "room", "outdoor", ubox(235, 548, 720, SOUTH))
corridor = unary_union(
    [
        ubox(-45, 185, 855, 240),
        ubox(490, 240, 540, 350),
        ubox(20, 350, 855, 440),
        ubox(95, 440, 235, SOUTH),
        ubox(720, 440, 855, SOUTH),
    ]
)
add("corr", "Third Floor Corridor", "corridor", "corridor", corridor)
# east (OG3.04)
add("void_e", "Void", "room", "outdoor", ubox(1175, NORTH, 1565, 350))
add("terr_e", "Terrace East", "outdoor", "balcony", ubox(1175, 350, 1565, 540))
add("tt1", "Think Tank 3.01", "room", "office", ubox(1160, 590, 1255, 650))
add("tt2", "Think Tank 3.02", "room", "office", ubox(1160, 650, 1255, SOUTH))
taken_e = unary_union([rooms[k][3] for k in ("mr5", "void_e", "terr_e", "tt1", "tt2")])
add("open_e", "Open Office East", "room", "office", ubox(855, NORTH, 1565, SOUTH).difference(taken_e))
# west (OG3.08)
W, CW = -1260, (-1055, -995)
for i, (y0, y1) in enumerate([(SOUTH, 565), (565, 430), (235, 130), (130, -15), (-15, -160)], 1):
    add(f"off{i}", f"Office 3.0{i}", "room", "office", ubox(W, y0, CW[0], y1))
add("nw_stairs", "North-West Stairs", "stair", "stairwell", ubox(W, 430, CW[0], 235))
add("corr_w", "West Wing Corridor", "corridor", "corridor", ubox(CW[0], -160, CW[1], SOUTH))
add("void_w", "Void", "room", "outdoor", ubox(-790, NORTH, -255, 360))
add("terr_w", "Terrace West", "outdoor", "balcony", ubox(-790, 360, -255, 550))
add("tt3", "Think Tank 3.03", "room", "office", ubox(-805, SOUTH, -700, 685))
add("tt4", "Think Tank 3.04", "room", "office", ubox(-805, 685, -700, 610))
add("tt5", "Think Tank 3.05", "room", "office", ubox(-340, SOUTH, -235, 680))
add("tt6", "Think Tank 3.06", "room", "office", ubox(-340, 680, -235, 605))
open_w = unary_union(
    [ubox(CW[1], -160, -810, SOUTH), ubox(-810, NORTH, -45, SOUTH), ubox(-45, 240, 20, SOUTH), ubox(20, 440, 95, SOUTH)]
)
taken_w = unary_union([rooms[k][3] for k in ("void_w", "terr_w", "tt3", "tt4", "tt5", "tt6")])
# the corridor's passage x 20..95 / y 350..440 stays corridor
add("open_w", "Open Office West", "room", "office", open_w.difference(taken_w).difference(corridor))

# ---- doors (U frame) -----------------------------------------------------------------------------------------------
doors = [
    ("kitchen", "corr", "door", (0, 185), 1.0),
    ("mr1", "corr", "door", (350, 185), 1.0),
    ("mr2", "corr", "door", (480, 185), 1.0),
    ("mr3", "corr", "door", (610, 185), 1.0),
    ("mr4", "corr", "door", (745, 185), 1.0),
    ("mr5", "open_e", "door", (880, 185), 1.0),
    ("it", "corr", "door", (160, 240), 1.0),
    ("elt", "corr", "door", (250, 240), 1.0),
    ("wc1", "corr", "door", (300, 240), 1.0),
    ("wc2", "corr", "door", (490, 328), 1.0),
    ("wc3", "corr", "door", (540, 328), 1.0),
    ("clean", "corr", "door", (70, 350), 1.0),
    ("lift", "corr", "door", (805, 350), 1.2),
    ("stairs", "corr", "opening", (480, 440), 2.5),
    ("corr", "open_e", "opening", (855, 212), 1.7),
    ("corr", "open_e", "opening", (855, 395), 2.5),
    ("corr", "open_w", "opening", (-45, 212), 1.7),
    ("corr", "open_w", "door", (20, 395), 1.2),
    ("terr_e", "open_e", "door", (1175, 445), 1.0),
    ("tt1", "open_e", "door", (1230, 590), 0.9),
    ("tt2", "open_e", "door", (1255, 710), 0.9),
    # west wing
    ("off1", "corr_w", "door", (CW[0], 720), 1.0),
    ("off1", "corr_w", "door", (CW[0], 630), 1.0),
    ("off2", "corr_w", "door", (CW[0], 520), 1.0),
    ("off3", "corr_w", "door", (CW[0], 165), 1.0),
    ("off4", "corr_w", "door", (CW[0], 55), 1.0),
    ("off5", "corr_w", "door", (CW[0], -90), 1.0),
    ("nw_stairs", "corr_w", "opening", (CW[0], 330), 1.5),
    ("corr_w", "open_w", "opening", (CW[1], 100), 3.0),
    ("corr_w", "open_w", "opening", (CW[1], 650), 3.0),
    ("terr_w", "open_w", "door", (-255, 450), 1.0),
    ("tt3", "open_w", "door", (-750, 685), 0.9),  # placeholder, moved to the free wall below
    ("tt4", "open_w", "door", (-750, 610), 0.9),
    ("tt5", "open_w", "door", (-235, 720), 0.9),
    ("tt6", "open_w", "door", (-290, 605), 0.9),
]
# Think Tank 3.03 opens to the west, not into 3.04
doors[[d[0] for d in doors].index("tt3")] = ("tt3", "open_w", "door", (-805, 725), 0.9)

# ---- devices (U frame), where the symbol hangs on the plan ---------------------------------------------------------
devices = [
    ("fire_extinguisher", "it", (115, 258)),  # OG3.04 inside the IT room (also on OG3.08)
    ("fire_extinguisher", "corr", (470, 236)),  # north corridor, on the core wall
    ("fire_extinguisher", "open_e", (862, 362)),  # beside the lift, east
    ("fire_extinguisher", "corr", (100, 445)),  # west leg, west wall (also on OG3.08)
    ("fire_extinguisher", "corr_w", (-1050, 225)),  # west wing corridor at the north-west stairs (OG3.08)
    ("fire_extinguisher", "open_w", (-515, SOUTH - 8)),  # west wing, south facade (OG3.08)
    ("manual_call_point", "corr", (100, 495)),
    ("manual_call_point", "open_e", (862, 440)),
    ("manual_call_point", "corr_w", (-1050, 280)),
    ("first_aid_kit", "kitchen", (90, 130)),
]

# ---- write ---------------------------------------------------------------------------------------------------------
b = json.load(open(PATH))
assert all(f["id"] != F for f in b["floors"]), "F3 already there"
b["floors"].append({"id": F, "level": 3, "name": "Floor 3", "elevation_m": 9.0, "height_m": 3.0})
b["floors"].sort(key=lambda f: f["level"])
ids = {}
for n, (key, (name, typ, room_type, geom)) in enumerate(rooms.items(), 1):
    sid = f"{F}-S{n:03d}"
    ids[key] = sid
    b["spaces"].append(
        {
            "id": sid,
            "floor_id": F,
            "type": typ,
            "name": name,
            "polygon": to_polygon(geom),
            "room_type": room_type,
            "ref": None,
            "synthetic": False,
        }
    )
shape = {k: g for k, (_, _, _, g) in rooms.items()}
for n, (a, c, kind, (X, Y), w) in enumerate(doors, 1):
    # snap onto the shared wall
    wall = shape[a].boundary.intersection(shape[c].buffer(1.0))
    p = Point(X, Y)
    assert not wall.is_empty, (a, c)
    q = (
        wall.interpolate(wall.project(p))
        if wall.geom_type == "LineString"
        else min((g.interpolate(g.project(p)) for g in getattr(wall, "geoms", [wall])), key=p.distance)
    )
    assert q.distance(p) < 15, (a, c, q.distance(p))
    b["openings"].append(
        {
            "id": f"{F}-O{n:04d}",
            "floor_id": F,
            "space_ids": [ids[a], ids[c]],
            "kind": kind,
            "position": tx(q.x, q.y),
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
for typ, key, (X, Y) in devices:
    assert shape[key].buffer(1).contains(Point(X, Y)), (typ, key)
    count[typ] = count.get(typ, 0) + 1
    b["assets"].append(
        {
            "id": f"{B}-A{next_id:05d}",
            "name": f"{names[typ]} 3.{count[typ]:02d}",
            "category": "equipment",
            "type": typ,
            "space_id": ids[key],
            "floor_id": F,
            "position": tx(X, Y),
            "footprint": {"width_m": size[typ][0], "depth_m": size[typ][1], "rotation_deg": 0.0},
            "source": "evacuation_plan",
        }
    )
    next_id += 1
for vc in b["vertical_connectors"]:
    key = {"lift": "lift", "stairs": "stairs"}[vc["kind"]]
    vc["floor_ids"].append(F)
    vc["space_ids"].append(ids[key])
json.dump(b, open(PATH, "w"), indent=1, ensure_ascii=False)
print("F3:", len(rooms), "spaces,", len(doors), "openings,", sum(count.values()), "devices", count)
