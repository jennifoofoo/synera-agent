"""Clean the Urban Colab geometry: rectilinear corridors, rooms cut out of corridors, no overlaps, exits from the plan.
All space, opening and asset ids stay; new exits get new ids appended at the end."""

import json
import sys
from pathlib import Path

from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

path = sys.argv[1]
b = json.loads(Path(path).read_text())
P = "plan-89323a15-"
sp = {s["id"].replace(P, ""): s for s in b["spaces"]}
geo = {k: Polygon(s["polygon"]).buffer(0) for k, s in sp.items()}


def U(*boxes):
    return unary_union([box(*bx) for bx in boxes])


# ---- ground floor
geo["F0-S014"] = Polygon([(37.0, 16.7), (47.5, 16.7), (47.5, 4.3), (37.0, 4.9)])  # Café: straight west wall
geo["F0-S009"] = U(
    (0.52, 14.88, 13.31, 17.5), (8.6, 12.0, 19.6, 17.5), (8.6, 5.0, 21.3, 12.0), (17.17, 17.5, 23.7, 21.18)
)  # Flur Süd
geo["F0-S012"] = U((19.6, 12.0, 37.0, 20.6), (21.3, 4.95, 37.0, 12.0)).difference(box(19.6, 17.5, 23.7, 20.6))  # Foyer
geo["F0-S015"] = U((23.9, 27.2, 44.7, 28.9), (42.9, 28.9, 44.7, 32.2))  # Flur Nord, no pentagon
geo["F0-S023"] = box(42.9, 16.9, 44.7, 27.2)  # Flur Ost
geo["F0-S020"] = box(37.6, 23.5, 42.9, 27.2)
geo["F0-S021"] = box(40.3, 20.3, 42.9, 23.5)
geo["F0-S022"] = U((37.5, 17.0, 42.9, 20.3), (37.5, 20.3, 40.3, 23.5))
# ---- first floor
geo["F1-S002"] = box(-6.7, 21.0, 22.6, 32.2)  # Seminar Rooms 1-3
geo["F1-S009"] = U(
    (-17.0, 15.04, 29.7, 17.56),
    (-17.0, 17.56, -6.6, 17.88),
    (-0.3, 17.56, 3.82, 21.0),
    (12.81, 17.56, 17.16, 21.0),
    (-9.59, 5.4, 13.6, 15.04),
    (13.6, 12.51, 29.7, 15.04),
)  # Flur 1. OG

geo["F1-S012"] = box(-5.17, 5.1, 9.02, 11.88)  # Terrasse up to the stairs (no hole in the corridor)
geo["F1-S011"] = box(0.19, 11.88, 9.34, 14.88)  # stairs and void sit exactly on the terrace edge
geo["F1-S014"] = box(-5.33, 11.88, -1.32, 15.04)
# Corridors and halls give way to rooms (rooms keep their shape); then remaining overlaps go to the smaller space.
YIELD = {
    "F0-S009",
    "F0-S012",
    "F0-S015",
    "F0-S023",
    "F0-S003",
    "F1-S009",
    "F1-S001",
    "F1-S002",
    "F0-S004",
    "F0-S020",
    "F0-S022",
}
for floor in ("F0", "F1"):
    keys = [k for k in geo if k.startswith(floor)]
    for k in keys:
        if k not in YIELD:
            continue
        others = unary_union([geo[o] for o in keys if o != k and (o not in YIELD or geo[o].area < geo[k].area)])
        geo[k] = geo[k].difference(others).buffer(0)


def ring(g, k=""):
    if isinstance(g, MultiPolygon):
        print("MULTI", k, [round(x.area, 1) for x in g.geoms])
        g = max(g.geoms, key=lambda x: x.area)
    if g.interiors:
        print("HOLE", k, len(g.interiors))
    g = g.simplify(0.02)
    pts = [[round(x, 3), round(y, 3)] for x, y in list(g.exterior.coords)[:-1]]
    return pts


for k, s in sp.items():
    s["polygon"] = ring(geo[k], k)

# ---- exits from the evacuation plan (E.05): 5 south, 2 north, 1 north-east; the existing two stay first
new_exits = [
    ("F0-S009", 9.8, 5.0),
    ("F0-S012", 25.2, 4.95),
    ("F0-S012", 33.5, 4.95),
    ("F0-S014", 39.0, 4.8),
    ("F0-S014", 45.5, 4.45),
    ("F0-S002", 12.7, 32.2),
    ("F0-S015", 43.8, 32.2),
]
used = {o["id"] for o in b["openings"]}
n = 100
for k, x, y in new_exits:
    while f"{P}F0-O{n:04d}" in used:
        n += 1
    b["openings"].append(
        {
            "id": f"{P}F0-O{n:04d}",
            "floor_id": P + "F0",
            "space_ids": [P + k, "outside"],
            "kind": "entrance",
            "position": [x, y],
            "width_m": 1.2,
            "step_free": True,
            "synthetic": False,
        }
    )
    used.add(f"{P}F0-O{n:04d}")

# ---- doors as drawn on the plan: Project Room double door mid-west wall and one to the area before the foyer;
# the stairs open to the corridor on their north side (the reader put them on the outer wall)
fixpos = {
    "F0-O-new28": (10.65, 25.5),
    "F0-O0006": (2.0, 14.88),
    "F0-O0007": (3.5, 14.88),
    "F0-O0008": (5.0, 14.88),
    "F0-O0009": (6.5, 14.88),
    "F0-O0010": (8.0, 14.88),
}
for o in b["openings"]:
    k = o["id"].replace(P, "")
    if k in fixpos:
        o["position"] = list(fixpos[k])
while f"{P}F0-O{n:04d}" in used:
    n += 1
b["openings"].append(
    {
        "id": f"{P}F0-O{n:04d}",
        "floor_id": P + "F0",
        "space_ids": [P + "F0-S002", P + "F0-S009"],
        "kind": "door",
        "position": [21.0, 21.2],
        "width_m": 1.8,
        "step_free": True,
        "synthetic": False,
    }
)
used.add(f"{P}F0-O{n:04d}")
# the green corridor is open towards the foyer on the plan (no wall): two wide openings
for pos in ((19.6, 15.0), (22.6, 17.5)):
    while f"{P}F0-O{n:04d}" in used:
        n += 1
    b["openings"].append(
        {
            "id": f"{P}F0-O{n:04d}",
            "floor_id": P + "F0",
            "space_ids": [P + "F0-S009", P + "F0-S012"],
            "kind": "opening",
            "position": list(pos),
            "width_m": 3.0,
            "step_free": True,
            "synthetic": False,
        }
    )
    used.add(f"{P}F0-O{n:04d}")
# ---- every door on the wall its two spaces share, every exit on its space's outer wall
moved, broken = [], []
for o in b["openings"]:
    ids = [i.replace(P, "") for i in o["space_ids"]]
    p = Point(o["position"])
    a = geo[ids[0]]
    if ids[1] == "outside":
        floor_keys = [k for k in geo if k[:2] == ids[0][:2] and k != ids[0]]
        outer = a.boundary.difference(unary_union([geo[k] for k in floor_keys]).buffer(0.2))
        target = outer if not outer.is_empty else a.boundary
    else:
        target = a.boundary.intersection(geo[ids[1]].buffer(0.25))
        if target.is_empty:
            broken.append((o["id"][-6:], ids))
            continue
    q = nearest_points(target, p)[0]
    if q.distance(p) > 0.05:
        moved.append((o["id"][-6:], round(q.distance(p), 2)))
        o["position"] = [round(q.x, 3), round(q.y, 3)]

# ---- devices in the space they now lie in
reassigned = []
for a in b["assets"]:
    p = Point(a["position"])
    floor = a["floor_id"].replace(P, "")
    inside = [k for k in geo if k.startswith(floor) and geo[k].buffer(0.05).contains(p)]
    if inside and P + inside[0] != a["space_id"] and a["space_id"].replace(P, "") not in inside:
        reassigned.append((a["id"][-6:], a["space_id"][-6:], inside[0]))
        a["space_id"] = P + inside[0]
    elif not inside:
        k = min((k for k in geo if k.startswith(floor)), key=lambda k: geo[k].distance(p))
        q = nearest_points(geo[k].buffer(-0.2), p)[0]
        a["position"] = [round(q.x, 3), round(q.y, 3)]
        reassigned.append((a["id"][-6:], "none", k, "moved in"))
        a["space_id"] = P + k

Path(path).write_text(json.dumps(b, ensure_ascii=False, indent=1))
print("moved doors:", moved)
print("doors without a shared wall:", broken)
print("devices reassigned:", reassigned)
