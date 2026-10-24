"""Latitude and longitude per building. Links are made between close buildings, lengths are estimates (haversine x 1.2).

JSON: {"buildings": [{"building_id", "lat", "lon", "entrance"?}], "pairs"?: [[a, b]], "max_distance_m"?: 300}
or a plain list of such buildings. CSV: columns building_id, lat, lon (optional entrance)."""

import math
from pathlib import Path

from building_agent.campus import ESTIMATE_FACTOR, Campus, building_center, entrances, load_building_map
from building_agent.campus_adapters import Adapter
from building_agent.campus_adapters._common import (
    add_building,
    build_link,
    cell,
    find_header,
    note,
    parse_number,
    read_json,
    read_rows,
    search_roots,
    text_of,
)

DEFAULT_MAX_DISTANCE_M = 300.0
EARTH_RADIUS_M = 6_371_000.0
SYNONYMS = {
    "building_id": ("building", "id", "building_name", "gebaeude"),
    "lat": ("latitude", "breite", "breitengrad"),
    "lon": ("lng", "long", "longitude", "laenge", "laengengrad"),
    "entrance": ("entrance_id", "eingang"),
}
REQUIRED = ("building_id", "lat", "lon")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((phi2 - phi1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _offset(lat: float, lon: float, dx: float, dy: float) -> tuple[float, float]:
    return (
        lat + math.degrees(dy / EARTH_RADIUS_M),
        lon + math.degrees(dx / (EARTH_RADIUS_M * max(math.cos(math.radians(lat)), 1e-6))),
    )


def _read(path: Path) -> tuple[list[dict], dict] | None:
    """(building rows with building_id, lat, lon, entrance; options) or None if this is not a geo file."""
    data = read_json(path)
    if data is not None:
        options = data if isinstance(data, dict) else {}
        items = options.get("buildings") if isinstance(data, dict) else data
        if isinstance(data, dict) and "links" in data:
            return None
        if not isinstance(items, list) or not items:
            return None
        rows = [
            {
                "building_id": text_of(item.get("building_id", item.get("id"))),
                "lat": item.get("lat", item.get("latitude")),
                "lon": item.get("lon", item.get("lng", item.get("longitude"))),
                "entrance": text_of(item.get("entrance")),
            }
            for item in items
            if isinstance(item, dict)
        ]
        if not rows or not all(row["lat"] is not None and row["lon"] is not None for row in rows):
            return None
        return rows, options
    table = read_rows(path)
    if not table:
        return None
    found = find_header(table, SYNONYMS, REQUIRED)
    if found is None:
        return None
    header_index, columns = found
    rows = [
        {name: cell(row, columns, name) for name in ("building_id", "lat", "lon", "entrance")}
        for row in table[header_index + 1 :]
    ]
    return rows, {}


def detect(path: Path) -> bool:
    return _read(path) is not None


def load(
    path: Path, root: Path | None = None, max_distance_m: float | None = None, pairs: list | None = None
) -> Campus:
    rows, options = _read(path) or ([], {})
    limit = max_distance_m or parse_number(options.get("max_distance_m")) or DEFAULT_MAX_DISTANCE_M
    listed = pairs if pairs is not None else options.get("pairs")
    listed_pairs = {
        frozenset(map(text_of, pair)) for pair in (listed or []) if isinstance(pair, list | tuple) and len(pair) == 2
    }
    campus = Campus(id=path.stem, name=path.stem)
    roots = search_roots(path, root)
    places: dict[str, dict] = {}
    for row in rows:
        lat, lon = parse_number(row["lat"]), parse_number(row["lon"])
        building_id = text_of(row["building_id"])
        if not building_id or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            note(campus, "geo_coordinates_unreadable", f"The position of building '{building_id}' could not be read.")
            continue
        if building_id in places:
            continue
        if not add_building(campus, building_id, roots):
            note(campus, "geo_building_not_found", f"No building folder found for '{building_id}'.", [building_id])
            continue
        building = campus.building(building_id)
        building_map, _ = load_building_map(building)
        places[building_id] = {"lat": lat, "lon": lon, "pinned": text_of(row["entrance"]), "map": building_map}
    origin_lat, origin_lon = next(((p["lat"], p["lon"]) for p in places.values()), (0.0, 0.0))
    for building_id, place in places.items():
        north = haversine_m(origin_lat, origin_lon, place["lat"], origin_lon)
        east = haversine_m(origin_lat, origin_lon, origin_lat, place["lon"])
        building = campus.building(building_id)
        building.origin = (
            round(math.copysign(east, place["lon"] - origin_lon), 1),
            round(math.copysign(north, place["lat"] - origin_lat), 1),
        )

    ids = list(places)
    for i, first in enumerate(ids):
        for second in ids[i + 1 :]:
            a, b = places[first], places[second]
            distance = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            if distance > limit and frozenset((first, second)) not in listed_pairs:
                continue
            best = _nearest_entrances(a, b)
            if best is None:
                note(
                    campus,
                    "geo_no_entrance",
                    f"No entrance pair found between '{first}' and '{second}'.",
                    [first, second],
                )
                continue
            raw = {
                "from_building": first,
                "from_entrance": best[0],
                "to_building": second,
                "to_entrance": best[1],
                "length_m": max(round(best[2] * ESTIMATE_FACTOR, 1), 0.1),
                "length_estimated": True,
            }
            campus.links.append(build_link(raw, len(campus.links) + 1, campus.load_findings))
    return campus


def _entrance_points(place: dict) -> list[tuple[str, float, float]]:
    building_map = place["map"]
    if building_map is None:
        return []
    center_x, center_y = building_center(building_map)
    points = []
    for item in entrances(building_map):
        if place["pinned"] and item["id"] != place["pinned"]:
            continue
        lat, lon = _offset(place["lat"], place["lon"], item["position"][0] - center_x, item["position"][1] - center_y)
        points.append((item["id"], lat, lon))
    return points


def _nearest_entrances(a: dict, b: dict) -> tuple[str, str, float] | None:
    best = None
    for id_a, lat_a, lon_a in _entrance_points(a):
        for id_b, lat_b, lon_b in _entrance_points(b):
            distance = haversine_m(lat_a, lon_a, lat_b, lon_b)
            if best is None or (distance, id_a, id_b) < (best[2], best[0], best[1]):
                best = (id_a, id_b, distance)
    return best


ADAPTER = Adapter(
    name="geo",
    detect=detect,
    load=load,
    description=(
        "a JSON or CSV file with building_id, lat and lon per building (JSON may add 'pairs' and 'max_distance_m'). "
        "Buildings closer than 300 m get a link; lengths are estimated as straight line times 1.2."
    ),
)
