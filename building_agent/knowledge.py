"""Place knowledge with time: facts (notes, issues, timed closures) anchored at rooms, assets and elements.

See docs/specs/place-knowledge.md. A fact is valid from `valid_from` until `valid_to` (open-ended if None). Nothing
is deleted: "resolved" adds a resolving fact and ends the old one (`valid_to`, `resolved_by`); only `undo_last`
removes a fact, and only within two minutes of creating it. Status is computed at query time:
  open      valid_from <= at and (valid_to is None or at < valid_to) and not resolved by then
  resolved  resolved_by is set and its time (the old fact's valid_to) <= at; resolving facts are always resolved
  expired   valid_to <= at without a resolution
Timed closures act on routing through `apply_timed_closures`, called at the start of every request (no job).

Storage: <root>/<building id>/facts.json (list, creation order) plus photos/<fact id>.jpg. Atomic writes
(temp file + os.replace) under one lock. Nothing from a client becomes a path: the folder comes from the building
id (checked against a strict pattern), photo names from server-made fact ids.
"""

import io
import json
import math
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shapely.geometry import Point, Polygon

from building_agent.time_words import BERLIN, berlin_now
from starter_agent.building_map import BuildingMap, MapError

DEFAULT_ROOT = Path("agent_output") / "knowledge"
FACTS_NAME = "facts.json"
PHOTOS_DIR = "photos"
KINDS = ("note", "issue", "closure")
SOURCES = ("voice", "text", "tap")
STATUSES = ("open", "resolved", "expired", "all")
MAX_TEXT_CHARS = 500
MAX_AUTHOR_CHARS = 80
MAX_UTTERANCE_CHARS = 1000
MAX_RELATED = 20
MAX_FACTS_PER_BUILDING = 5000
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 50_000_000  # refuse decompression bombs before decoding
MAX_SIDE_PX = 1600
JPEG_QUALITY = 85
NEAR_ROOM_M = 1.0  # a point may lie this far outside its room (a tap on the wall line)
UNDO_SECONDS = 120
FACT_ID = re.compile(r"f-[0-9a-f]{12}")
BUILDING_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")
MAGIC = ((b"\xff\xd8\xff", "JPEG"), (b"\x89PNG\r\n\x1a\n", "PNG"))
DEFAULT_AUTHOR = "Technician"


class KnowledgeError(ValueError):
    """A request the store refuses; `status` is the HTTP status the server answers with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Fact:
    id: str
    building: str
    kind: str
    anchor: dict  # {space_id, asset_id, element_id, point, floor_id}
    text: str
    valid_from: str
    valid_to: str | None = None
    status: str = "open"  # stored: open | resolved; returned by query: open | resolved | expired at `at`
    resolved_by: str | None = None
    author: str | None = None
    person_id: str | None = None
    source: str = "text"
    utterance: str = ""
    photo: str | None = None  # stored as "photos/<id>.jpg"; the web layer turns it into a URL
    created_at: str = ""
    related: list[str] = field(default_factory=list)
    resolves: str | None = None  # set on a resolving fact: the fact it ended
    previous_valid_to: str | None = None  # on a resolved fact: its valid_to before resolving (for undo)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Fact":
        names = cls.__dataclass_fields__
        return cls(**{key: value for key, value in raw.items() if key in names})


# ---------- time ----------


def iso(moment: datetime) -> str:
    return berlin_now(moment).isoformat(timespec="seconds")


def parse_time(value) -> datetime | None:
    """ISO text or datetime -> aware datetime in UTC (naive counts as Europe/Berlin); None stays None.

    UTC on purpose: two aware datetimes with the SAME ZoneInfo compare by wall time, so in the repeated hour when
    summer time ends (02:00-03:00 twice) a fact made at 02:59+02:00 looked like the future at 02:05+01:00."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return berlin_now(value).astimezone(UTC)
    try:
        return berlin_now(datetime.fromisoformat(str(value))).astimezone(UTC)
    except ValueError as error:
        raise KnowledgeError(f"Not a time: {value!r}.") from error


def status_at(fact: Fact, at: datetime) -> str:
    """open | resolved | expired | future, as seen at `at`."""
    if fact.resolves:
        return "resolved"
    end = parse_time(fact.valid_to)
    if end is not None and end <= at:
        return "resolved" if fact.resolved_by else "expired"
    if parse_time(fact.valid_from) > at:
        return "future"
    return "open"


def is_active(fact: Fact, at: datetime) -> bool:
    return status_at(fact, at) == "open"


# ---------- names, ids, anchors ----------


def building_of(building: "BuildingMap | str") -> str:
    """The store key of a building: its id from building.json (or the id string itself)."""
    name = (building.data.get("building") or {}).get("id") if isinstance(building, BuildingMap) else building
    if not isinstance(name, str) or not BUILDING_ID.fullmatch(name):
        raise KnowledgeError("Unknown building.", 404)
    return name


def person_id_of(author: str | None) -> str | None:
    """'Techniker A' -> 'techniker-a'."""
    if not author:
        return None
    slug = re.sub(r"[^0-9a-zäöüß]+", "-", author.strip().lower()).strip("-")
    return slug or None


def clean_text(raw, name: str, limit: int, required: bool) -> str | None:
    if raw is None and not required:
        return None
    if not isinstance(raw, str):
        raise KnowledgeError(f"{name} must be text.")
    text = " ".join(raw.split()) if name != "utterance" else raw.strip()
    if not text:
        if required:
            raise KnowledgeError(f"{name} must not be empty.")
        return None
    if len(text) > limit:
        raise KnowledgeError(f"{name} is longer than {limit} characters.")
    return text


def element_spaces(bm: BuildingMap, element_id: str) -> list[str]:
    if element_id in bm.openings:
        return list(bm.openings[element_id]["space_ids"])
    if element_id in bm.connectors:
        return list(bm.connectors[element_id]["space_ids"])
    if element_id in bm.spaces:
        return [element_id]
    return []


def node_spaces(bm: BuildingMap, node_id: str) -> list[str]:
    """Rooms a node (room, asset, door/opening, lift/stairs) is in or touches."""
    if node_id in bm.assets:
        return [bm.assets[node_id]["space_id"]]
    return element_spaces(bm, node_id)


def known_node(bm: BuildingMap, node_id) -> bool:
    return isinstance(node_id, str) and (
        node_id in bm.spaces or node_id in bm.assets or node_id in bm.openings or node_id in bm.connectors
    )


def read_point(raw, polygon: Polygon | None) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = [raw.get("x"), raw.get("y")]
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        raise KnowledgeError("point must be [x, y].")
    if any(isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) for v in raw):
        raise KnowledgeError("point must be two finite numbers.")
    point = Point(float(raw[0]), float(raw[1]))
    if polygon is not None and polygon.distance(point) > NEAR_ROOM_M:
        raise KnowledgeError("point is not in the room.")
    return [round(point.x, 3), round(point.y, 3)]


def check_anchor(bm: BuildingMap, raw, kind: str) -> dict:
    """Validated anchor with every id checked against the map; space and floor filled in from the asset or
    element when missing."""
    if not isinstance(raw, dict):
        raise KnowledgeError("anchor must be an object.")
    space_id, asset_id, element_id, floor_id = (
        raw.get(name) for name in ("space_id", "asset_id", "element_id", "floor_id")
    )
    for name, value in (
        ("space_id", space_id),
        ("asset_id", asset_id),
        ("element_id", element_id),
        ("floor_id", floor_id),
    ):
        if value is not None and not isinstance(value, str):
            raise KnowledgeError(f"{name} must be an id.")
    space_id, asset_id, element_id, floor_id = (v or None for v in (space_id, asset_id, element_id, floor_id))
    if asset_id is not None:
        if asset_id not in bm.assets:
            raise KnowledgeError("asset_id is not an asset of this building.")
        asset_space = bm.assets[asset_id]["space_id"]
        if space_id is not None and space_id != asset_space:
            raise KnowledgeError("asset_id is not in that room.")
        space_id = asset_space
    if element_id is not None:
        if not (element_id in bm.openings or element_id in bm.connectors or element_id in bm.spaces):
            try:
                element_id = bm.find_element(element_id)
            except MapError as error:
                raise KnowledgeError("element_id is not a door, lift, stairs or room of this building.") from error
        touching = element_spaces(bm, element_id)
        if space_id is None:
            if floor_id is not None and element_id in bm.connectors:  # the stop on the named floor
                stops = dict(zip(bm.connectors[element_id]["floor_ids"], touching, strict=False))
                space_id = stops.get(floor_id)
            space_id = space_id or (touching[0] if touching else None)
        elif space_id not in touching and element_id not in bm.connectors:
            raise KnowledgeError("element_id does not touch that room.")
    if kind == "closure" and element_id is None:
        raise KnowledgeError("A closure needs element_id (door, lift, stairs or room).")
    if space_id is None:
        raise KnowledgeError("anchor needs space_id, asset_id or element_id.")
    if space_id not in bm.spaces:
        raise KnowledgeError("space_id is not a room of this building.")
    space = bm.spaces[space_id]
    if floor_id is not None and floor_id not in bm.floors:
        raise KnowledgeError("floor_id is not a floor of this building.")
    if floor_id is not None and floor_id != space["floor_id"]:
        raise KnowledgeError("floor_id does not match the room.")
    point = read_point(raw.get("point"), Polygon(space["polygon"]))
    return {
        "space_id": space_id,
        "asset_id": asset_id,
        "element_id": element_id,
        "point": point,
        "floor_id": space["floor_id"],
    }


def check_related(bm: BuildingMap, raw: Iterable, anchor: dict) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str) or not isinstance(raw, Iterable):
        raise KnowledgeError("related must be a list of ids.")
    main = {anchor["space_id"], anchor["asset_id"], anchor["element_id"]}
    related: list[str] = []
    for node_id in raw:
        if not known_node(bm, node_id):
            raise KnowledgeError(f"related id {str(node_id)[:60]!r} is not part of this building.")
        if node_id not in main and node_id not in related:
            related.append(node_id)
    if len(related) > MAX_RELATED:
        raise KnowledgeError(f"At most {MAX_RELATED} related places.")
    return related


# ---------- photos ----------


def sniff(data: bytes) -> str | None:
    """'JPEG', 'PNG' or 'WEBP' from the first bytes, None for anything else."""
    for magic, kind in MAGIC:
        if data.startswith(magic):
            return kind
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def clean_photo(data: bytes) -> bytes:
    """Sniffed JPEG/PNG/WebP (<= 8 MB) -> JPEG, upright, max 1600 px long side, no metadata (EXIF, GPS, ICC)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if not isinstance(data, bytes | bytearray) or not data:
        raise KnowledgeError("photo must be image bytes.")
    if len(data) > MAX_PHOTO_BYTES:
        raise KnowledgeError("The photo is larger than 8 MB.", 413)
    kind = sniff(bytes(data))
    if kind is None:
        raise KnowledgeError("The photo must be a JPEG, PNG or WebP image.", 415)
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != kind:
                raise KnowledgeError("The photo content does not match its type.", 415)
            if image.width * image.height > MAX_PIXELS:
                raise KnowledgeError("The photo has too many pixels.", 413)
            image.load()
            upright = ImageOps.exif_transpose(image)  # keep the orientation the phone meant, then drop EXIF
            if upright.mode in ("RGBA", "LA", "P", "PA"):
                rgba = upright.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                upright = flat
            else:
                upright = upright.convert("RGB")
            upright.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
            clean = Image.new("RGB", upright.size)  # fresh image: no info, no EXIF, no ICC carried over
            clean.paste(upright)
            out = io.BytesIO()
            clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except KnowledgeError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise KnowledgeError("The photo could not be read.", 415) from error


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


# ---------- areas and asset types ----------


HALL = re.compile(r"^(?:halle|hall|h)\s*-?\s*([a-z])\s*-?\s*(\d+)?$")


def area_spaces(bm: BuildingMap, area: str) -> set[str]:
    """Rooms of an area: 'Halle A' / 'Hall A' / 'H-A' -> every zone named '... H-A<n>'; 'Halle A2' -> 'H-A2';
    otherwise rooms whose name or ref starts with (or whose name contains) the words, or a floor name."""
    wanted = " ".join(str(area or "").lower().split())
    if not wanted:
        return set()
    hall = HALL.match(wanted)
    if hall:
        letter, number = hall.group(1), hall.group(2)
        code = re.compile(rf"\bh-{letter}{number}\b" if number else rf"\bh-{letter}\d+\b")
        found = {space_id for space_id, space in bm.spaces.items() if code.search(space["name"].lower())}
        if found:
            return found
    found = set()
    for space_id, space in bm.spaces.items():
        name, ref = space["name"].lower(), str(space.get("ref") or "").lower()
        if name.startswith(wanted) or ref == wanted or f" {wanted}" in f" {name}":
            found.add(space_id)
    if not found:
        floors = {floor_id for floor_id, floor in bm.floors.items() if floor["name"].lower() == wanted}
        found = {space_id for space_id, space in bm.spaces.items() if space["floor_id"] in floors}
    return found


def type_matches(asset_type: str, wanted: str) -> bool:
    norm = re.sub(r"[\s-]+", "_", wanted.strip().lower())
    return asset_type in (norm, norm.removesuffix("s"), norm.removesuffix("es"))


# ---------- store ----------


class KnowledgeStore:
    """All facts on disk, one JSON file per building. Thread-safe; every write is atomic."""

    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.lock = threading.RLock()
        self.cache: dict[str, tuple[float, list[Fact]]] = {}

    # --- files ---

    def folder(self, building) -> Path:
        name = building_of(building)
        folder = (self.root / name).resolve()
        if folder.parent != self.root.resolve():
            raise KnowledgeError("Unknown building.", 404)
        return folder

    def load(self, building) -> list[Fact]:
        path = self.folder(building) / FACTS_NAME
        with self.lock:
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                return []
            cached = self.cache.get(str(path))
            if cached and cached[0] == mtime:
                return [replace(fact) for fact in cached[1]]
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            facts = [
                Fact.from_dict(item)
                for item in raw
                if isinstance(item, dict) and FACT_ID.fullmatch(str(item.get("id", "")))
            ]
            self.cache[str(path)] = (mtime, facts)
            return [replace(fact) for fact in facts]

    def save(self, building, facts: list[Fact]) -> None:
        path = self.folder(building) / FACTS_NAME
        data = json.dumps([fact.to_dict() for fact in facts], ensure_ascii=False, indent=1).encode("utf-8")
        with self.lock:
            atomic_write(path, data)
            self.cache.pop(str(path), None)

    def photo_path(self, building, fact_id: str) -> Path | None:
        """The stored JPEG of a fact, None if the id is malformed, unknown or has no photo."""
        if not isinstance(fact_id, str) or not FACT_ID.fullmatch(fact_id):
            return None
        fact = next((fact for fact in self.load(building) if fact.id == fact_id), None)
        if fact is None or not fact.photo:
            return None
        path = self.folder(building) / PHOTOS_DIR / f"{fact_id}.jpg"
        return path if path.is_file() else None

    # --- writing ---

    def add(
        self,
        bm: BuildingMap,
        *,
        kind: str,
        anchor: dict,
        text: str,
        valid_to=None,
        author: str | None = None,
        source: str = "text",
        utterance: str = "",
        related: Iterable[str] = (),
        photo_bytes: bytes | None = None,
        now: datetime | None = None,
    ) -> Fact:
        """Validate and store one fact (valid from now). valid_to: ISO text or datetime, must be in the future."""
        if kind not in KINDS:
            raise KnowledgeError(f"kind must be one of {', '.join(KINDS)}.")
        if source not in SOURCES:
            raise KnowledgeError(f"source must be one of {', '.join(SOURCES)}.")
        current = berlin_now(now)
        text = clean_text(text, "text", MAX_TEXT_CHARS, required=True)
        author = clean_text(author, "author", MAX_AUTHOR_CHARS, required=False)
        utterance = clean_text(utterance or None, "utterance", MAX_UTTERANCE_CHARS, required=False) or ""
        clean_anchor = check_anchor(bm, anchor, kind)
        clean_related = check_related(bm, related, clean_anchor)
        end = parse_time(valid_to)
        if end is not None and end <= current:
            raise KnowledgeError("valid_to must be in the future.")
        photo = clean_photo(photo_bytes) if photo_bytes is not None else None
        fact = Fact(
            id="f-" + uuid.uuid4().hex[:12],
            building=building_of(bm),
            kind=kind,
            anchor=clean_anchor,
            related=clean_related,
            text=text,
            valid_from=iso(current),
            valid_to=iso(end) if end else None,
            status="open",
            author=author,
            person_id=person_id_of(author),
            source=source,
            utterance=utterance,
            created_at=iso(current),
        )
        with self.lock:
            facts = self.load(bm)
            if len(facts) >= MAX_FACTS_PER_BUILDING:
                raise KnowledgeError("This building has too many facts.", 409)
            if photo is not None:
                atomic_write(self.folder(bm) / PHOTOS_DIR / f"{fact.id}.jpg", photo)
                fact.photo = f"{PHOTOS_DIR}/{fact.id}.jpg"
            self.save(bm, [*facts, fact])
        return fact

    def resolve(
        self, bm: BuildingMap, fact_id: str, *, text: str = "", author: str | None = None, now: datetime | None = None
    ) -> Fact:
        """End an open fact: a new resolving fact (status resolved, `resolves` = old id) and the old one gets
        valid_to = now and resolved_by. Any anchor of a multi-anchor fact resolves the whole fact."""
        current = berlin_now(now)
        text = clean_text(text or None, "text", MAX_TEXT_CHARS, required=False) or "resolved"
        author = clean_text(author, "author", MAX_AUTHOR_CHARS, required=False)
        with self.lock:
            facts = self.load(bm)
            old = next((fact for fact in facts if fact.id == fact_id), None)
            if old is None:
                raise KnowledgeError("Unknown fact.", 404)
            state = status_at(old, current)
            if state != "open":
                raise KnowledgeError(f"That fact is not open (it is {state}).", 409)
            done = Fact(
                id="f-" + uuid.uuid4().hex[:12],
                building=old.building,
                kind=old.kind,
                anchor=dict(old.anchor),
                related=list(old.related),
                text=text,
                valid_from=iso(current),
                valid_to=iso(current),
                status="resolved",
                author=author,
                person_id=person_id_of(author),
                source="text",
                created_at=iso(current),
                resolves=old.id,
            )
            old.previous_valid_to = old.valid_to
            old.valid_to = iso(current)
            old.resolved_by = done.id
            old.status = "resolved"
            self.save(bm, [*facts, done])
        return replace(done)

    def undo_last(self, building, now: datetime | None = None, within_s: int = UNDO_SECONDS) -> Fact | None:
        """Remove the newest fact if it was created less than `within_s` seconds ago (typo right after saving).
        Undoing a resolution reopens the fact it resolved. Returns the removed fact or None."""
        current = berlin_now(now)
        with self.lock:
            facts = self.load(building)
            if not facts:
                return None
            last = facts[-1]
            age = (current - parse_time(last.created_at)).total_seconds()
            if not 0 <= age < within_s:
                return None
            kept = facts[:-1]
            if last.resolves:
                for fact in kept:
                    if fact.id == last.resolves and fact.resolved_by == last.id:
                        fact.valid_to, fact.resolved_by, fact.status = fact.previous_valid_to, None, "open"
                        fact.previous_valid_to = None
            self.save(building, kept)
            (self.folder(building) / PHOTOS_DIR / f"{last.id}.jpg").unlink(missing_ok=True)
        return last

    # --- reading ---

    def get(self, building, fact_id: str) -> Fact | None:
        return next((fact for fact in self.load(building) if fact.id == fact_id), None)

    def query(
        self,
        bm: BuildingMap,
        *,
        space_id: str | None = None,
        asset_id: str | None = None,
        element_id: str | None = None,
        area: str | None = None,
        floor_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        status: str = "open",
        person: str | None = None,
        since=None,
        until=None,
        at=None,
        history: bool = False,
    ) -> list[Fact]:
        """Facts matching every given filter; `status` is computed at `at` (default now) on the returned copies.
        Default: open now. history=True (or status='all'): every status, newest first. since/until keep facts
        whose validity overlaps that period. space_id also matches facts on assets in the room and on doors/lifts
        touching it; every filter also looks at `related`."""
        if status not in STATUSES:
            raise KnowledgeError(f"status must be one of {', '.join(STATUSES)}.")
        moment = berlin_now(parse_time(at)) if at is not None else berlin_now()
        wanted_status = "all" if history and status == "open" else status
        start, end = parse_time(since), parse_time(until)
        areas = area_spaces(bm, area) if area else None
        person_key = person_id_of(person) if person else None
        found: list[tuple[int, Fact]] = []
        for index, fact in enumerate(self.load(bm)):
            state = status_at(fact, moment)
            if state == "future" or (wanted_status != "all" and state != wanted_status):
                continue
            if start is not None or end is not None:
                begins, ends = parse_time(fact.valid_from), parse_time(fact.valid_to)
                if end is not None and begins > end:
                    continue
                if start is not None and ends is not None and ends < start:
                    continue
            if person_key and fact.person_id != person_key:
                continue
            nodes = [fact.anchor.get("space_id"), fact.anchor.get("asset_id"), fact.anchor.get("element_id")]
            nodes = [node for node in [*nodes, *fact.related] if node]
            spaces = {fact.anchor.get("space_id")} | {space for node in nodes for space in node_spaces(bm, node)}
            spaces.discard(None)
            assets = [bm.assets[node] for node in nodes if node in bm.assets]
            if space_id and space_id not in spaces:
                continue
            if asset_id and asset_id not in nodes:
                continue
            if element_id and element_id not in nodes:
                continue
            if areas is not None and not (spaces & areas):
                continue
            if (
                floor_id
                and floor_id != fact.anchor.get("floor_id")
                and not any(bm.spaces[space]["floor_id"] == floor_id for space in spaces if space in bm.spaces)
            ):
                continue
            if asset_type and not any(type_matches(asset["type"], asset_type) for asset in assets):
                continue
            if category and not any(asset.get("category") == category.strip().lower() for asset in assets):
                continue
            found.append((index, replace(fact, status=state)))
        if wanted_status == "all" or history:
            found.sort(key=lambda pair: (parse_time(pair[1].created_at), pair[0]), reverse=True)
        return [fact for _, fact in found]

    def active(self, building, at=None) -> list[Fact]:
        """Every fact open at `at` (default now), in creation order, status set."""
        moment = berlin_now(parse_time(at)) if at is not None else berlin_now()
        return [replace(fact, status="open") for fact in self.load(building) if is_active(fact, moment)]

    def active_closures(self, building, at=None) -> dict[str, str | None]:
        """{element_id: valid_to ISO (None = until resolved)} of closures open at `at`; the latest end wins."""
        ends: dict[str, str | None] = {}
        for fact in self.active(building, at):
            element = fact.anchor.get("element_id")
            if fact.kind != "closure" or not element:
                continue
            if element in ends and (ends[element] is None or fact.valid_to is None):
                ends[element] = None
            elif element not in ends or parse_time(fact.valid_to) > parse_time(ends[element]):
                ends[element] = fact.valid_to
        return ends

    def persons(self, building) -> list[dict]:
        """[{person_id, name, count}] of everyone who reported something, most reports first."""
        people: dict[str, dict] = {}
        for fact in self.load(building):
            if not fact.person_id:
                continue
            entry = people.setdefault(fact.person_id, {"person_id": fact.person_id, "name": fact.author, "count": 0})
            entry["count"] += 1
            entry["name"] = fact.author  # the latest spelling
        return sorted(people.values(), key=lambda entry: (-entry["count"], entry["person_id"]))


# ---------- routing ----------


def apply_timed_closures(bm: BuildingMap, store: KnowledgeStore, now: datetime | None = None) -> set[str]:
    """Close every element with an open closure fact and reopen the ones whose fact expired or was resolved.
    Only closures this function made are reopened; a manual closure (no fact) is never touched. Returns the
    element ids closed by facts now. Call it at the start of every route/state request and chat turn."""
    try:
        wanted = {
            element
            for element in store.active_closures(bm, now if now is not None else None)
            if element in bm.connectors or element in bm.openings or element in bm.spaces
        }
    except KnowledgeError:
        return set()
    ours: set[str] = getattr(bm, "fact_closed", set())
    for element in ours - wanted:
        bm.closed.discard(element)
    now_ours = ours & wanted
    for element in wanted:
        if element not in bm.closed:
            bm.closed.add(element)
            now_ours.add(element)
    bm.fact_closed = now_ours
    return wanted


def closed_until(store: KnowledgeStore, bm: BuildingMap, now: datetime | None = None) -> dict[str, str]:
    """{element_id: ISO end} for timed closures open now (the page shows 'Closed until ...')."""
    return {element: end for element, end in store.active_closures(bm, now).items() if end}


def later(moment: datetime, **delta) -> datetime:
    """Helper for callers and tests: moment + delta in real time (DST safe)."""
    return (berlin_now(moment).astimezone(UTC) + timedelta(**delta)).astimezone(BERLIN)


def graph_jsonld(bm: BuildingMap, store: KnowledgeStore, at=None) -> dict:
    """JSON-LD of the building plus facts with Brick Schema / RealEstateCore types, see knowledge_export."""
    from building_agent.knowledge_export import graph_jsonld as build

    return build(bm, store, at)


def aas_export(bm: BuildingMap, store: KnowledgeStore, at=None) -> dict:
    """Asset Administration Shell (simplified AAS v3 JSON) per machine, see knowledge_export."""
    from building_agent.knowledge_export import aas_export as build

    return build(bm, store, at)
