"""Level 3, internal campus structure: buildings, links between their entrances, validation in plain sentences.

Adapters (building_agent/campus_adapters/) turn any input into a `Campus`; routing and tools only know this structure.
Bad data never raises: it comes back as findings. Only unusable input raises `CampusError`."""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from building_agent.level4.schema import Finding, Findings
from starter_agent.building_map import OUTSIDE, BuildingMap

LINK_KINDS = ("walkway", "bridge", "tunnel")
ESTIMATE_FACTOR = 1.2
VERY_LONG_LINK_M = 5000.0
DEFAULT_ROOTS = (Path("data"),)


class CampusError(ValueError):
    """The input cannot be used at all (missing file, nothing to read)."""


class UnknownCampusFormat(CampusError):
    """No adapter recognises the file. The message says what each adapter expects, so the agent can ask."""


@dataclass
class CampusBuilding:
    building_id: str
    path: Path | None = None
    origin: tuple[float, float] | None = None
    rotation_deg: float = 0.0


@dataclass(kw_only=True)
class Link:
    id: str
    kind: str = "walkway"
    name: str = ""
    from_building: str
    from_entrance: str
    to_building: str
    to_entrance: str
    length_m: float | None = None
    length_estimated: bool = False
    width_m: float | None = None
    step_free: bool = True
    closed: bool = False
    level_delta: int = 0


@dataclass
class Campus:
    id: str
    name: str
    buildings: list[CampusBuilding] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    # Problems found while reading the input (skipped rows, unreadable numbers). Not part of equality.
    load_findings: list[Finding] = field(default_factory=list, compare=False, repr=False)

    def building(self, building_id: str) -> CampusBuilding | None:
        return next((item for item in self.buildings if item.building_id == building_id), None)

    def to_dict(self) -> dict:
        buildings = []
        for item in self.buildings:
            entry: dict = {"building_id": item.building_id, "path": str(item.path) if item.path else None}
            if item.origin is not None:
                entry["origin"] = list(item.origin)
            entry["rotation_deg"] = item.rotation_deg
            buildings.append(entry)
        links = [
            {
                "id": link.id,
                "kind": link.kind,
                "name": link.name,
                "from": {"building_id": link.from_building, "entrance": link.from_entrance},
                "to": {"building_id": link.to_building, "entrance": link.to_entrance},
                "length_m": link.length_m,
                "length_estimated": link.length_estimated,
                "width_m": link.width_m,
                "step_free": link.step_free,
                "closed": link.closed,
                "level_delta": link.level_delta,
            }
            for link in self.links
        ]
        return {"id": self.id, "name": self.name, "buildings": buildings, "links": links}


def save_campus(campus: Campus, path: Path) -> None:
    Path(path).write_text(json.dumps(campus.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- building helpers ----------


def entrances(building_map: BuildingMap) -> list[dict]:
    """Entrance openings (those with 'outside' on one side), with the room behind them."""
    found = []
    for opening in building_map.openings.values():
        space_ids = opening.get("space_ids", [])
        if OUTSIDE not in space_ids:
            continue
        inside = [space_id for space_id in space_ids if space_id != OUTSIDE]
        space = building_map.spaces.get(inside[0]) if inside else None
        found.append(
            {
                "id": opening["id"],
                "room": space["name"] if space else "",
                "space_id": inside[0] if inside else "",
                "position": list(opening["position"]),
                "width_m": opening.get("width_m"),
                "step_free": bool(opening.get("step_free", True)),
            }
        )
    return sorted(found, key=lambda item: item["id"])


def building_center(building_map: BuildingMap) -> tuple[float, float]:
    xs, ys = [], []
    for space in building_map.spaces.values():
        for x, y in space["polygon"]:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0)
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def resolve_building_dir(name: str, roots: list[Path] | tuple[Path, ...]) -> Path | None:
    """Find a building folder by id or directory name: <root>/<name> or <root>/<split>/<name>."""
    name = str(name).strip()
    if not name or "\x00" in name:
        return None
    for root in roots:
        direct = Path(root) / name
        inside = ".." not in name and direct.resolve().is_relative_to(Path(root).resolve())
        if inside and (direct / "building.json").is_file():
            return direct
    if re.fullmatch(r"[\w.\- ]+", name) and ".." not in name:
        for root in roots:
            for candidate in sorted(Path(root).glob(f"*/{name}")):
                if (candidate / "building.json").is_file():
                    return candidate
    return None


def load_building_map(building: CampusBuilding) -> tuple[BuildingMap | None, Finding | None]:
    if building.path is None or not Path(building.path).exists():
        return None, Finding(
            "error",
            "building_path_missing",
            f"Building '{building.building_id}' has no folder at {building.path}.",
            [building.building_id],
        )
    folder = Path(building.path)
    if not folder.is_dir() or not (folder / "building.json").is_file():
        return None, Finding(
            "error",
            "building_json_missing",
            f"The folder of building '{building.building_id}' has no building.json.",
            [building.building_id],
        )
    try:
        return BuildingMap.load(folder), None
    except Exception:  # noqa: BLE001
        return None, Finding(
            "error",
            "building_unreadable",
            f"The building.json of building '{building.building_id}' could not be read.",
            [building.building_id],
        )


def load_maps(campus: Campus) -> tuple[dict[str, BuildingMap | None], list[Finding]]:
    maps: dict[str, BuildingMap | None] = {}
    findings: list[Finding] = []
    for building in campus.buildings:
        if building.building_id in maps:
            continue
        maps[building.building_id], finding = load_building_map(building)
        if finding:
            findings.append(finding)
    return maps, findings


def world_point(building: CampusBuilding, local: list[float] | tuple[float, float]) -> tuple[float, float] | None:
    if building.origin is None:
        return None
    angle = math.radians(building.rotation_deg)
    x, y = local[0], local[1]
    return (
        building.origin[0] + x * math.cos(angle) - y * math.sin(angle),
        building.origin[1] + x * math.sin(angle) + y * math.cos(angle),
    )


def _entrance(maps: dict[str, BuildingMap | None], building_id: str, entrance_id: str) -> dict | None:
    building_map = maps.get(building_id)
    if building_map is None:
        return None
    return next((item for item in entrances(building_map) if item["id"] == entrance_id), None)


# ---------- estimation and validation ----------


def estimate_missing_lengths(campus: Campus, maps: dict[str, BuildingMap | None]) -> None:
    """Fill a missing link length from the building origins (straight line times 1.2) and flag it."""
    for link in campus.links:
        if link.length_m is not None:
            continue
        first = _entrance(maps, link.from_building, link.from_entrance)
        second = _entrance(maps, link.to_building, link.to_entrance)
        building_a, building_b = campus.building(link.from_building), campus.building(link.to_building)
        if not (first and second and building_a and building_b):
            continue
        point_a = world_point(building_a, first["position"])
        point_b = world_point(building_b, second["position"])
        if point_a is None or point_b is None:
            continue
        link.length_m = round(math.dist(point_a, point_b) * ESTIMATE_FACTOR, 1)
        link.length_estimated = True


def validate_campus(campus: Campus, maps: dict[str, BuildingMap | None] | None = None) -> list[Finding]:
    """Check a campus and return plain-sentence findings. Never raises."""
    findings: list[Finding] = []
    if maps is None:
        maps, map_findings = load_maps(campus)
        findings.extend(map_findings)
    seen_buildings: set[str] = set()
    for building in campus.buildings:
        if building.building_id in seen_buildings:
            findings.append(
                Finding(
                    "warning",
                    "duplicate_building",
                    f"Building '{building.building_id}' is listed more than once.",
                    [building.building_id],
                )
            )
        seen_buildings.add(building.building_id)

    link_ids: set[str] = set()
    signatures: set[tuple] = set()
    connected: set[str] = set()
    for link in campus.links:
        connected.update((link.from_building, link.to_building))
        if link.id in link_ids:
            findings.append(
                Finding("error", "duplicate_link_id", f"The link id '{link.id}' is used more than once.", [link.id])
            )
        link_ids.add(link.id)
        if link.kind not in LINK_KINDS:
            findings.append(
                Finding(
                    "error",
                    "unknown_kind",
                    f"Link {link.id} has the kind '{link.kind}', which is not one of {', '.join(LINK_KINDS)}.",
                    [link.id],
                )
            )
        known = True
        for building_id in (link.from_building, link.to_building):
            if building_id not in seen_buildings:
                known = False
                findings.append(
                    Finding(
                        "error",
                        "unknown_building",
                        f"Link {link.id} refers to building '{building_id}', which is not part of the campus.",
                        [link.id, building_id],
                    )
                )
        if link.from_building == link.to_building:
            findings.append(
                Finding(
                    "error",
                    "link_within_building",
                    f"Link {link.id} connects building '{link.from_building}' to itself.",
                    [link.id, link.from_building],
                )
            )
        if known:
            for building_id, entrance_id in (
                (link.from_building, link.from_entrance),
                (link.to_building, link.to_entrance),
            ):
                findings.extend(_check_entrance(link, maps, building_id, entrance_id))
        signature = (
            link.kind,
            frozenset([(link.from_building, link.from_entrance), (link.to_building, link.to_entrance)]),
        )
        if signature in signatures:
            findings.append(
                Finding(
                    "warning",
                    "duplicate_link",
                    f"Link {link.id} repeats another link between the same two entrances.",
                    [link.id],
                )
            )
        signatures.add(signature)
        findings.extend(_check_length(link))
        if link.width_m is not None and not (link.width_m > 0 and math.isfinite(link.width_m)):
            findings.append(
                Finding(
                    "warning",
                    "link_width_invalid",
                    f"Link {link.id} has a width of {link.width_m} m, which is not usable.",
                    [link.id],
                )
            )

    for building in campus.buildings:
        if building.building_id not in connected:
            findings.append(
                Finding(
                    "warning",
                    "building_not_connected",
                    f"Building '{building.building_id}' has no link to any other building, so it is not connected.",
                    [building.building_id],
                )
            )
    return findings


def _check_entrance(
    link: Link, maps: dict[str, BuildingMap | None], building_id: str, entrance_id: str
) -> list[Finding]:
    building_map = maps.get(building_id)
    if building_map is None:
        return []
    items = [link.id, building_id]
    if not entrance_id:
        return [
            Finding(
                "error", "entrance_not_found", f"Link {link.id} names no entrance of building '{building_id}'.", items
            )
        ]
    entrance = _entrance(maps, building_id, entrance_id)
    if entrance is None:
        what = "not an entrance (it does not lead outside)" if entrance_id in building_map.openings else "not present"
        return [
            Finding(
                "error",
                "entrance_not_found",
                f"Link {link.id}: '{entrance_id}' is {what} in building '{building_id}'.",
                items + [entrance_id],
            )
        ]
    if link.step_free and not entrance["step_free"]:
        return [
            Finding(
                "warning",
                "step_free_conflict",
                f"Link {link.id} is marked step-free, but the entrance '{entrance_id}' of building '{building_id}' has steps.",
                items + [entrance_id],
            )
        ]
    return []


def _check_length(link: Link) -> list[Finding]:
    if link.length_m is None:
        return [
            Finding(
                "error",
                "link_length_missing",
                f"Link {link.id} has no length and it cannot be estimated, because the building positions are unknown.",
                [link.id],
            )
        ]
    if not math.isfinite(link.length_m) or link.length_m <= 0:
        return [
            Finding(
                "error",
                "link_length_not_positive",
                f"Link {link.id} has a length of {link.length_m} m, but it must be more than 0.",
                [link.id],
            )
        ]
    found = []
    if link.length_estimated:
        found.append(
            Finding(
                "warning",
                "length_estimated",
                f"The length of link {link.id} is an estimate ({link.length_m} m, straight line times {ESTIMATE_FACTOR}).",
                [link.id],
            )
        )
    if link.length_m > VERY_LONG_LINK_M:
        found.append(
            Finding(
                "warning",
                "link_length_very_long",
                f"Link {link.id} is {link.length_m} m long, which is unusually far for a campus.",
                [link.id],
            )
        )
    return found


# ---------- loading ----------


def load_campus(path: str | Path, root: str | Path | None = None) -> tuple[Campus, Findings]:
    """Load a campus from any supported file. `root` is where building folders are looked up by id."""
    from building_agent.campus_adapters import describe_adapters, load_adapters

    path = Path(path)
    if path.is_dir():
        path = path / "campus.json"
    if not path.is_file():
        raise CampusError(f"There is no campus file at {path}.")
    for adapter in load_adapters().values():
        try:
            recognised = adapter.detect(path)
        except Exception:  # noqa: BLE001
            recognised = False
        if not recognised:
            continue
        try:
            campus = adapter.load(path, Path(root) if root else None)
        except CampusError:
            raise
        except Exception as error:
            raise CampusError(f"The file {path} looked like '{adapter.name}' but could not be read: {error}") from error
        maps, map_findings = load_maps(campus)
        estimate_missing_lengths(campus, maps)
        findings = Findings(list(campus.load_findings) + map_findings + validate_campus(campus, maps))
        return campus, findings
    raise UnknownCampusFormat(f"I do not recognise the file {path.name}.\n{describe_adapters()}")


# ---------- example ----------

EXAMPLE_BUILDINGS = (
    ("proc-campus-dev-000", (0.0, 0.0), 0.0),
    ("proc-factory-dev-003", (120.0, 40.0), 90.0),
    ("resplan-439", (60.0, 130.0), 0.0),
)


def make_example_campus(root: Path = Path("data")) -> Campus:
    """Three real dev buildings joined by a walkway and a bridge. Nothing is written to disk."""
    root = Path(root)
    campus = Campus(id="campus-example", name="Example campus")
    maps = {}
    for building_id, origin, rotation in EXAMPLE_BUILDINGS:
        folder = resolve_building_dir(building_id, [root])
        if folder is None:
            raise CampusError(f"Example building '{building_id}' not found under {root}.")
        campus.buildings.append(CampusBuilding(building_id, folder, origin, rotation))
        maps[building_id] = BuildingMap.load(folder)
    first, second, third = (maps[item[0]] for item in EXAMPLE_BUILDINGS)
    ids = [item[0] for item in EXAMPLE_BUILDINGS]

    def pick(building_map: BuildingMap, step_free: bool = True) -> str:
        options = [item for item in entrances(building_map) if item["step_free"] or not step_free]
        return options[0]["id"]

    campus.links = [
        Link(
            id="L1", kind="walkway", name="Covered walkway", from_building=ids[0], from_entrance=pick(first),
            to_building=ids[1], to_entrance=pick(second), length_m=85.0, width_m=2.5,
        ),
        Link(
            id="L2", kind="bridge", name="Glass bridge", from_building=ids[1], from_entrance=pick(second),
            to_building=ids[2], to_entrance=pick(third), length_m=40.0, width_m=3.0, level_delta=1,
        ),
    ]  # fmt: skip
    return campus
