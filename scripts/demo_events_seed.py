"""Seed today's hackathon events and room bookings for the demo building (Munich Urban Colab, plan-89323a15), so Wanda
can answer "Where are the pitches?" or "Is the Project Room free at 10:00?" (docs/specs/events.md).

    uv run python scripts/demo_events_seed.py [building_dir] [--root agent_output/knowledge]

Dates are relative to today (Europe/Berlin). Idempotent: an event with the same title and start is skipped. Events
never change routes. Demo data only, never for benchmark buildings.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from building_agent.agent import KNOWLEDGE_ROOT
from building_agent.knowledge import KnowledgeStore, berlin_now, parse_time
from starter_agent.building_map import BuildingMap

DEFAULT_BUILDING = Path("agent_output") / "buildings" / "plan-89323a15"

# (title, rooms (first = anchor), start (days from today, hour, minute), end (days, hour, minute), organiser)
EVENTS = [
    ("Manage & More × UVC × Anthropic Hackathon", ["Foyer", "Seminar Rooms 1-3"], (-1, 9, 0), (0, 18, 0), None),
    ("Code freeze", ["Foyer"], (0, 13, 0), (0, 13, 15), None),
    ("Pitches", ["Auditorium (Arena)"], (0, 14, 0), (0, 16, 0), None),
    ("Lunch", ["Café (Gastraum)"], (0, 12, 30), (0, 13, 30), None),
    ("Project Room booked: Team Synera", ["Project Room"], (0, 9, 0), (0, 12, 0), "Leonie"),
    ("Projektraum West booked: Jury prep", ["Projektraum West"], (0, 13, 0), (0, 14, 0), None),
]


def room_id(bm: BuildingMap, name: str) -> str:
    found = [space["id"] for space in bm.spaces.values() if space["name"] == name]
    if not found:
        raise SystemExit(f"No room named {name!r} in this building.")
    return found[0]


def at_day(today: datetime, days: int, hour: int, minute: int) -> datetime:
    return (today + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def seed_events(bm: BuildingMap, store: KnowledgeStore, now: datetime | None = None, quiet: bool = False) -> int:
    """Add the demo events around `now` (default: the real time). Returns how many were added."""
    current = berlin_now(now)
    today = current.replace(hour=0, minute=0, second=0, microsecond=0)
    known = {
        (fact.text, parse_time(fact.valid_from))
        for fact in store.query(bm, status="all", at=current)
        if fact.kind == "event"
    }
    added = 0
    for title, rooms, start, end, organiser in EVENTS:
        begins, ends = at_day(today, *start), at_day(today, *end)
        if (title, parse_time(begins)) in known:
            continue
        ids = [room_id(bm, name) for name in rooms]
        store.add(
            bm,
            kind="event",
            anchor={"space_id": ids[0]},
            related=ids[1:],
            text=title,
            valid_from=begins,
            valid_to=ends,
            author=organiser,
            now=current,
        )
        added += 1
        if not quiet:
            print(f"{begins:%a %d.%m %H:%M} to {ends:%H:%M}  {', '.join(rooms):34}  {title}")
    if not quiet:
        print(f"{added} events added, {len(EVENTS) - added} already there ({bm.data['building']['id']}).")
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("building_dir", type=Path, nargs="?", default=DEFAULT_BUILDING)
    parser.add_argument("--root", type=Path, default=KNOWLEDGE_ROOT)
    arguments = parser.parse_args()
    seed_events(BuildingMap.load(arguments.building_dir), KnowledgeStore(arguments.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
