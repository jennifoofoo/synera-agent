"""Input generators for the robustness sweep: one per kind, built only from a building's own data."""

import inspect
import random
from collections.abc import Callable

from starter_agent.building_map import BuildingMap

PER_KIND = 6
WIDTHS = (0.0, 0.8, 1.0, 1.1, 1.5, 5.0)
DIRECTIONS = ("above", "below")


class Pools:
    def __init__(self, bm: BuildingMap, seed: str) -> None:
        self.bm = bm
        self.rng = random.Random(seed)
        self.floors = sorted(bm.floors)
        self.spaces = sorted(bm.spaces)
        self.by_floor: dict[str, list[str]] = {}
        for space_id in self.spaces:
            self.by_floor.setdefault(bm.spaces[space_id]["floor_id"], []).append(space_id)
        self.room_types = sorted({space["room_type"] for space in bm.spaces.values()})
        self.asset_types = sorted({asset["type"] for asset in bm.assets.values()})
        levels = sorted(bm.floors.values(), key=lambda floor: floor["level"])
        self.extreme_floors = [levels[0]["id"], levels[-1]["id"]] if levels else []

    def floor_id(self) -> str:
        pool = self.extreme_floors if self.rng.random() < 0.4 else self.floors
        return self.rng.choice(pool)

    def room_type(self, floor_id: str) -> str:
        types = sorted({self.bm.spaces[s]["room_type"] for s in self.by_floor.get(floor_id, [])})
        if types and self.rng.random() < 0.85:
            return self.rng.choice(types)
        return self.rng.choice([*self.room_types, "no_such_type"])

    def asset_type(self) -> str:
        if self.asset_types and self.rng.random() < 0.9:
            return self.rng.choice(self.asset_types)
        return "no_such_asset"

    def space(self, floor_id: str | None = None) -> str:
        pool = self.by_floor.get(floor_id) if floor_id else None
        return self.rng.choice(pool or self.spaces)

    def adjacent_pair(self) -> tuple[str, str]:
        pairs = [
            tuple(opening["space_ids"])
            for opening in self.bm.openings.values()
            if len(opening["space_ids"]) == 2 and all(s in self.bm.spaces for s in opening["space_ids"])
        ]
        if pairs and self.rng.random() < 0.7:
            return self.rng.choice(pairs)
        floor_id = self.floor_id()
        return self.space(floor_id), self.space(floor_id)


def _start_only(pools: Pools) -> list[dict]:
    return [{"start": pools.space()} for _ in range(PER_KIND)]


def _floor_room(pools: Pools) -> list[dict]:
    out = []
    for _ in range(PER_KIND):
        floor_id = pools.floor_id()
        out.append({"floor_id": floor_id, "room_type": pools.room_type(floor_id)})
    return out


def _errand(pools: Pools) -> list[dict]:
    out = []
    for _ in range(PER_KIND):
        floor_id = pools.floor_id()
        out.append(
            {
                "start": pools.space(),
                "asset_type": pools.asset_type(),
                "floor_id": floor_id,
                "room_type": pools.room_type(floor_id),
            }
        )
    return out


def _room_stacked(pools: Pools) -> list[dict]:
    return [{"start": pools.space(), "direction": DIRECTIONS[i % 2]} for i in range(PER_KIND)]


def _straight_line(pools: Pools) -> list[dict]:
    out = [{"first": pools.space(), "second": pools.space()} for _ in range(PER_KIND - 1)]
    same = pools.space()
    return [*out, {"first": same, "second": same}]


def _what_if_door(pools: Pools) -> list[dict]:
    out = []
    for _ in range(PER_KIND):
        first, second = pools.adjacent_pair()
        out.append(
            {
                "first": first,
                "second": second,
                "door_floor_id": pools.bm.spaces[first]["floor_id"],
                "floor_id": pools.floor_id(),
            }
        )
    return out


def _wide_delivery(pools: Pools) -> list[dict]:
    out = []
    for i in range(PER_KIND):
        floor_id = pools.floor_id()
        out.append({"start": pools.space(floor_id), "floor_id": floor_id, "min_width": WIDTHS[i % len(WIDTHS)]})
    return out


def _step_free(pools: Pools) -> list[dict]:
    connectors = sorted(pools.bm.connectors) or [pools.space()]
    return [
        {"closed": pools.rng.choice(connectors), "start": pools.space(), "floor_id": pools.floor_id()}
        for _ in range(PER_KIND)
    ]


GENERATORS: dict[str, Callable[[Pools], list[dict]]] = {
    "errand": _errand,
    "floor_area_total": _floor_room,
    "largest_room": _floor_room,
    "room_stacked": _room_stacked,
    "step_free_reachable_count": _step_free,
    "shared_walls_count": _start_only,
    "straight_line_3d": _straight_line,
    "what_if_door": _what_if_door,
    "wide_delivery_count": _wide_delivery,
}


def known_params(fn: Callable) -> set[str]:
    return {name for name in inspect.signature(fn).parameters if name != "bm"}


def build_inputs(kind_name: str, pools: Pools) -> list[dict]:
    return GENERATORS[kind_name](pools)
