"""Level 4 stair hall doors: plans such as Swiss Dwellings do not draw the door between an apartment and its stair hall.

For every group of rooms that has no way out and no stair hall of its own, propose one door to a neighbouring stair
hall on their longest shared wall. Deterministic, no API, never edits input. Returns `Suggestion`s, so
`apply_suggestions` and `describe_suggestions` from suggest.py work on them."""

import re
from collections import defaultdict

from building_agent.level4.suggest import (
    HUB_ROOM_TYPES,
    HUB_TYPES,
    MIN_WALL_M,
    VERTICAL_ROOM_TYPES,
    VERTICAL_TYPES,
    WALL_CAP_M,
    WALL_WEIGHT,
    WET_ROOM_TYPES,
    Suggestion,
    _candidates,
    _groups,
    _has_door,
    _polygon,
    apply_suggestions,
    suggest_doors,
)
from building_agent.level4.validate import room_label
from starter_agent.building_map import OUTSIDE

STAIR_NAME = re.compile(r"treppe|stair|landing|aufzug|elevator|\blift\b|hall access|stair ?hall", re.IGNORECASE)
HALL_BONUS = 2.0
PURE_VERTICAL_PENALTY = 3.0
CLUSTER_HUB_BONUS = 1.5
CLUSTER_WET_PENALTY = 2.0
CLUSTER_OUTDOOR_PENALTY = 3.0
MAX_DOORS_PER_HALL = 3
LIVING_BONUS = 0.7
REFERENCE_BONUS = 1.0
CORRIDOR_FALLBACK = 0.0


def is_stair_hall(space: dict) -> bool:
    if space.get("type") in VERTICAL_TYPES or space.get("room_type") in VERTICAL_ROOM_TYPES:
        return True
    return any(STAIR_NAME.search(str(space.get(key) or "")) for key in ("name", "ref"))


def _hall_bonus(hall: dict) -> float:
    pure = hall.get("type") in VERTICAL_TYPES or hall.get("room_type") == "lift"
    hub = hall.get("type") in HUB_TYPES or hall.get("room_type") in HUB_ROOM_TYPES
    return HALL_BONUS if hub and not pure else (-PURE_VERTICAL_PENALTY if pure else 0.0)


def _side_score(room: dict) -> float:
    if room.get("type") == "outdoor" or room.get("room_type") == "balcony":
        return -CLUSTER_OUTDOOR_PENALTY
    if room.get("room_type") in WET_ROOM_TYPES:
        return -CLUSTER_WET_PENALTY
    if room.get("type") in HUB_TYPES or room.get("room_type") in HUB_ROOM_TYPES:
        return CLUSTER_HUB_BONUS
    return LIVING_BONUS if room.get("room_type") == "living_room" else 0.0


def _is_hub(space: dict) -> bool:
    return space.get("type") in HUB_TYPES or space.get("room_type") in HUB_ROOM_TYPES


def suggest_stair_doors(building: dict, max_suggestions: int = 20) -> list[Suggestion]:
    """Doors between isolated rooms and a stair hall (or, failing that, a corridor), best first.

    Tier 1 is a door between a stair hall and a room that is not one. Tier 2 is a door between a corridor or hall and
    any other room (or between two stair halls). Every room group without a way out gets at most one door, and every
    stair hall at most MAX_DOORS_PER_HALL."""
    try:
        spaces = [space for space in building["spaces"] if _polygon(space) is not None]
        ids = {space["id"] for space in spaces}
        by_id = {space["id"]: space for space in spaces}
        halls = {space["id"] for space in spaces if is_stair_hall(space)}
        if not halls:
            return []
        groups = _groups(building, ids, [])
        members: dict[str, list[str]] = defaultdict(list)
        for space_id in sorted(ids):
            members[groups.find(space_id)].append(space_id)
        has_entrance = OUTSIDE in groups.parent and any(
            OUTSIDE in (o.get("space_ids") or []) for o in building.get("openings") or []
        )
        if has_entrance:
            reference = groups.find(OUTSIDE)
        else:
            reference = max(members, key=lambda root: (len(members[root]), root), default=None)
        scored = []
        for pair in _candidates(spaces).values():
            first, second = by_id[pair.first], by_id[pair.second]
            roots = (groups.find(pair.first), groups.find(pair.second))
            if roots[0] == roots[1] or pair.wall < MIN_WALL_M or _has_door(building, pair.first, pair.second):
                continue
            hall_ends = [end for end in (pair.first, pair.second) if end in halls]
            hub_ends = [end for end in (pair.first, pair.second) if end not in halls and _is_hub(by_id[end])]
            if not hall_ends and not hub_ends:
                continue
            tier = 1 if len(hall_ends) == 1 else 2
            if tier == 2 and not CORRIDOR_FALLBACK:
                continue
            score = WALL_WEIGHT * min(pair.wall, WALL_CAP_M)
            for end in (pair.first, pair.second):
                space = by_id[end]
                score += _hall_bonus(space) if end in halls else _side_score(space)
            if reference in roots:
                score += REFERENCE_BONUS
            scored.append((tier, -score, -pair.wall, pair.first, pair.second, pair, score, hall_ends))
        scored.sort(key=lambda item: item[:5])
        used_roots: set[str] = set()
        per_hall: dict[str, int] = defaultdict(int)
        chosen = []
        for _, _, _, room, hall, pair, score, hall_ends in scored:
            roots = {groups.find(room), groups.find(hall)}
            if len(chosen) >= max_suggestions or (roots - {reference}) & used_roots:
                continue
            if any(per_hall[end] >= MAX_DOORS_PER_HALL for end in hall_ends):
                continue
            used_roots |= roots - {reference}
            for end in hall_ends:
                per_hall[end] += 1
            chosen.append((room, hall, pair, score))
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    result = []
    for room, hall, pair, score in chosen:
        first, second = by_id[room], by_id[hall]
        result.append(
            Suggestion(
                room,
                hall,
                room_label(first),
                room_label(second),
                first["floor_id"],
                pair.position,
                pair.wall,
                round(score, 3),
                f"{pair.wall:.1f} m of shared wall with the stair hall",
            )
        )
    return result


def suggest_stairs_then_generic(building: dict) -> tuple[list[Suggestion], list[Suggestion]]:
    """Stair hall doors first, then the generic suggestions for whatever is still isolated after them."""
    stairs = suggest_stair_doors(building)
    return stairs, suggest_doors(apply_suggestions(building, stairs) if stairs else building)


def describe_stair_doors(suggestions: list[Suggestion], max_items: int = 8) -> str:
    """Plain-words proposal for the card, empty when there is nothing to propose."""
    if not suggestions:
        return ""
    shown = ", ".join(f"{s.first_ref} to {s.second_ref}" for s in suggestions[:max_items])
    more = f", and {len(suggestions) - max_items} more" if len(suggestions) > max_items else ""
    return (
        "These apartments have no door to the stair hall in the plan (it is usually not drawn). "
        f"I suggest: {shown}{more}. Say yes to add them."
    )
