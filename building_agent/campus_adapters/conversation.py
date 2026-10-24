"""A campus described in conversation. The agent turns what the person said into structured entries (no LLM here).

Entries are a list of dicts, each with a `type`:
  {"type": "building", "building_id": "proc-campus-dev-000", "path"?: "data/dev/...", "origin"?: [x, y], "rotation_deg"?: 0}
  {"type": "link", "building_a": id, "entrance_a": opening id, "building_b": id, "entrance_b": opening id,
   "kind"?: "walkway" | "bridge" | "tunnel", "length_m"?: 85, "width_m"?, "step_free"?, "closed"?, "name"?, "id"?}
Buildings used in a link but not listed are looked up by id under `root` (default: data/). A saved description is a
.json file {"id"?, "name"?, "entries": [...]}."""

from pathlib import Path

from building_agent.campus import Campus
from building_agent.campus_adapters import Adapter
from building_agent.campus_adapters._common import (
    add_building,
    build_link,
    note,
    parse_number,
    parse_origin,
    read_json,
    text_of,
)


def campus_from_description(
    entries: list, root: Path | None = None, campus_id: str = "campus-conversation", name: str = "Campus"
) -> Campus:
    campus = Campus(id=campus_id, name=name)
    roots = ([Path(root)] if root else []) + [Path("data")]
    entries = entries if isinstance(entries, list) else []
    for index, entry in enumerate(entries, start=1):
        if isinstance(entry, dict) and entry.get("type") == "building" and text_of(entry.get("building_id")):
            extra = {
                "origin": parse_origin(entry.get("origin")),
                "rotation_deg": parse_number(entry.get("rotation_deg")) or 0.0,
            }
            if not add_building(campus, text_of(entry["building_id"]), roots, entry.get("path"), **extra):
                note(campus, "building_not_found", f"No building folder found for '{entry['building_id']}'.")
    link_count = 0
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or entry.get("type") != "link":
            if not (isinstance(entry, dict) and entry.get("type") == "building"):
                note(campus, "entry_unreadable", f"Entry {index} is neither a building nor a link and was skipped.")
            continue
        link_count += 1
        raw = dict(entry)
        raw["from_building"], raw["from_entrance"] = entry.get("building_a"), entry.get("entrance_a")
        raw["to_building"], raw["to_entrance"] = entry.get("building_b"), entry.get("entrance_b")
        for building_id in (text_of(raw["from_building"]), text_of(raw["to_building"])):
            if building_id:
                add_building(campus, building_id, roots)
        campus.links.append(build_link(raw, link_count, campus.load_findings))
    return campus


def detect(path: Path) -> bool:
    data = read_json(path)
    return isinstance(data, dict) and isinstance(data.get("entries"), list) and "links" not in data


def load(path: Path, root: Path | None = None) -> Campus:
    data = read_json(path) or {}
    return campus_from_description(
        data.get("entries", []),
        root=root or path.parent,
        campus_id=text_of(data.get("id")) or path.stem,
        name=text_of(data.get("name")) or path.stem,
    )


ADAPTER = Adapter(
    name="conversation",
    detect=detect,
    load=load,
    description=(
        "a .json file {'entries': [...]} saved from a conversation, with entries of type 'building' (building_id) "
        "and type 'link' (building_a, entrance_a, building_b, entrance_b, kind, length_m)."
    ),
)
