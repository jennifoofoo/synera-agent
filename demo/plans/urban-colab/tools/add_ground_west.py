"""Add the west part of the Urban Colab ground floor to building.json, from the evacuation plan E.06.

Reproducible: run once on a building.json whose F0 ends at x ~0.5 (E.05 only). E.06 goes into the building frame with
the lift and the main stairs as anchors: x = 11.24 + (px - 657) * 0.032, y = 19.25 - (py - 440) * 0.032 (stairs land
on 0.6..9.1 / 11.9..14.8, IT and electrical room on their F0 walls). The photo is keystoned near its top edge, so the
new rooms take their y from the F0 walls they continue (Project Room West 22.9..32.2, changing-room row 17.5..22.9).
Existing F0 rooms keep their IDs: Project Room West is extended west (E.05 cut it off), South Corridor gets its west
end. New: Hazardous Materials Store, Toilets, Hand Wash Room, Toilets, North-West Stairs, West Exit Corridor.
Usage: python add_ground_west.py demo/buildings/plan-89323a15/building.json
"""

import json
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon, box

PATH = Path(sys.argv[1])
B = "plan-89323a15"
F = f"{B}-F0"
ROW = (17.5, 22.899)  # south corridor top .. Project Room West bottom

b = json.loads(PATH.read_text())
space = {s["id"]: s for s in b["spaces"]}
assert min(x for x, _ in space[f"{F}-S001"]["polygon"]) > 0, "west part already there"


def polygon(geom):
    geom = geom.buffer(0)
    assert geom.geom_type == "Polygon" and not geom.interiors, geom.geom_type
    return [[round(x, 3), round(y, 3)] for x, y in list(geom.exterior.coords)[:-1]]


# extend two existing rooms (same IDs)
space[f"{F}-S001"]["polygon"] = polygon(box(-4.8, 22.899, 6.583, 32.202))
south = Polygon(space[f"{F}-S009"]["polygon"]).union(box(-7.2, 11.879, 0.52, 17.5))
space[f"{F}-S009"]["polygon"] = polygon(south.simplify(0.001))

new = {
    "haz": ("Hazardous Materials Store", "room", "storage", box(-7.2, ROW[0], -4.8, ROW[1])),
    "wc1": ("Toilets", "room", "toilet", box(-4.8, ROW[0], -2.4, ROW[1])),
    "wash": ("Hand Wash Room", "room", "toilet", box(-2.4, ROW[0], -0.5, ROW[1])),
    "wc2": ("Toilets", "room", "toilet", box(-0.5, ROW[0], 1.145, ROW[1])),
    "nw": ("North-West Stairs", "stair", "stairwell", box(-7.2, 22.899, -4.8, 32.202)),
    "wexit": ("West Exit Corridor", "corridor", "corridor", box(-9.3, 14.1, -7.2, 23.5)),
}
n0 = max(int(s["id"].split("-S")[1]) for s in b["spaces"] if s["floor_id"] == F)
ids = {"south": f"{F}-S009", "prw": f"{F}-S001"}
shape = {"south": Polygon(space[f"{F}-S009"]["polygon"]), "prw": Polygon(space[f"{F}-S001"]["polygon"])}
for i, (key, (name, typ, room_type, geom)) in enumerate(new.items(), 1):
    ids[key] = f"{F}-S{n0 + i:03d}"
    shape[key] = geom
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

doors = [
    ("wc1", "south", "door", (-3.0, 17.5), 1.0),
    ("wash", "south", "door", (-1.3, 17.5), 1.0),
    ("wc2", "south", "door", (0.3, 17.5), 1.0),
    ("haz", "wexit", "door", (-7.2, 21.5), 1.0),
    ("nw", "wexit", "door", (-7.2, 23.2), 1.0),
    ("wexit", "south", "door", (-7.2, 16.0), 1.6),
    ("wexit", "outside", "entrance", (-9.3, 21.6), 1.0),
    ("wexit", "outside", "entrance", (-9.3, 15.5), 1.0),
    ("nw", "outside", "entrance", (-6.0, 32.202), 1.0),
]
m0 = max(int(o["id"].split("-O")[1]) for o in b["openings"] if o["floor_id"] == F and o["id"].split("-O")[1].isdigit())
for i, (a, c, kind, (x, y), w) in enumerate(doors, 1):
    p = Point(x, y)
    if c == "outside":
        assert shape[a].boundary.distance(p) < 0.05, a
        pair = [ids[a], "outside"]
    else:
        wall = shape[a].boundary.intersection(shape[c].buffer(0.05))
        assert not wall.is_empty and wall.distance(p) < 0.3, (a, c)
        pair = [ids[a], ids[c]]
    b["openings"].append(
        {
            "id": f"{F}-O{m0 + i:04d}",
            "floor_id": F,
            "space_ids": pair,
            "kind": kind,
            "position": [x, y],
            "width_m": w,
            "step_free": True,
            "synthetic": False,
        }
    )

devices = [
    ("fire_extinguisher", "prw", (3.3, 32.0)),  # on E.05 and E.06, missing so far
    ("manual_call_point", "prw", (4.8, 32.0)),
    ("manual_call_point", "nw", (-6.4, 29.6)),
    ("fire_extinguisher", "wexit", (-7.6, 22.4)),
    ("fire_extinguisher", "south", (-7.0, 13.3)),
    ("fire_extinguisher", "south", (-3.9, 12.0)),
    ("manual_call_point", "south", (-3.0, 12.0)),
]
names = {"fire_extinguisher": "Fire extinguisher", "manual_call_point": "Fire alarm call point"}
size = {"fire_extinguisher": (0.3, 0.3), "manual_call_point": (0.15, 0.1)}
count = {t: sum(1 for a in b["assets"] if a["floor_id"] == F and a["type"] == t) for t in names}
next_id = max(int(a["id"].split("-A")[1]) for a in b["assets"]) + 1
for typ, key, (x, y) in devices:
    assert shape[key].buffer(0.05).contains(Point(x, y)), (typ, key)
    count[typ] += 1
    b["assets"].append(
        {
            "id": f"{B}-A{next_id:05d}",
            "name": f"{names[typ]} 0.{count[typ]:02d}",
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
PATH.write_text(json.dumps(b, indent=1, ensure_ascii=False))
print("F0 west:", len(new), "new spaces,", len(doors), "openings,", len(devices), "devices")
