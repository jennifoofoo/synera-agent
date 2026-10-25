"""Seed a small, believable history of place notes for the demo building, so the knowledge graph and its time
slider have something to show (several people, places and days, some notes already ended, one ending tomorrow).

    uv run python scripts/demo_knowledge_seed.py [building_dir] [--root agent_output/knowledge]

Writes straight into the knowledge store the page and the chat read (agent_output/knowledge), with real past
timestamps, which the facts API cannot do (it stamps "now"). Idempotent: a note whose text is already stored for the
building is skipped. No closures: they would change routes in the demo. Demo data only, never for benchmark buildings.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from building_agent.agent import KNOWLEDGE_ROOT
from building_agent.knowledge import KnowledgeStore, berlin_now
from starter_agent.building_map import BuildingMap

DEFAULT_BUILDING = Path("agent_output") / "buildings" / "plan-89323a15"

# (days ago, hour, place (room or device name), kind, text, author, ends in days (None = open), resolved after hours)
STORY = [
    (6, 7, "Fire extinguisher 0.07", "note", "Checked, seal intact, next inspection in March.", "Marta", None, None),
    (5, 16, "Foyer", "issue", "Delivery pallets block the side entrance.", "Jonas", None, 20),
    (4, 9, "Fire alarm call point 0.04", "issue", "Cover cracked, still works.", "Marta", None, None),
    (0, 5, "Fire extinguisher 3.02", "issue", "Bracket is loose, always check it first.", "Night shift", None, None),
    (3, 11, "Café", "note", "Coffee machine descaled, takes 10 minutes to heat up.", "Ali", None, None),
    (
        2,
        14,
        "Lift",
        "issue",
        "Lift out of order until tomorrow, technician booked. Use the Main Stairs.",
        "Jonas",
        1,
        None,
    ),
    (1, 8, "Project Room", "note", "Beamer remote is in the drawer under the window.", "Ali", None, None),
    (1, 17, "Defibrillator 0.01", "note", "Pads replaced, expiry 2028.", "Marta", None, None),
    (0, 7, "Kitchenette", "issue", "Dishwasher leaks a little, towel under it.", "Night shift", 2, None),
    (0, 9, "Seminar Rooms 1-3", "note", "Partition wall between rooms 2 and 3 stays open this week.", "Ali", 5, None),
]


def anchor_for(bm: BuildingMap, place: str) -> dict:
    for asset in bm.assets.values():
        if asset["name"] == place:
            return {"asset_id": asset["id"]}
    for space in bm.spaces.values():
        if space["name"] == place:
            return {"space_id": space["id"]}
    raise SystemExit(f"No room or device named {place!r} in this building.")


def seed(building_dir: Path, root: Path) -> int:
    bm = BuildingMap.load(building_dir)
    store = KnowledgeStore(root)
    known = {fact.text for fact in store.query(bm, history=True, at=berlin_now() + timedelta(days=30))}
    today = berlin_now().replace(minute=0, second=0, microsecond=0)
    added = 0
    for days_ago, hour, place, kind, text, author, ends_in, resolved_after in STORY:
        if text in known:
            continue
        when = (today - timedelta(days=days_ago)).replace(hour=hour)
        if when > berlin_now():
            when = berlin_now() - timedelta(minutes=30)
        valid_to = (berlin_now() + timedelta(days=ends_in)).isoformat() if ends_in else None
        fact = store.add(bm, kind=kind, anchor=anchor_for(bm, place), text=text, author=author, valid_to=None, now=when)
        if valid_to:  # valid_to must lie after creation; set it on the stored fact (the store has no update call)
            facts = store.load(bm)
            for stored in facts:
                if stored.id == fact.id:
                    stored.valid_to = valid_to
            store.save(bm, facts)
        if resolved_after:
            store.resolve(bm, fact.id, text="cleared", author=author, now=when + timedelta(hours=resolved_after))
        added += 1
        print(f"{when:%a %d.%m %H:%M}  {kind:5}  {place:28}  {author:11}  {text}")
    print(f"{added} notes added, {len(STORY) - added} already there ({building_dir.name}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("building_dir", type=Path, nargs="?", default=DEFAULT_BUILDING)
    parser.add_argument("--root", type=Path, default=KNOWLEDGE_ROOT)
    arguments = parser.parse_args()
    return seed(arguments.building_dir, arguments.root)


if __name__ == "__main__":
    sys.exit(main())
