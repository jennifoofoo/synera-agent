"""Question catalogue generator: realistic user questions for one building, with the expected answer
computed by our own kinds and the BuildingMap (field `truth`), never typed by hand.

    uv run python -m tests.catalogue.generate data/dev/proc-factory-dev-003 --write

writes tests/data/question_catalogue.jsonl (the committed catalogue is the proc-factory-dev-003 instance).
Items whose slots a building cannot fill (no lift, no coffee machine, ...) are left out for that building.
Truth types: number, room, rooms_any, route, bool, text_any, none. Behaviours: answer_number, answer_room,
route, ask_back, refuse, edit_card, explain."""

import argparse
import json
from pathlib import Path

from building_agent import routing
from building_agent.registry import load_kinds
from starter_agent.building_map import OUTSIDE, BuildingMap, MapError

CATALOGUE = Path("tests/data/question_catalogue.jsonl")
NON_ROOMS = {"corridor", "stairwell", "lift", "outdoor", "elevator_shaft", "shaft"}
GERMAN = {
    "office": "Büro",
    "meeting_room": "Besprechungsraum",
    "bedroom": "Schlafzimmer",
    "toilet": "Toilette",
    "bathroom": "Badezimmer",
    "kitchen": "Küche",
    "generic_room": "Raum",
    "server_room": "Serverraum",
}
MACHINE_PREFERENCE = ["cnc_mill", "injection_moulding_machine", "drill_press", "welding_station", "waterjet_cutter"]
COFFEE_PREFERENCE = ["coffee_machine", "vending_machine"]
CONSTRUCTED = ("ground floor", "level 0", "floor 0")


def words(value: str) -> str:
    return value.replace("_", " ")


def plural(value: str) -> str:
    text = words(value)
    return text[:-1] + "ies" if text.endswith("y") else text + ("es" if text.endswith(("s", "sh")) else "s")


class Slots:
    """The rooms, floors and things a template can talk about, chosen by rules, never by name."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.bm: BuildingMap = routing.load_map(directory)
        bm = self.bm
        self.floors = sorted(bm.floors.values(), key=lambda floor: floor["level"])
        self.low, self.top = self.floors[0], self.floors[-1]
        self.ground = next((f for f in self.floors if f["level"] == 0), self.low)
        real = [s for s in bm.spaces.values() if s["room_type"] not in NON_ROOMS and s["id"] != OUTSIDE]
        self.real = sorted(real, key=lambda s: s["id"])
        counts: dict[str, int] = {}
        for space in self.real:
            if space["room_type"] not in ("toilet", "bathroom"):
                counts[space["room_type"]] = counts.get(space["room_type"], 0) + 1
        self.type = max(sorted(counts), key=lambda t: counts[t])
        per_floor = {
            f["id"]: sum(1 for s in self.real if s["room_type"] == self.type and s["floor_id"] == f["id"])
            for f in self.floors
        }
        self.main = bm.floors[max(sorted(per_floor), key=lambda f: per_floor[f])]
        self.other = self.top if self.top["id"] != self.main["id"] else self.low
        self.rooms_main = [s for s in self.real if s["room_type"] == self.type and s["floor_id"] == self.main["id"]]
        self.a = self.rooms_main[0]
        self.c = next((s for s in self.real if s["room_type"] == self.type and s["floor_id"] == self.other["id"]), None)
        self.b = None
        self.a_neighbours: list[str] = []
        if "shared_walls_count" in load_kinds():
            found = load_kinds()["shared_walls_count"].fn(bm, start=self.a["id"])
            self.a_neighbours = list(found.get("space_ids", []))
            self.b = next((bm.spaces[i] for i in self.a_neighbours if bm.spaces[i]["room_type"] not in NON_ROOMS), None)
        self.entrance = self.entrance_room()
        self.entrance_rooms = self.all_entrance_rooms()
        self.door_pair, self.nodoor_pair = self.pick_pairs()
        self.lifts = [c for c in bm.connectors.values() if c["kind"] == "lift"]
        self.stairs = [c for c in bm.connectors.values() if c["kind"] == "stairs"]
        self.toilet_type = next(
            (t for t in ("toilet", "bathroom") if any(s["room_type"] == t for s in self.real)), None
        )
        self.kitchen = any(s["room_type"] == "kitchen" for s in self.real)
        asset_counts: dict[str, int] = {}
        for asset in bm.assets.values():
            asset_counts[asset["type"]] = asset_counts.get(asset["type"], 0) + 1
        self.asset_counts = asset_counts
        self.closure = self.pick_closure()
        self.door_limit = self.pick_door_limit()
        self.coffee = next((t for t in COFFEE_PREFERENCE if t in asset_counts), None)
        self.machine = next((t for t in MACHINE_PREFERENCE if t in asset_counts), None)

    # names and phrases
    def name(self, space: dict | None) -> str:
        return space["name"] if space else ""

    def floor_name(self, floor: dict) -> str:
        return floor["name"].lower()

    def floor_variants(self, floor: dict) -> dict[str, str]:
        level = floor["level"]
        full = self.floor_name(floor)
        if level == 0:
            return {
                "full": full,
                "level": "level 0",
                "storey": "storey 0",
                "number": "floor 0",
                "short": "EG",
                "ordinal": full,
            }
        names = {1: "first", 2: "second", 3: "third", 4: "fourth"}
        ordinal = f"{names[level]} floor" if level in names else full
        return {
            "full": full,
            "level": f"level {level}",
            "storey": f"storey {level}",
            "number": f"floor {level}",
            "short": f"{level}F",
            "ordinal": ordinal,
        }

    def entrance_room(self) -> dict | None:
        for opening in sorted(self.bm.openings.values(), key=lambda o: o["id"]):
            if OUTSIDE in opening["space_ids"]:
                space = self.bm.spaces[self.bm.other_side(opening, OUTSIDE)]
                if space["room_type"] not in ("stairwell", "lift"):
                    return space
        return None

    def all_entrance_rooms(self) -> list[dict]:
        found = {}
        for opening in self.bm.openings.values():
            if OUTSIDE in opening["space_ids"]:
                space = self.bm.spaces[self.bm.other_side(opening, OUTSIDE)]
                found[space["id"]] = space
        return list(found.values())

    def pick_pairs(self) -> tuple[tuple | None, tuple | None]:
        """(two rooms joined by a door, two neighbouring rooms with no door between them)."""
        bm = self.bm
        real_ids = {s["id"] for s in self.real}
        joined = None
        for opening in sorted(bm.openings.values(), key=lambda o: o["id"]):
            first, second = opening["space_ids"]
            if (
                first in real_ids
                and second in real_ids
                and bm.spaces[first]["floor_id"] == bm.spaces[second]["floor_id"]
            ):
                joined = (bm.spaces[first], bm.spaces[second])
                break
        doors = {frozenset(o["space_ids"]) for o in bm.openings.values()}
        loose = None
        for neighbour in self.a_neighbours:
            space = bm.spaces[neighbour]
            if space["room_type"] not in NON_ROOMS and frozenset((self.a["id"], neighbour)) not in doors:
                loose = (self.a, space)
                break
        return joined, loose

    def pick_closure(self) -> dict | None:
        """The stair or lift whose closure changes the A to C walk most (a closure that changes nothing teaches nothing)."""
        best, best_delta = None, -1.0
        if self.c is None:
            return None
        base = self.route_length(self.a["id"], self.c["id"])
        for connector in sorted(self.bm.connectors.values(), key=lambda c: c["id"]):
            if self.main["id"] not in connector["floor_ids"] and self.other["id"] not in connector["floor_ids"]:
                continue
            closed = self.route_length(self.a["id"], self.c["id"], closed=(connector["id"],))
            delta = 1e6 if closed is None else (closed - (base or 0))
            if closed is not None and base is not None and delta < 1.0:
                continue
            if delta > best_delta:
                best, best_delta = connector, delta
        return best

    def pick_door_limit(self) -> float:
        """A door width limit that splits the interior doors, so a 'narrower than' question has a real answer."""
        widths = [o["width_m"] for o in self.bm.openings.values() if OUTSIDE not in o["space_ids"]]
        for limit in (0.9, 1.0, 1.1, 1.2, 1.5):
            narrow = sum(1 for w in widths if w < limit)
            if 0 < narrow < len(widths):
                return limit
        return 1.0

    def assets_of(self, asset_type: str) -> list[dict]:
        return sorted((a for a in self.bm.assets.values() if a["type"] == asset_type), key=lambda a: a["id"])

    def rooms_with(self, asset_type: str) -> list[dict]:
        seen = {}
        for asset in self.assets_of(asset_type):
            seen[asset["space_id"]] = self.bm.spaces[asset["space_id"]]
        return list(seen.values())

    def route_length(
        self, start: str, destination: str, step_free: bool = False, closed: tuple[str, ...] = ()
    ) -> float | None:
        bm = self.bm
        for element in closed:
            bm.closed.add(element)
        try:
            return routing.route(bm, start, destination, step_free).length_m
        except MapError:
            return None
        finally:
            for element in closed:
                bm.closed.discard(element)


def number(value: float, rel: float = 0.0, tol_abs: float = 0.0, alts: list[float] | None = None) -> dict:
    return {
        "type": "number",
        "value": round(float(value), 2),
        "tol_rel": rel,
        "tol_abs": tol_abs,
        "alts": [round(float(a), 2) for a in alts or []],
    }


def room_truth(slots: Slots, space_ids: list[str], area: float | None = None) -> dict:
    spaces = [slots.bm.spaces[i] for i in space_ids]
    return {
        "type": "room",
        "names": [s["name"] for s in spaces],
        "refs": [s.get("ref") or "" for s in spaces],
        "area_m2": area,
    }


def route_truth(length: float | None, step_free: bool = False, dest: str | None = None) -> dict:
    return {
        "type": "route",
        "reachable": length is not None,
        "length_m": length,
        "step_free": step_free,
        "destination": dest,
    }


def build(directory: Path) -> list[dict]:
    s = Slots(directory)
    bm, kinds = s.bm, load_kinds()
    items: list[dict] = []
    counters: dict[str, int] = {}

    def add(prefix, persona, intent, turns, behaviour, truth=None, rules=None, tools=None, note=""):
        if isinstance(turns, str):
            turns = [turns]
        counters[prefix] = counters.get(prefix, 0) + 1
        items.append(
            {
                "id": f"{prefix}-{counters[prefix]:02d}",
                "persona": persona,
                "kind_or_intent": intent,
                "text": turns[0],
                "turns": turns,
                "expected_behaviour": behaviour,
                "truth": truth or {"type": "none"},
                "rules": rules or [],
                "expected_tools": tools or [],
                "note": note,
            }
        )

    ty, ty_p = words(s.type), plural(s.type)
    de_ty = GERMAN.get(s.type, ty)
    main, other = s.main, s.other
    fm, fo = s.floor_variants(main), s.floor_variants(other)
    A, B, C = s.a["name"], s.name(s.b), s.name(s.c)
    entrance = s.entrance
    top_id, main_id, other_id = s.top["id"], main["id"], other["id"]

    def tail(kind: str) -> str:
        return {
            "number": " Finish with a line 'Answer: <number>'.",
            "room": " Finish with a line 'Answer: <room name or number>'.",
            "largest": " Finish with a line 'Answer: <room name or number>, <area> m²'.",
        }[kind]

    # ---------------- benchmark kinds ----------------
    largest = kinds["largest_room"].fn(bm, floor_id=main_id, room_type=s.type)
    lt = {**room_truth(s, [largest["space_id"]], largest["area_m2"])}
    add(
        "BM-largest",
        "benchmark",
        "largest_room",
        f"Which is the largest {ty} on the {fm['full']}, and how big is it in m²?" + tail("largest"),
        "answer_room",
        lt,
        ["answer_line"],
        ["largest_room"],
    )
    add(
        "BM-largest",
        "benchmark",
        "largest_room",
        f"biggest {ty} on {fm['level']}? tell me the size too",
        "answer_room",
        lt,
        [],
        ["largest_room"],
        "level wording, no Answer line",
    )
    add(
        "BM-largest",
        "benchmark",
        "largest_room",
        f"Welcher {de_ty} im {fm['full']} ist der größte und wie viele m² hat er?",
        "answer_room",
        lt,
        [],
        ["largest_room"],
        "German",
    )
    add(
        "BM-largest",
        "benchmark",
        "largest_room",
        f"wich is the larges {ty} on flor {main['level']} and its sqm",
        "answer_room",
        lt,
        [],
        ["largest_room"],
        "typos, number as floor",
    )
    overall = max(
        (
            kinds["largest_room"].fn(bm, floor_id=f["id"], room_type=s.type)
            for f in s.floors
            if any(x["room_type"] == s.type and x["floor_id"] == f["id"] for x in s.real)
        ),
        key=lambda r: r["area_m2"],
    )
    add(
        "BM-largest",
        "benchmark",
        "largest_room",
        f"What is the biggest {ty} in the whole building?",
        "answer_room",
        room_truth(s, [overall["space_id"]], overall["area_m2"]),
        [],
        ["largest_room"],
        "missing floor: all floors",
    )

    total = kinds["floor_area_total"].fn(bm, floor_id=main_id, room_type=s.type)
    tt = number(total["total_m2"], rel=0.05)
    add(
        "BM-area",
        "benchmark",
        "floor_area_total",
        f"Facilities want the total floor area of every {ty} on the {fm['full']} added together. How many square metres is that?"
        + tail("number"),
        "answer_number",
        tt,
        ["answer_line"],
        ["floor_area_total"],
    )
    add(
        "BM-area",
        "benchmark",
        "floor_area_total",
        f"total m2 of all {ty_p} on {fm['storey']}?",
        "answer_number",
        tt,
        [],
        ["floor_area_total"],
        "storey wording, plural",
    )
    add(
        "BM-area",
        "benchmark",
        "floor_area_total",
        f"Wie groß ist die Gesamtfläche aller {de_ty}-Räume im {fm['full']}?",
        "answer_number",
        tt,
        [],
        ["floor_area_total"],
        "German",
    )
    add(
        "BM-area",
        "benchmark",
        "floor_area_total",
        f"add up the area of the {ty_p} on {fm['ordinal']} pls, in sqm",
        "answer_number",
        tt,
        [],
        ["floor_area_total"],
        "ordinal word",
    )

    if s.machine and s.c:
        asset_type = s.machine
        value = _try(
            lambda: kinds["errand"].fn(bm, start=s.a["id"], asset_type=asset_type, floor_id=other_id, room_type=s.type)
        )
        if value:
            et = number(value["length_m"], rel=0.01, tol_abs=1.0)
            at = words(asset_type)
            add(
                "BM-errand",
                "benchmark",
                "errand",
                f"I'm in {A} ({fm['full']}). I need to grab a {at} from the room that has one closest to me, then carry it to the largest {ty} on the {fo['full']}. I can carry it on the stairs. How far will I walk in total, in metres?"
                + tail("number"),
                "answer_number",
                et,
                ["answer_line"],
                ["errand"],
            )
            add(
                "BM-errand",
                "benchmark",
                "errand",
                f"start {A}, pick up a {at} from nearest room w/ one, bring it to biggest {ty} on {fo['level']}, stairs ok. total walk in m?",
                "answer_number",
                et,
                [],
                ["errand"],
                "abbreviations",
            )
            add(
                "BM-errand",
                "benchmark",
                "errand",
                f"Ich bin in {A}. Ich muss ein {at} aus dem nächsten Raum holen und zum größten {de_ty} im {fo['full']} tragen. Wie weit laufe ich insgesamt?",
                "answer_number",
                et,
                [],
                ["errand"],
                "German",
            )
            add(
                "BM-errand",
                "benchmark",
                "errand",
                f"how far do i walk: from {A}, nearest {at}, then to the largest {ty} upstairs/downstairs on {fo['number']}?",
                "answer_number",
                et,
                [],
                ["errand"],
                "vague floor words",
            )

    if entrance:
        width = _pick_width(s, entrance, top_id)
        value = _try(
            lambda: kinds["wide_delivery_count"].fn(bm, start=entrance["id"], floor_id=top_id, min_width=width)
        )
        if value is not None:
            wt = number(value["count"])
            f_top = s.floor_variants(s.top)
            add(
                "BM-wide",
                "benchmark",
                "wide_delivery_count",
                f"I'm moving a {width} m wide trolley. It can't go on stairs or steps (lifts are fine), and every door it passes through must be at least {width} m wide. It arrives through the entrance into {entrance['name']} ({s.floor_name(bm.floors[entrance['floor_id']])}). Into how many rooms on the {f_top['full']} can it be delivered?"
                + tail("number"),
                "answer_number",
                wt,
                ["answer_line"],
                ["wide_delivery_count"],
            )
            add(
                "BM-wide",
                "benchmark",
                "wide_delivery_count",
                f"{width}m wide pallet, no stairs, lifts ok, doors must be {width}m+. enters at {entrance['name']}. how many rooms on {f_top['level']} can I reach?",
                "answer_number",
                wt,
                [],
                ["wide_delivery_count"],
                "abbreviations",
            )
            add(
                "BM-wide",
                "benchmark",
                "wide_delivery_count",
                f"Eine {width} m breite Palette, keine Treppen, Türen mindestens {width} m. Eingang in {entrance['name']}. In wie viele Räume im {f_top['full']} kommt sie?",
                "answer_number",
                wt,
                [],
                ["wide_delivery_count"],
                "German",
            )
            add(
                "BM-wide",
                "benchmark",
                "wide_delivery_count",
                f"Into how many rooms on the {f_top['storey']} can a {width} m wide machine be delivered from {entrance['name']} without steps?",
                "answer_number",
                wt,
                [],
                ["wide_delivery_count"],
                "storey wording",
            )
        if s.lifts:
            lift = s.lifts[0]
            value = _try(
                lambda: kinds["step_free_reachable_count"].fn(
                    bm, closed=lift["id"], start=entrance["id"], floor_id=top_id
                )
            )
            if value is not None:
                rt = number(value["count"])
                f_top = s.floor_variants(s.top)
                ef = s.floor_name(bm.floors[entrance["floor_id"]])
                add(
                    "BM-stepfree",
                    "benchmark",
                    "step_free_reachable_count",
                    f"{lift['name']} is out of service. A wheelchair user comes in through the entrance into {entrance['name']} ({ef}). How many rooms on the {f_top['full']} can they still reach?"
                    + tail("number"),
                    "answer_number",
                    rt,
                    ["answer_line"],
                    ["step_free_reachable_count"],
                )
                add(
                    "BM-stepfree",
                    "benchmark",
                    "step_free_reachable_count",
                    f"{lift['name'].lower()} down. wheelchair enters at {entrance['name']}. rooms on {f_top['level']} still reachable?",
                    "answer_number",
                    rt,
                    [],
                    ["step_free_reachable_count"],
                    "lowercase, abbreviations",
                )
                add(
                    "BM-stepfree",
                    "benchmark",
                    "step_free_reachable_count",
                    f"Der Aufzug {lift['name']} ist außer Betrieb. Rollstuhlfahrer kommen durch den Eingang in {entrance['name']}. Wie viele Räume im {f_top['full']} erreichen sie noch?",
                    "answer_number",
                    rt,
                    [],
                    ["step_free_reachable_count"],
                    "German",
                )
                add(
                    "BM-stepfree",
                    "benchmark",
                    "step_free_reachable_count",
                    f"With {lift['name']} closed, how many rooms upstairs on {f_top['storey']} can someone in a wheelchair reach from {entrance['name']}?",
                    "answer_number",
                    rt,
                    [],
                    ["step_free_reachable_count"],
                    "paraphrase",
                )

    above = _try(lambda: kinds["room_stacked"].fn(bm, start=s.a["id"], direction="above"))
    below = _try(lambda: kinds["room_stacked"].fn(bm, start=s.a["id"], direction="below"))
    direction, found = ("above", above) if above else ("below", below)
    if found:
        word_ = "ceiling" if direction == "above" else "floor"
        stacked = room_truth(s, [found["space_id"]])
        fl = s.floor_name(main)
        add(
            "BM-stacked",
            "benchmark",
            "room_stacked",
            (
                f"There's water dripping from the ceiling in {A} ({fl}). Which room is directly above it?"
                if direction == "above"
                else f"A washing machine is leaking onto the floor of {A} ({fl}). Which room directly below it will the water reach?"
            )
            + tail("room"),
            "answer_room",
            stacked,
            ["answer_line"],
            ["room_stacked"],
        )
        add(
            "BM-stacked",
            "benchmark",
            "room_stacked",
            f"what is right {direction} {A}?",
            "answer_room",
            stacked,
            [],
            ["room_stacked"],
            "short",
        )
        add(
            "BM-stacked",
            "benchmark",
            "room_stacked",
            f"Welcher Raum liegt direkt {'über' if direction == 'above' else 'unter'} {A}?",
            "answer_room",
            stacked,
            [],
            ["room_stacked"],
            "German",
        )
        add(
            "BM-stacked",
            "benchmark",
            "room_stacked",
            f"leak in {A} on {fm['level']}, which room is on the next {'upper' if direction == 'above' else 'lower'} storey directly over/under it?",
            "answer_room",
            stacked,
            [],
            ["room_stacked"],
            "level wording",
        )
        _ = word_

    walls = kinds["shared_walls_count"].fn(bm, start=s.a["id"])
    wl = number(walls["count"])
    add(
        "BM-walls",
        "benchmark",
        "shared_walls_count",
        f"We're soundproofing {A} ({s.floor_name(main)}). How many other rooms on that floor share a wall with it? Count every room whose wall runs along it for at least 1 m, with or without a door between them; corridors, stairwells and lifts don't count."
        + tail("number"),
        "answer_number",
        wl,
        ["answer_line"],
        ["shared_walls_count"],
    )
    add(
        "BM-walls",
        "benchmark",
        "shared_walls_count",
        f"how many rooms share a wall with {A}?",
        "answer_number",
        wl,
        [],
        ["shared_walls_count"],
        "short, no floor",
    )
    add(
        "BM-walls",
        "benchmark",
        "shared_walls_count",
        f"Mit wie vielen anderen Räumen hat {A} eine gemeinsame Wand (mindestens 1 m)?",
        "answer_number",
        wl,
        [],
        ["shared_walls_count"],
        "German",
    )
    add(
        "BM-walls",
        "benchmark",
        "shared_walls_count",
        f"neighbours of {A}: number of adjacent rooms on the same {fm['storey']} touching it along a wall?",
        "answer_number",
        wl,
        [],
        ["shared_walls_count"],
        "neighbours wording",
    )

    if s.c:
        line = kinds["straight_line_3d"].fn(bm, first=s.a["id"], second=s.c["id"])
        sl = number(line["distance_m"], rel=0.02)
        add(
            "BM-line",
            "benchmark",
            "straight_line_3d",
            f"We're planning a wireless sensor link between {A} ({s.floor_name(main)}) and {C} ({s.floor_name(other)}). What is the straight-line distance in metres between the centres of the two rooms (each room's floor-plan centroid, at its floor's elevation)?"
            + tail("number"),
            "answer_number",
            sl,
            ["answer_line"],
            ["straight_line_3d"],
        )
        add(
            "BM-line",
            "benchmark",
            "straight_line_3d",
            f"distance as the crow flies between {A} and {C} in m?",
            "answer_number",
            sl,
            [],
            ["straight_line_3d"],
            "crow flies, no floors",
        )
        add(
            "BM-line",
            "benchmark",
            "straight_line_3d",
            f"Wie viele Meter Luftlinie liegen zwischen {A} und {C}?",
            "answer_number",
            sl,
            [],
            ["straight_line_3d"],
            "German",
        )
        add(
            "BM-line",
            "benchmark",
            "straight_line_3d",
            f"how far is {A} from {C} in a straight line (3D, through the ceiling)?",
            "answer_number",
            sl,
            [],
            ["straight_line_3d"],
            "3D wording",
        )

    if s.b:
        value = _try(
            lambda: kinds["what_if_door"].fn(
                bm, first=s.a["id"], second=s.b["id"], door_floor_id=main_id, floor_id=other_id
            )
        )
        if value is not None:
            wd = number(value["count"])
            f_o = fo
            add(
                "BM-door",
                "benchmark",
                "what_if_door",
                f"What if we add a door between {A} ({s.floor_name(main)}) and {B} ({s.floor_name(main)}), in the middle of the wall they share? How many rooms on the {f_o['full']} would then have a shorter walk out of the building, to their nearest entrance, by more than 1 m?"
                + tail("number"),
                "answer_number",
                wd,
                ["answer_line"],
                ["what_if_door"],
            )
            add(
                "BM-door",
                "benchmark",
                "what_if_door",
                f"new door {A} <-> {B}: on {f_o['level']}, how many rooms get a >1 m shorter way to the exit?",
                "answer_number",
                wd,
                [],
                ["what_if_door"],
                "abbreviations",
            )
            add(
                "BM-door",
                "benchmark",
                "what_if_door",
                f"Wenn wir eine Tür zwischen {A} und {B} einbauen, bei wie vielen Räumen im {f_o['full']} wird der Weg nach draußen um mehr als 1 m kürzer?",
                "answer_number",
                wd,
                [],
                ["what_if_door"],
                "German",
            )
            add(
                "BM-door",
                "benchmark",
                "what_if_door",
                f"If a door were cut through the shared wall of {A} and {B}, how many rooms on {f_o['storey']} would walk more than a metre less to leave the building?",
                "answer_number",
                wd,
                [],
                ["what_if_door"],
                "paraphrase",
            )

    # ---------------- warm-up kinds ----------------
    located_type = s.machine or s.coffee or next(iter(sorted(s.asset_counts)))
    loc_rooms = s.rooms_with(located_type)
    loc_floors = sorted({s.floor_name(bm.floors[r["floor_id"]]) for r in loc_rooms})
    lt_ = {
        "type": "rooms_any",
        "names": [r["name"] for r in loc_rooms],
        "refs": [r.get("ref") or "" for r in loc_rooms],
        "floors": loc_floors,
    }
    at = words(located_type)
    add(
        "WU-locate",
        "warmup",
        "locate",
        f"Where is the {at}?",
        "answer_room",
        lt_,
        [],
        ["find_asset", "search_building"],
    )
    add("WU-locate", "warmup", "locate", f"wo finde ich {at}?", "answer_room", lt_, [], ["find_asset"], "German")
    add(
        "WU-locate",
        "warmup",
        "locate",
        f"which floor is the {at} on, and in which room?",
        "answer_room",
        lt_,
        [],
        ["find_asset"],
        "two part",
    )
    add("WU-locate", "warmup", "locate", f"locate {at} pls", "answer_room", lt_, [], ["find_asset"], "imperative")
    count_type, count_floor = _count_slot(s)
    n = sum(1 for a in bm.assets.values() if a["type"] == count_type and a["floor_id"] == count_floor["id"])
    cf = s.floor_variants(count_floor)
    ct = number(n)
    ca = words(count_type)
    add(
        "WU-count",
        "warmup",
        "count",
        f"How many {ca} items are on the {cf['full']}?",
        "answer_number",
        ct,
        [],
        ["search_building", "find_asset"],
    )
    add(
        "WU-count",
        "warmup",
        "count",
        f"number of {plural(count_type)} on {cf['level']}",
        "answer_number",
        ct,
        [],
        ["search_building", "find_asset"],
        "level wording",
    )
    add(
        "WU-count",
        "warmup",
        "count",
        f"Wie viele {ca} gibt es im {cf['full']}?",
        "answer_number",
        ct,
        [],
        ["search_building", "find_asset"],
        "German",
    )
    add(
        "WU-count",
        "warmup",
        "count",
        f"count the {plural(count_type)} on {cf['ordinal']} for me",
        "answer_number",
        ct,
        [],
        ["search_building", "find_asset"],
        "ordinal",
    )
    if s.c:
        fa, fc = s.floor_name(main), s.floor_name(other)
        r1 = s.route_length(s.a["id"], s.c["id"])
        add(
            "WU-route",
            "warmup",
            "route",
            f"How do I get from {A} ({fa}) to {C} ({fc})?",
            "route",
            route_truth(r1, False, s.c["id"]),
            ["route_tool"],
            ["find_route"],
        )
        add(
            "WU-route",
            "warmup",
            "route",
            f"way from {A} to {C}?",
            "route",
            route_truth(r1, False, s.c["id"]),
            ["route_tool"],
            ["find_route"],
            "no floors",
        )
        add(
            "WU-route",
            "warmup",
            "route",
            f"Wie komme ich von {A} nach {C}?",
            "route",
            route_truth(r1, False, s.c["id"]),
            ["route_tool"],
            ["find_route"],
            "German",
        )
        add(
            "WU-route",
            "warmup",
            "route",
            f"route {C} from {A}, how long is the walk?",
            "route",
            route_truth(r1, False, s.c["id"]),
            ["route_tool"],
            ["find_route"],
            "terse",
        )
        r2 = s.route_length(s.a["id"], s.c["id"], step_free=True)
        add(
            "WU-stepfree",
            "warmup",
            "route_step_free",
            f"Is there a step-free route from {A} ({fa}) to {C} ({fc})?",
            "route",
            route_truth(r2, True, s.c["id"]),
            ["step_free_flag"],
            ["find_route"],
        )
        add(
            "WU-stepfree",
            "warmup",
            "route_step_free",
            f"can i get from {A} to {C} without stairs?",
            "route",
            route_truth(r2, True, s.c["id"]),
            ["step_free_flag"],
            ["find_route"],
            "lowercase",
        )
        add(
            "WU-stepfree",
            "warmup",
            "route_step_free",
            f"Gibt es einen barrierefreien Weg von {A} nach {C}?",
            "route",
            route_truth(r2, True, s.c["id"]),
            ["step_free_flag"],
            ["find_route"],
            "German",
        )
        add(
            "WU-stepfree",
            "warmup",
            "route_step_free",
            f"{A} to {C}, step free route pls",
            "route",
            route_truth(r2, True, s.c["id"]),
            ["step_free_flag"],
            ["find_route"],
            "terse",
        )
        if s.stairs or s.lifts:
            conn = s.closure or (s.stairs or s.lifts)[0]
            r3 = s.route_length(s.a["id"], s.c["id"], closed=(conn["id"],))
            ct3 = route_truth(r3, False, s.c["id"])
            add(
                "WU-closure",
                "warmup",
                "route_with_closure",
                f"{conn['name']} is closed for maintenance. How do I get from {A} ({fa}) to {C} ({fc})?",
                "route",
                ct3,
                ["route_tool", "closure_respected"],
                ["assume_closed", "find_route"],
            )
            add(
                "WU-closure",
                "warmup",
                "route_with_closure",
                f"{conn['name'].lower()} closed, route {A} to {C}?",
                "route",
                ct3,
                ["route_tool", "closure_respected"],
                ["assume_closed", "find_route"],
                "terse",
            )
            add(
                "WU-closure",
                "warmup",
                "route_with_closure",
                f"Der {conn['name']} ist wegen Wartung gesperrt. Wie komme ich von {A} nach {C}?",
                "route",
                ct3,
                ["route_tool", "closure_respected"],
                ["assume_closed", "find_route"],
                "German",
            )
            add(
                "WU-closure",
                "warmup",
                "route_with_closure",
                f"we can't use {conn['name']} today. what's the way from {A} to {C} then?",
                "route",
                ct3,
                ["route_tool", "closure_respected"],
                ["assume_closed", "find_route"],
                "colloquial",
            )
        if s.b:
            tour = _try(lambda: routing.route(bm, s.a["id"], s.c["id"], False, [s.b["id"]]).length_m)
            tt_ = route_truth(tour, False, s.c["id"])
            add(
                "WU-tour",
                "warmup",
                "tour",
                f"Starting at {A} ({fa}), visit {B} ({fa}), then {C} ({fc}) in this order. What is the route?",
                "route",
                tt_,
                ["route_tool"],
                ["find_route"],
            )
            add(
                "WU-tour",
                "warmup",
                "tour",
                f"start {A}, then {B}, then end at {C}. how far overall?",
                "route",
                tt_,
                ["route_tool"],
                ["find_route"],
                "terse",
            )
            add(
                "WU-tour",
                "warmup",
                "tour",
                f"Ich starte in {A}, will erst zu {B} und dann zu {C}. Wie lang ist der Weg?",
                "route",
                tt_,
                ["route_tool"],
                ["find_route"],
                "German",
            )
            add(
                "WU-tour",
                "warmup",
                "tour",
                f"plan a round: {A} -> {B} -> {C}, give me the total length",
                "route",
                tt_,
                ["route_tool"],
                ["find_route"],
                "arrows",
            )

    _personas(s, add, locals())
    return items


def _try(call):
    try:
        return call()
    except Exception:  # noqa: BLE001 - a slot that cannot be computed on this building is simply left out
        return None


def _pick_width(s: Slots, entrance: dict, floor_id: str) -> float:
    kind = load_kinds()["wide_delivery_count"].fn
    totals = sum(1 for sp in s.real if sp["floor_id"] == floor_id)
    for width in (1.1, 1.0, 0.9, 1.2, 1.5, 2.0):
        value = _try(lambda width=width: kind(s.bm, start=entrance["id"], floor_id=floor_id, min_width=width))
        if value is not None and 0 < value["count"] < totals:
            return width
    return 1.1


def _count_slot(s: Slots) -> tuple[str, dict]:
    best = max(
        ((a["type"], a["floor_id"]) for a in s.bm.assets.values() if a["type"] not in ("chair", "dining_chair")),
        key=lambda k: (
            sum(1 for a in s.bm.assets.values() if (a["type"], a["floor_id"]) == k) < 12,
            sum(1 for a in s.bm.assets.values() if (a["type"], a["floor_id"]) == k),
            k,
        ),
    )
    return best[0], s.bm.floors[best[1]]


def _personas(s: Slots, add, env: dict) -> None:
    from tests.catalogue.personas import add_personas

    add_personas(s, add, env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("building", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    items = build(args.building)
    lines = [json.dumps({**item, "building": args.building.name}, ensure_ascii=False) for item in items]
    if args.write:
        CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
        CATALOGUE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(items)} items for {args.building.name}")


if __name__ == "__main__":
    main()
