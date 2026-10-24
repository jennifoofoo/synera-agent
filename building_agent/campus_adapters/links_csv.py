"""A table of links, one row per link (CSV from Excel, Sheets or a text editor). Buildings are found by id or folder name."""

from pathlib import Path

from building_agent.campus import Campus
from building_agent.campus_adapters import Adapter
from building_agent.campus_adapters._common import (
    add_building,
    build_link,
    cell,
    find_header,
    note,
    read_rows,
    search_roots,
)

SYNONYMS = {
    "building_a": ("from_building", "from", "building_from", "von", "source_building", "building_1", "start_building"),
    "entrance_a": ("from_entrance", "entrance_from", "from_door", "entrance_1", "start_entrance", "von_eingang"),
    "building_b": ("to_building", "to", "nach", "building_to", "target_building", "building_2", "end_building"),
    "entrance_b": ("to_entrance", "entrance_to", "to_door", "entrance_2", "end_entrance", "nach_eingang"),
    "kind": ("type", "link_type", "art", "typ"),
    "length_m": ("length", "distance", "dist", "distance_m", "dist_m", "laenge", "laenge_m", "length_meters"),
    "width_m": ("width", "breite"),
    "step_free": ("stepfree", "stufenfrei", "accessible", "barrier_free"),
    "closed": ("gesperrt", "blocked"),
    "id": ("link_id",),
    "name": ("label", "bezeichnung"),
    "level_delta": ("levels", "floor_delta"),
    "length_estimated": ("estimated",),
}
REQUIRED = ("building_a", "entrance_a", "building_b", "entrance_b")


def _header(path: Path):
    rows = read_rows(path)
    if not rows:
        return None
    found = find_header(rows, SYNONYMS, REQUIRED)
    return None if found is None else (rows, *found)


def detect(path: Path) -> bool:
    return _header(path) is not None


def load(path: Path, root: Path | None = None) -> Campus:
    rows, header_index, columns = _header(path)
    campus = Campus(id=path.stem, name=path.stem)
    roots = search_roots(path, root)
    for index, row in enumerate(rows[header_index + 1 :], start=1):
        raw = {
            "id": cell(row, columns, "id"),
            "name": cell(row, columns, "name"),
            "kind": cell(row, columns, "kind"),
            "from_building": cell(row, columns, "building_a"),
            "from_entrance": cell(row, columns, "entrance_a"),
            "to_building": cell(row, columns, "building_b"),
            "to_entrance": cell(row, columns, "entrance_b"),
            "length_m": cell(row, columns, "length_m"),
            "width_m": cell(row, columns, "width_m"),
            "step_free": cell(row, columns, "step_free") or None,
            "closed": cell(row, columns, "closed") or None,
            "level_delta": cell(row, columns, "level_delta"),
            "length_estimated": cell(row, columns, "length_estimated") or None,
        }
        if not raw["from_building"] and not raw["to_building"]:
            note(campus, "row_empty", f"Row {index} names no buildings and was skipped.")
            continue
        for building_id in (raw["from_building"], raw["to_building"]):
            if building_id:
                add_building(campus, building_id, roots)
        campus.links.append(build_link(raw, index, campus.load_findings))
    return campus


ADAPTER = Adapter(
    name="links_csv",
    detect=detect,
    load=load,
    description=(
        "a CSV table (comma, semicolon or tab separated, decimal comma allowed) with one row per link and the columns "
        "building_a, entrance_a, building_b, entrance_b, and optionally kind, length_m, width_m, step_free, closed "
        "(also accepted: from/to, from_building/to_building, type, length, distance, dist)."
    ),
)
