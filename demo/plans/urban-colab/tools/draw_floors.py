# ruff: noqa: SIM115  (one-off data scripts)
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon

b = json.load(open(sys.argv[1]))
out = sys.argv[2]
for f in b["floors"]:
    fig, ax = plt.subplots(figsize=(14, 9))
    sp = [s for s in b["spaces"] if s["floor_id"] == f["id"]]
    for s in sp:
        p = s["polygon"]
        xs = [x for x, _ in p] + [p[0][0]]
        ys = [y for _, y in p] + [p[0][1]]
        ax.plot(xs, ys, lw=1)
        c = Polygon(p).representative_point()
        ax.text(c.x, c.y, s["id"][-3:] + " " + s["name"][:16], fontsize=7, ha="center")
    for o in b["openings"]:
        if o["floor_id"] != f["id"]:
            continue
        x, y = o["position"]
        m = {"door": "o", "opening": "s", "entrance": "^"}[o["kind"]]
        ax.plot(x, y, m, color="red" if o["kind"] == "entrance" else "k", ms=6)
    for a in b["assets"]:
        if a["floor_id"] != f["id"]:
            continue
        ax.plot(*a["position"], "x", color="orange", ms=6)
    # overlaps
    for i, s in enumerate(sp):
        for t in sp[i + 1 :]:
            inter = Polygon(s["polygon"]).buffer(0).intersection(Polygon(t["polygon"]).buffer(0))
            if inter.area > 1.0:
                print(
                    f["id"][-2:],
                    "overlap",
                    s["id"][-3:],
                    s["name"][:14],
                    "/",
                    t["id"][-3:],
                    t["name"][:14],
                    round(inter.area, 1),
                    "m2",
                )
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_title(f["id"])
    fig.savefig(f"{out}/{f['id'][-2:]}.png", dpi=90, bbox_inches="tight")
    plt.close(fig)
print("ok")
