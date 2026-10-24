# ruff: noqa: BLE001, S110, B023
"""Drawn-versus-data audit of the 3D twin (twin/): what the scene really draws against what the JSON API says.

Run it with `scripts/twin_audit.sh` (starts the Python server without an API key and the twin dev server, opens
N buildings in headless Chromium, prints one table, exits non-zero on a mismatch) or through
`tests/e2e/test_twin_audit.py` (pytest -m e2e). It reads the scene through `window.__twinAudit` (twin/src/audit.ts),
so it does not depend on class names or line numbers of the twin code.

Checks per building:
  counts   spaces, connectors, assets, and doors / openings / entrances (a gap in the drawn walls and outline
           at the opening) drawn versus the data
  gaps     no wall top and no outline line across any opening of kind 'opening' (centre and both ends)
  routes   5 random room pairs: the drawn polyline is the server's route points, in order (tolerance 2 cm)
  edits    a door added with /api/door is a gap, a door in state.removed_openings is wall again
  closed   /api/close on a door, a room and a connector draws closed markers; reopening removes them; a route
           recomputed with its connector closed does not use it any more
Once per run: the campus route drawn on the site map follows the legs' world points.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TWIN = ROOT / "twin"

# A fixed, diverse default list (all in data/dev): proc factory (2 floors, openings), proc factory with 3 floors and
# lifts, proc campus, swiss (doors 0.9 m), osm (rotated), resplan (single floor), multi-floor osm with lifts.
DEFAULT_BUILDINGS = [
    "dev/proc-factory-dev-003",
    "dev/proc-factory-dev-005",
    "dev/proc-campus-dev-000",
    "dev/swiss-203",
    "dev/swiss-1689",
    "dev/osm-way27326387",
    "dev/osm-way22744230",
    "dev/osm-way360544293",
    "dev/resplan-1465",
    "dev/resplan-3832",
]

DOOR_REACH = 0.8  # same meaning as in twin/src/scene/geometry.ts: a door belongs to the edge within this distance
SHARED_TOL = 0.35
ROUTE_TOL = 0.02
ASSET_LIMIT = 4000  # per floor, the twin's ALL_THINGS_LIMIT


# ---------------------------------------------------------------- small geometry (independent of the twin code)


def _edges(polygon):
    return [(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))]


def _nearest_on_edge(a, b, p):
    length = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
    s = max(0.0, min(length, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / length))
    q = (a[0] + (b[0] - a[0]) / length * s, a[1] + (b[1] - a[1]) / length * s)
    return s, math.hypot(p[0] - q[0], p[1] - q[1]), length, q


def shared_boundaries(first, second):
    found = []
    for a, b in _edges(first):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 0.05:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        for c, d in _edges(second):
            off = lambda r: abs((r[0] - a[0]) * uy - (r[1] - a[1]) * ux)
            if off(c) > SHARED_TOL or off(d) > SHARED_TOL:
                continue
            along = lambda r: (r[0] - a[0]) * ux + (r[1] - a[1]) * uy
            s0 = max(0.0, min(along(c), along(d)))
            s1 = min(length, max(along(c), along(d)))
            if s1 - s0 > 0.05:
                found.append(((a[0] + ux * s0, a[1] + uy * s0), (a[0] + ux * s1, a[1] + uy * s1)))
    return found


def is_zone(width, length):
    """Same rule as the twin: an opening of 4 m or more that spans most of the shared boundary is a hall zone line."""
    return width >= 4 and width >= length * 0.6


def zone_midpoints(opening, polygons):
    """Midpoints of the shared boundary for openings drawn as zone lines (else an empty list)."""
    if opening["kind"] != "opening" or len(polygons) < 2:
        return []
    segs = shared_boundaries(polygons[0], polygons[1])
    if not segs:
        return []
    best = min(segs, key=lambda seg: _nearest_on_edge(seg[0], seg[1], opening["position"])[1])
    if not is_zone(opening.get("width_m") or 0.9, math.dist(*best)):
        return []
    return [((best[0][0] + best[1][0]) / 2, (best[0][1] + best[1][1]) / 2)]


def probe_points(opening, polygons):
    """Points on the wall line where the opening must be a gap, or None when the data puts it off any wall."""
    width = opening.get("width_m") or 0.9
    pos = opening["position"]
    if len(polygons) >= 2:
        best = None
        for seg in shared_boundaries(polygons[0], polygons[1]):
            s, dist, length, _ = _nearest_on_edge(seg[0], seg[1], pos)
            if best is None or dist < best[0]:
                best = (dist, seg, s, length)
        if best and (opening["kind"] == "opening" or best[0] <= DOOR_REACH):
            _, seg, s, length = best
            ux, uy = (seg[1][0] - seg[0][0]) / length, (seg[1][1] - seg[0][1]) / length
            if opening["kind"] == "opening":
                if is_zone(width, length):
                    # a hall zone line: no wall along the whole shared boundary
                    return [
                        (seg[0][0] + ux * length * k, seg[0][1] + uy * length * k)
                        for k in (0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95)
                    ]
                lo, hi = (
                    (0.0, length) if width >= length - 0.01 else (max(0.0, s - width / 2), min(length, s + width / 2))
                )
            else:
                half = max(0.3, width / 2)
                lo, hi = max(0.0, s - half), min(length, s + half)
            # inside the gap, away from its ends (an end can be a wall corner)
            return [
                (seg[0][0] + ux * (lo + (hi - lo) * k), seg[0][1] + uy * (lo + (hi - lo) * k))
                for k in (0.35, 0.5, 0.65)
            ]
    near = []
    for polygon in polygons:
        for a, b in _edges(polygon):
            s, dist, length, _ = _nearest_on_edge(a, b, pos)
            if length >= 0.05:
                near.append((dist, a, b, s, length))
    if not near or min(n[0] for n in near) > DOOR_REACH:
        return None
    closest = min(n[0] for n in near)
    half = max(0.3, width / 2)
    out = []
    for dist, a, b, s, length in near:
        if dist <= closest + 0.05:  # a door at a corner opens both edges
            mid = (max(0.0, s - half) + min(length, s + half)) / 2  # middle of that gap
            out.append((a[0] + (b[0] - a[0]) / length * mid, a[1] + (b[1] - a[1]) / length * mid))
    return out


# ---------------------------------------------------------------- plumbing


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(url: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up in {timeout:.0f} s")


class Stack:
    """The Python server (no API key) and the twin dev server, or an already running twin (TWIN_AUDIT_BASE)."""

    def __init__(self, data: Path | None = None):
        self.procs: list[subprocess.Popen] = []
        self.data = data or Path(os.environ.get("TWIN_AUDIT_DATA", ROOT / "data"))
        self.base = os.environ.get("TWIN_AUDIT_BASE", "").rstrip("/")

    def __enter__(self):
        if self.base:
            wait_http(self.base + "/api/status", 10)
            return self
        api_port, twin_port = free_port(), free_port()
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")}
        self.procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "web", "--data", str(self.data), "--port", str(api_port)],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        wait_http(f"http://127.0.0.1:{api_port}/api/status")
        vite = TWIN / "node_modules" / ".bin" / "vite"
        self.procs.append(
            subprocess.Popen(
                [str(vite), "--port", str(twin_port), "--strictPort", "--host", "127.0.0.1"],
                cwd=TWIN,
                env={**env, "TWIN_API": f"http://127.0.0.1:{api_port}"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        self.base = f"http://127.0.0.1:{twin_port}"
        wait_http(self.base + "/api/status")
        return self

    def __exit__(self, *exc):
        for proc in self.procs:
            proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    # JSON helpers against the API (through the twin's proxy, same origin as the page)
    def get(self, path: str):
        return json.load(urllib.request.urlopen(self.base + path, timeout=60))

    def post(self, path: str, body: dict):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        return json.load(urllib.request.urlopen(request, timeout=60))


@dataclass
class Row:
    building: str
    check: str
    data: str
    drawn: str
    ok: bool
    note: str = ""


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)

    def add(self, building, check, data, drawn, ok, note=""):
        self.rows.append(Row(building, check, str(data), str(drawn), bool(ok), note))

    def table(self) -> str:
        lines = [f"{'building':26} {'check':26} {'data':>8} {'drawn':>8}  result"]
        for r in self.rows:
            lines.append(
                f"{r.building[-26:]:26} {r.check:26} {r.data:>8} {r.drawn:>8}  {'ok' if r.ok else 'MISMATCH'} {r.note}".rstrip()
            )
        bad = sum(not r.ok for r in self.rows)
        lines.append(f"\n{len(self.rows)} checks, {bad} mismatches")
        return "\n".join(lines)

    @property
    def failed(self) -> list[Row]:
        return [r for r in self.rows if not r.ok]


# ---------------------------------------------------------------- the checks


def open_building(browser, stack: Stack, key: str):
    context = browser.new_context(viewport={"width": 1100, "height": 420})
    page = context.new_page()
    page.goto(f"{stack.base}/?building={key}")
    page.wait_for_function(
        "window.__twinAudit && window.__twinAudit.store.getState().model && !window.__twinAudit.store.getState().loading",
        timeout=120000,
    )
    page.evaluate(
        """() => { const s = window.__twinAudit.store.getState();
          s.setViewMode('3d'); s.setFloorMode('exploded'); s.setThingsMode('all'); window.__twinAudit.store.setState({ ao: false }); }"""
    )
    page.wait_for_function("window.__twinAudit.drawnSpaces().length > 0", timeout=60000)
    page.wait_for_timeout(800)
    return context, page


def dedupe(points, tol=1e-6):
    out = []
    for p in points:
        if not out or math.hypot(out[-1][0] - p[0], out[-1][1] - p[1]) > tol:
            out.append(tuple(p))
    return out


def check_counts(report, page, key, data):
    spaces = {s["id"]: s for s in data["spaces"]}
    polys = {s["id"]: s["polygon"] for s in data["spaces"]}
    drawn_spaces = set(page.evaluate("window.__twinAudit.drawnSpaces()"))
    report.add(key, "spaces", len(spaces), len(drawn_spaces & set(spaces)), drawn_spaces >= set(spaces))
    connectors_drawn = sum(1 for c in data["connectors"] if all(i in drawn_spaces for i in c["space_ids"]))
    report.add(
        key,
        "connectors (all stops)",
        len(data["connectors"]),
        connectors_drawn,
        connectors_drawn == len(data["connectors"]),
    )
    per_floor: dict[str, int] = {}
    for a in data["assets"]:
        per_floor[a["floor_id"]] = per_floor.get(a["floor_id"], 0) + 1
    expected_assets = sum(min(n, ASSET_LIMIT) for n in per_floor.values())
    drawn_assets = page.evaluate("window.__twinAudit.drawnThings()")
    report.add(key, "assets", expected_assets, drawn_assets, drawn_assets == expected_assets)

    probes, meta = [], []
    for o in data["openings"]:
        pts = probe_points(o, [polys[i] for i in o["space_ids"] if i in polys])
        meta.append((o, pts))
        probes.extend([o["floor_id"], p[0], p[1]] for p in (pts or []))
    blocked = page.evaluate("(list) => list.map(([f, x, y]) => window.__twinAudit.blockedAt(f, [x, y]))", probes)
    cursor = 0
    stats: dict[str, dict[str, int]] = {}
    bad_examples: list[str] = []
    for o, pts in meta:
        kind = o["kind"]
        s = stats.setdefault(kind, {"data": 0, "off_wall": 0, "gap": 0})
        s["data"] += 1
        if pts is None:
            s["off_wall"] += 1
            continue
        mine = blocked[cursor : cursor + len(pts)]
        cursor += len(pts)
        if all(not b["wall"] and not b["line"] for b in mine):
            s["gap"] += 1
        elif len(bad_examples) < 3:
            bad_examples.append(f"{o['id'].split('-', 3)[-1]} {o['width_m']}m")
    zones = [
        (o, zone_midpoints(o, [polys[i] for i in o["space_ids"] if i in polys]))
        for o in data["openings"]
        if o["kind"] == "opening"
    ]
    zones = [(o, mids) for o, mids in zones if mids]
    if zones:
        dashed = page.evaluate(
            "(list) => list.map(([f, x, y]) => window.__twinAudit.zoneLineNear(f, [x, y]))",
            [[o["floor_id"], m[0][0], m[0][1]] for o, m in zones],
        )
        report.add(key, "wide openings as zone lines", len(zones), sum(dashed), all(dashed))
    for kind, s in sorted(stats.items()):
        want = s["data"] - s["off_wall"]
        note = f"off-wall in data: {s['off_wall']}" if s["off_wall"] else ""
        if s["gap"] != want and bad_examples:
            note += " blocked: " + ", ".join(bad_examples)
        report.add(key, f"{kind}s as gaps", s["data"], s["gap"], s["gap"] == want, note.strip())
    return spaces


def room_ids(data):
    return [s["id"] for s in data["spaces"] if s["type"] not in ("outdoor",) and s["name"]]


def check_routes(report, stack, page, key, data, rng):
    ids = room_ids(data)
    floor_of = {s["id"]: s["floor_id"] for s in data["spaces"]}
    ok_routes = good = 0
    worst = 0.0
    multi_floor_pair = None
    pairs = [tuple(rng.sample(ids, 2)) for _ in range(5)]
    if len({s["floor_id"] for s in data["spaces"]}) > 1:
        for _ in range(60):  # one pair with a route that changes floors, for the connector check
            a, b = rng.sample(ids, 2)
            if floor_of[a] == floor_of[b]:
                continue
            found = stack.post("/api/route", {"building": key, "start": a, "destination": b})["route"]
            if found.get("ok") and found.get("floor_changes"):
                multi_floor_pair = (a, b)
                break
        if multi_floor_pair:
            pairs[-1] = multi_floor_pair
    for a, b in pairs:
        server = stack.post("/api/route", {"building": key, "start": a, "destination": b})["route"]
        if not server.get("ok"):
            continue
        ok_routes += 1
        expected = dedupe(p for seg in server["segments"] for p in seg["points"])
        page.evaluate("([a, b]) => window.__twinAudit.store.getState().route(a, b)", [a, b])
        page.wait_for_timeout(250)
        drawn = dedupe(page.evaluate("window.__twinAudit.drawnRoute()"))
        if len(drawn) == len(expected):
            dev = max((math.hypot(d[0] - e[0], d[1] - e[1]) for d, e in zip(drawn, expected)), default=0.0)
        else:
            dev = float("inf")
        worst = max(worst, dev)
        good += dev <= ROUTE_TOL
    report.add(
        key,
        "routes follow server points",
        ok_routes,
        good,
        good == ok_routes,
        "" if good == ok_routes else f"max deviation {worst:.2f} m",
    )
    page.evaluate("window.__twinAudit.store.getState().clearRoute()")
    return multi_floor_pair


def check_closed(report, stack, page, key, data, pair):
    store = "window.__twinAudit.store.getState()"
    spaces = {s["id"]: s for s in data["spaces"]}
    targets = []
    door = next((o for o in data["openings"] if o["kind"] == "door"), None)
    if door:
        targets.append(("door", door["id"], 1))
    room = next((s for s in data["spaces"] if s["type"] == "room"), None)
    if room:
        targets.append(("room", room["id"], 1))
    connector = data["connectors"][0] if data["connectors"] else None
    if connector:
        targets.append(("connector", connector["id"], len([i for i in connector["space_ids"] if i in spaces])))
    for label, element, expected in targets:
        page.evaluate(f"(id) => {store}.setClosed(id, true)", element)
        page.wait_for_timeout(300)
        closed = page.evaluate("window.__twinAudit.drawnClosed()")
        page.evaluate(f"(id) => {store}.setClosed(id, false)", element)
        page.wait_for_timeout(300)
        reopened = page.evaluate("window.__twinAudit.drawnClosed()")
        ok = closed["elements"] == expected and reopened["elements"] == 0
        if label == "door":  # a closed door also gets a bar across its gap
            ok = ok and closed["bars"] == 1 and reopened["bars"] == 0
        report.add(
            key,
            f"closed {label} drawn",
            expected,
            closed["elements"],
            ok,
            "" if reopened["elements"] == 0 else "still drawn after reopen",
        )
    if connector and pair:
        route = stack.post("/api/route", {"building": key, "start": pair[0], "destination": pair[1]})["route"]
        used = [c["connector_id"] for c in (route.get("floor_changes") or [])]
        if route.get("ok") and used:
            target = used[0]
            page.evaluate(f"([a, b]) => {store}.route(a, b)", list(pair))
            page.evaluate(f"(id) => {store}.setClosed(id, true)", target)
            page.wait_for_timeout(300)
            # the server recomputes state.route on a closure; the UI just redraws it
            new = page.evaluate(f"{store}.state.route")
            avoids = (not new.get("ok")) or target not in [c["connector_id"] for c in (new.get("floor_changes") or [])]
            drawn = dedupe(page.evaluate("window.__twinAudit.drawnRoute()"))
            expected = dedupe(p for seg in (new.get("segments") or []) for p in seg["points"]) if new.get("ok") else []
            matches = len(drawn) == len(expected) and all(
                math.hypot(d[0] - e[0], d[1] - e[1]) <= ROUTE_TOL for d, e in zip(drawn, expected)
            )
            report.add(
                key,
                "route avoids closed connector",
                target.split("-")[-1],
                "avoided" if avoids else "USED",
                avoids and matches,
                "" if matches else "drawn line is not the new route",
            )
            page.evaluate(f"(id) => {store}.setClosed(id, false)", target)
            page.evaluate(f"{store}.clearRoute()")
        else:
            report.add(key, "route avoids closed connector", "-", "-", True, "no floor-changing route found, skipped")


def _blocked(page, floor_id, point):
    return page.evaluate("([f, x, y]) => window.__twinAudit.blockedAt(f, [x, y])", [floor_id, point[0], point[1]])


def check_edits(report, stack, page, key, data):
    """Doors added in the session (/api/door) are drawn as gaps; doors removed in the state are wall again."""
    store = "window.__twinAudit.store.getState()"
    spaces = {s["id"]: s for s in data["spaces"]}
    have = {tuple(sorted(o["space_ids"])) for o in data["openings"]}
    floors = sorted({s["floor_id"] for s in data["spaces"]})
    pair = None
    for floor_id in floors[:2]:
        rooms = [s for s in data["spaces"] if s["floor_id"] == floor_id and s["type"] in ("room", "corridor", "hall")]
        for i, a in enumerate(rooms):
            for c in rooms[i + 1 :]:
                if tuple(sorted((a["id"], c["id"]))) in have:
                    continue
                if any(math.dist(*seg) > 1.5 for seg in shared_boundaries(a["polygon"], c["polygon"])):
                    pair = (a, c)
                    break
            if pair:
                break
        if pair:
            break
    if pair:
        a, c = pair
        page.evaluate(f"([a, b]) => {store}.addDoor(a, b)", [a["id"], c["id"]])
        page.wait_for_timeout(500)
        door = page.evaluate(f"{store}.state.added_doors[0]")
        pts = probe_points({"kind": "door", "position": door["position"], "width_m": 0.9}, [a["polygon"], c["polygon"]])
        mine = [_blocked(page, door["floor_id"], p) for p in pts or []]
        ok = bool(pts) and all(not b["wall"] and not b["line"] for b in mine)
        report.add(key, "added door drawn as gap", 1, int(ok), ok)
        page.evaluate(f"{store}.reset()")
        page.wait_for_timeout(500)
    else:
        report.add(key, "added door drawn as gap", "-", "-", True, "no door-less neighbours, skipped")
    door = next((o for o in data["openings"] if o["kind"] == "door" and len(o["space_ids"]) == 2), None)
    if door:
        pts = probe_points(door, [spaces[i]["polygon"] for i in door["space_ids"]])
        if pts:
            page.evaluate(
                f"(id) => {{ const s = {store}; s.applyState({{ ...s.state, removed_openings: [id] }}); }}", door["id"]
            )
            page.wait_for_timeout(500)
            after = [_blocked(page, door["floor_id"], p) for p in pts]
            ok = any(b["wall"] for b in after)
            report.add(key, "removed door drawn as wall", 1, int(ok), ok)
            page.evaluate(f"{store}.reset()")
            page.wait_for_timeout(500)


def check_building(browser, stack, key, report):
    data = stack.get(f"/api/building?key={key}")
    rng = random.Random(key)
    t0 = time.time()
    context, page = open_building(browser, stack, key)
    t1 = time.time()
    try:
        check_counts(report, page, key, data)
        t2 = time.time()
        pair = check_routes(report, stack, page, key, data, rng)
        t3 = time.time()
        check_closed(report, stack, page, key, data, pair)
        check_edits(report, stack, page, key, data)
        print(
            f"  open {t1 - t0:.0f} s, counts {t2 - t1:.0f} s, routes {t3 - t2:.0f} s, closed {time.time() - t3:.0f} s",
            flush=True,
        )
    finally:
        context.close()
        try:
            stack.post("/api/reset", {"building": key})
        except Exception:
            pass


def check_campus(browser, stack, report):
    try:
        loaded = stack.post("/api/campus/load", {"key": "example"})
    except Exception as error:  # an older server without campus endpoints
        report.add("campus example", "campus available", "-", "-", True, f"skipped ({error})")
        return
    view = loaded["campus"]
    mapped = [b for b in view["buildings"] if b.get("page_key")]
    if len(mapped) < 2:
        report.add("campus example", "campus buildings with maps", 2, len(mapped), False)
        return
    firsts = []
    for b in mapped[:2]:
        data = stack.get(f"/api/building?key={b['page_key']}")
        room = next(s for s in data["spaces"] if s["type"] == "room" and s["name"])
        firsts.append((b["id"], room["id"]))
    route = stack.post(
        "/api/campus/route",
        {
            "start": firsts[0][1],
            "destination": firsts[1][1],
            "start_building": firsts[0][0],
            "destination_building": firsts[1][0],
        },
    )
    if not route.get("ok"):
        report.add("campus example", "campus route", "ok", route.get("error", "?"), False)
        return
    expected = []
    for leg in route["legs"]:
        pts = (
            [leg["from"]["world_point"], leg["to"]["world_point"]]
            if leg["kind"] == "link"
            else (leg.get("world_points") or [])
        )
        expected.extend(p for p in pts if p)
    expected = dedupe(expected, 0.01)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.goto(f"{stack.base}/?campus=example")
    page.wait_for_function("window.__twinAudit && window.__twinAudit.campus.getState().view?.loaded", timeout=120000)
    page.evaluate(
        """async ([a, b, sa, sb]) => { const c = window.__twinAudit.campus; await c.getState().routeBetween(a, b, { startBuilding: sa, destinationBuilding: sb });
          window.__twinAudit.store.getState().setViewMode('2d'); c.setState({ mode: 'site', current: null }); }""",
        [firsts[0][1], firsts[1][1], firsts[0][0], firsts[1][0]],
    )
    page.wait_for_selector("[data-audit=campus-route]", timeout=30000)
    d = page.get_attribute("[data-audit=campus-route]", "d")
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    drawn = [(nums[i], -nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    ok = len(drawn) == len(expected) and all(
        math.hypot(a[0] - b[0], a[1] - b[1]) <= 0.02 for a, b in zip(drawn, expected)
    )
    report.add(
        "campus example",
        "campus route legs drawn",
        len(expected),
        len(drawn),
        ok,
        "" if ok else "site-map line differs from the legs' world points",
    )
    context.close()


def run(buildings=None, campus=True, log=print) -> Report:
    from playwright.sync_api import sync_playwright

    report = Report()
    with Stack() as stack, sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        try:
            for key in buildings or DEFAULT_BUILDINGS:
                started = time.time()
                before = len(report.rows)
                try:
                    check_building(browser, stack, key, report)
                except Exception as error:  # a crash is a finding, not a reason to stop the run
                    report.add(key, "audit ran", "-", "-", False, f"{type(error).__name__}: {str(error)[:120]}")
                log(f"{key}: {len(report.rows) - before} checks in {time.time() - started:.0f} s")
            if campus:
                try:
                    check_campus(browser, stack, report)
                except Exception as error:
                    report.add(
                        "campus example", "audit ran", "-", "-", False, f"{type(error).__name__}: {str(error)[:120]}"
                    )
        finally:
            browser.close()
    return report


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "-n", type=int, default=len(DEFAULT_BUILDINGS), help="number of buildings from the default list"
    )
    parser.add_argument("--building", action="append", help="audit this key instead of the default list (repeatable)")
    parser.add_argument("--no-campus", action="store_true")
    args = parser.parse_args(argv)
    keys = args.building or DEFAULT_BUILDINGS[: args.n]
    report = run(keys, campus=not args.no_campus)
    print()
    print(report.table())
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
