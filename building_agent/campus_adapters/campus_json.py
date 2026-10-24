"""Our own format: campus.json with `buildings` and `links` (see docs/specs/level3-campus.md)."""

from pathlib import Path

from building_agent.campus import Campus, CampusBuilding
from building_agent.campus_adapters import Adapter
from building_agent.campus_adapters._common import (
    add_building,
    build_link,
    note,
    parse_number,
    parse_origin,
    read_json,
    search_roots,
    text_of,
)


def detect(path: Path) -> bool:
    data = read_json(path)
    return isinstance(data, dict) and isinstance(data.get("buildings"), list) and isinstance(data.get("links"), list)


def _endpoint(link: dict, side: str) -> tuple[str, str]:
    value = link.get(side)
    if isinstance(value, dict):
        return text_of(value.get("building_id", value.get("building"))), text_of(value.get("entrance"))
    return text_of(link.get(f"{side}_building")), text_of(link.get(f"{side}_entrance"))


def load(path: Path, root: Path | None = None) -> Campus:
    data = read_json(path) or {}
    campus = Campus(id=text_of(data.get("id")) or path.stem, name=text_of(data.get("name")) or path.stem)
    roots = search_roots(path, root)
    for index, entry in enumerate(data.get("buildings", []), start=1):
        if not isinstance(entry, dict) or not text_of(entry.get("building_id", entry.get("id"))):
            note(campus, "building_unreadable_entry", f"Building entry {index} has no building_id and was skipped.")
            continue
        building_id = text_of(entry.get("building_id", entry.get("id")))
        if campus.building(building_id) is not None:
            campus.buildings.append(CampusBuilding(building_id, campus.building(building_id).path))
            continue
        rotation = parse_number(entry.get("rotation_deg"))
        extra = {"origin": parse_origin(entry.get("origin")), "rotation_deg": rotation or 0.0}
        if not add_building(campus, building_id, roots, entry.get("path"), **extra):
            campus.buildings.append(CampusBuilding(building_id, None, **extra))
    for index, entry in enumerate(data.get("links", []), start=1):
        if not isinstance(entry, dict):
            note(campus, "link_unreadable_entry", f"Link entry {index} is not an object and was skipped.")
            continue
        raw = dict(entry)
        raw["from_building"], raw["from_entrance"] = _endpoint(entry, "from")
        raw["to_building"], raw["to_entrance"] = _endpoint(entry, "to")
        campus.links.append(build_link(raw, index, campus.load_findings))
    return campus


ADAPTER = Adapter(
    name="campus_json",
    detect=detect,
    load=load,
    description=(
        "a .json file with a 'buildings' list (building_id, path, origin, rotation_deg) and a 'links' list "
        "(id, kind, from {building_id, entrance}, to {building_id, entrance}, length_m, width_m, step_free, closed)."
    ),
)
