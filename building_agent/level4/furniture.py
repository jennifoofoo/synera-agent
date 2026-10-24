"""Furniture glyphs of the plan svg: what they say about a room.

The kit draws every furniture or equipment item of a room as a small coloured rectangle (fill with opacity 0.75) on
the labelled plan, and the matching svg keeps them as patches next to the room outlines. On the 240 kit buildings of
train and dev the glyphs are one to one with the assets of building.json (same count, same centre, same footprint),
and the colour is the asset category (brown furniture, green equipment, blue fixture, red machine). So a glyph is
(category, footprint in metres), and the footprint nearly names the asset type. This module reads the glyphs, turns a
room into tokens, guesses the room type and the asset types, and says how sure it is. Nothing calls an API: the model
is a small naive Bayes table (furniture_model.json, trained by scripts/furniture_train.py), counts only, no new
dependency. Low confidence means: keep the generic type and the asset out (never a guess below the thresholds)."""

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

PNG_PER_PT = 100 / 72
# fill -> glyph colour class (also the asset category: brown furniture, green equipment, blue fixture, red machine)
GLYPH_FILLS = {"#7f6a4f": "brown", "#2e7d32": "green", "#4f81bd": "blue", "#c0504d": "red"}
CATEGORY = {"brown": "furniture", "green": "equipment", "blue": "fixture", "red": "machine"}
MODEL_PATH = Path(__file__).with_name("furniture_model.json")
GENERIC = "generic_room"
CLASSIFIED_FILLS = {
    "beige",
    "yellow",
}  # plain rooms; orange and purple (stair, lift), green (balcony), grey are read elsewhere
CORRIDOR_FILL = "grey"
OUTDOOR_FILL = "green"
ROOM_CONFIDENCE = 0.8  # posterior needed before a room type is set
ASSET_CONFIDENCE = 0.8  # posterior needed before an asset is listed
STEP = 0.05  # glyph sizes are put on this grid (metres)

_GLYPH = re.compile(r'<g id="patch_\d+">\s*<path d="([^"]+)"[^>]*style="fill: (#[0-9a-f]{6}); opacity: 0\.75"')
_NUMBER = re.compile(r"-?\d+\.?\d*")


@dataclass
class Glyph:
    colour: str  # "brown" | "green" | "blue" | "red"
    x: float  # centre, png pixels
    y: float
    long_px: float  # longer side of the minimum rotated rectangle
    short_px: float
    angle: float  # direction of the long side in degrees, 0 to 180


def read_glyphs(text: str) -> list[Glyph]:
    """Every furniture glyph of an svg text, in drawing order. Unknown fills and degenerate shapes are skipped."""
    glyphs = []
    for data, fill in _GLYPH.findall(text):
        colour = GLYPH_FILLS.get(fill)
        numbers = [float(v) for v in _NUMBER.findall(data)]
        if colour is None or len(numbers) % 2 or len(numbers) < 6:
            continue
        points = [(x * PNG_PER_PT, y * PNG_PER_PT) for x, y in zip(numbers[::2], numbers[1::2])]
        shape = Polygon(points)
        if not shape.is_valid or shape.area <= 0:
            continue
        glyphs.append(_glyph(colour, shape))
    return glyphs


def _glyph(colour: str, shape: Polygon) -> Glyph:
    box = list(shape.minimum_rotated_rectangle.exterior.coords)[:4]
    first = (box[1][0] - box[0][0], box[1][1] - box[0][1])
    second = (box[2][0] - box[1][0], box[2][1] - box[1][1])
    length_a, length_b = math.hypot(*first), math.hypot(*second)
    vector, long_px, short_px = (first, length_a, length_b) if length_a >= length_b else (second, length_b, length_a)
    centre = shape.centroid
    return Glyph(colour, centre.x, centre.y, long_px, short_px, math.degrees(math.atan2(vector[1], vector[0])) % 180)


def glyph_key(glyph: Glyph, px_per_m: float) -> str:
    """Colour and footprint on the 5 cm grid, e.g. 'brown:1.4x0.7' (the long side first)."""
    long_m = round(glyph.long_px / px_per_m / STEP) * STEP
    short_m = round(glyph.short_px / px_per_m / STEP) * STEP
    return f"{glyph.colour}:{long_m:.2f}x{short_m:.2f}"


def key_footprint(key: str) -> tuple[float, float]:
    long_m, short_m = key.split(":")[1].split("x")
    return float(long_m), float(short_m)


# ---------- rooms: which glyphs, which tokens ----------


def glyphs_by_room(polygons: list[list[list[float]]], glyphs: list[Glyph]) -> list[list[Glyph]]:
    """For every room polygon (px) the glyphs whose centre lies in it. A glyph goes to the smallest room that holds it."""
    shapes = [Polygon(points) for points in polygons]
    prepared = [prep(shape) for shape in shapes]
    order = sorted(range(len(shapes)), key=lambda i: shapes[i].area)
    held: list[list[Glyph]] = [[] for _ in shapes]
    for glyph in glyphs:
        point = Point(glyph.x, glyph.y)
        for index in order:
            if prepared[index].contains(point):
                held[index].append(glyph)
                break
    return held


def ref_shape(ref: str | None) -> str:
    """Format of a room number: digits become d, letters L ('1.30' -> 'd.dd', 'H-A2' -> 'L-Ld')."""
    if not ref:
        return "none"
    letters = re.sub(r"[A-Za-z]+", "L", ref)
    return re.sub(r"\d+", lambda m: "d" * min(len(m.group()), 4), letters)


def _bin(value: float, edges: list[float]) -> int:
    return sum(value >= edge for edge in edges)


@dataclass
class RoomInput:
    polygon_px: list[list[float]]
    ref: str | None
    fill_class: str  # palette name of the outline fill ("beige", "green", "grey", ...), see svg_read.ROOM_FILLS
    glyphs: list[Glyph]
    corridor_next_to: bool = False


def room_tokens(room: RoomInput, px_per_m: float, level: int, rooms_on_floor: int) -> dict[str, float]:
    """Weighted tokens of one room: glyph keys (the main signal), size, shape, number format, floor, corridor flag."""
    shape = Polygon(room.polygon_px)
    area = shape.area / px_per_m**2
    box = list(shape.minimum_rotated_rectangle.exterior.coords)[:4]
    sides = sorted([math.dist(box[0], box[1]), math.dist(box[1], box[2])])
    aspect = sides[1] / sides[0] if sides[0] > 0 else 1.0
    count = len(room.glyphs)
    tokens: dict[str, float] = defaultdict(float)
    damp = 1 / math.sqrt(max(count, 1))
    for glyph in room.glyphs:
        tokens["g:" + glyph_key(glyph, px_per_m)] += damp * GLYPH_WEIGHT
    tokens[f"area:{_bin(area, [4, 7, 10, 14, 20, 30, 50, 100, 200])}"] += 1
    tokens[f"aspect:{_bin(aspect, [1.3, 1.8, 2.5, 4])}"] += 1
    tokens[f"count:{_bin(count, [1, 2, 3, 5, 9, 15])}"] += 1
    tokens[f"ref:{ref_shape(room.ref)}"] += 1
    tokens[f"level:{min(max(level, -1), 3)}"] += 1
    tokens[f"corr:{int(room.corridor_next_to)}"] += 1
    tokens[f"fill:{room.fill_class}"] += 1
    tokens[f"size:{_bin(rooms_on_floor, [6, 12, 25, 60])}"] += 1
    return dict(tokens)


GLYPH_WEIGHT = 3.0


def corridor_flags(polygons: list[list[list[float]]], fill_classes: list[str], px_per_m: float) -> list[bool]:
    """True for every room that touches a room with the corridor fill (grey)."""
    shapes = [Polygon(points) for points in polygons]
    corridors = [shape.buffer(0.3 * px_per_m) for shape, fill in zip(shapes, fill_classes) if fill == CORRIDOR_FILL]
    return [
        fill != CORRIDOR_FILL and any(c.intersects(shape) for c in corridors)
        for shape, fill in zip(shapes, fill_classes)
    ]


# ---------- the model: naive Bayes over tokens ----------


class RoomTypeModel:
    """Multinomial naive Bayes (counts only). Fit, subtract (leave one out), predict with a posterior."""

    def __init__(self) -> None:
        self.class_count: Counter[str] = Counter()
        self.token_count: dict[str, Counter[str]] = defaultdict(Counter)
        self.vocabulary: set[str] = set()

    def add(self, label: str, tokens: dict[str, float], sign: int = 1) -> None:
        self.class_count[label] += sign
        for token, weight in tokens.items():
            self.token_count[label][token] += sign * weight
            self.vocabulary.add(token)

    def predict(self, tokens: dict[str, float]) -> tuple[str, float]:
        """(label, posterior). The posterior is tempered by the number of token groups so it is not wildly sure."""
        classes = [c for c, n in self.class_count.items() if n > 0]
        if not classes:
            return GENERIC, 0.0
        total = sum(self.class_count[c] for c in classes)
        scores = {}
        size = len(self.vocabulary) + 1
        for label in classes:
            row = self.token_count[label]
            row_total = sum(v for v in row.values() if v > 0)
            score = math.log(self.class_count[label] / total)
            for token, weight in tokens.items():
                score += weight * math.log((max(row.get(token, 0.0), 0.0) + 0.1) / (row_total + 0.1 * size))
            scores[label] = score / TEMPERATURE
        top = max(scores.values())
        norm = sum(math.exp(v - top) for v in scores.values())
        label = max(scores, key=scores.get)
        return label, 1 / norm

    def to_json(self) -> dict:
        return {
            "classes": dict(self.class_count),
            "tokens": {c: {t: round(v, 3) for t, v in row.items() if v > 0} for c, row in self.token_count.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> "RoomTypeModel":
        model = cls()
        model.class_count = Counter(data["classes"])
        for label, row in data["tokens"].items():
            model.token_count[label] = Counter(row)
            model.vocabulary.update(row)
        return model


TEMPERATURE = 4.0


# ---------- asset types: table of (room type, key) and (key) ----------


class AssetTypeTable:
    """P(asset type | glyph key, room type, rank) with back-offs. The rank is the place of the glyph among the glyphs
    of the same key in its room, in drawing order (the kit draws a room's items in the order it makes them, so the
    first 0.6 x 0.6 piece of a kitchen is the stove and the second the dishwasher)."""

    def __init__(self) -> None:
        self.tables: list[dict[str, Counter[str]]] = [defaultdict(Counter) for _ in range(3)]

    @staticmethod
    def names(key: str, room_type: str | None, rank: int) -> list[str | None]:
        capped = min(rank, 2)
        room = None if room_type is None else f"{room_type}|{key}"
        return [None if room is None else f"{room}#{capped}", room, key]

    def add(self, key: str, room_type: str, asset_type: str, rank: int, sign: int = 1) -> None:
        for table, name in zip(self.tables, self.names(key, room_type, rank), strict=True):
            table[name][asset_type] += sign

    def predict(self, key: str, room_type: str | None, rank: int = 0) -> tuple[str, float] | None:
        """Most specific table with enough support wins (counts on the same footing as the posterior)."""
        for table, name in zip(self.tables, self.names(key, room_type, rank), strict=True):
            row = table.get(name) if name is not None else None
            total = sum(v for v in row.values() if v > 0) if row else 0
            if total >= MIN_SUPPORT:
                label, n = max(row.items(), key=lambda kv: kv[1])
                return label, n / total
        return None

    def to_json(self) -> dict:
        return {
            str(i): {k: {t: v for t, v in row.items() if v > 0} for k, row in table.items()}
            for i, table in enumerate(self.tables)
        }

    @classmethod
    def from_json(cls, data: dict) -> "AssetTypeTable":
        table = cls()
        for index, rows in enumerate(table.tables):
            for key, row in data[str(index)].items():
                rows[key] = Counter(row)
        return table


def glyph_ranks(glyphs: list[Glyph], px_per_m: float) -> list[tuple[str, int]]:
    """(key, rank among the same key in this room) of every glyph, in drawing order."""
    seen: Counter[str] = Counter()
    out = []
    for glyph in glyphs:
        key = glyph_key(glyph, px_per_m)
        out.append((key, seen[key]))
        seen[key] += 1
    return out


MIN_SUPPORT = 3


@dataclass
class Model:
    rooms: RoomTypeModel
    assets: AssetTypeTable
    meta: dict | None = None  # leave-one-building-out numbers of the training run, shown on the card

    def save(self, path: Path = MODEL_PATH) -> None:
        data = {"rooms": self.rooms.to_json(), "assets": self.assets.to_json(), "meta": self.meta or {}}
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "Model | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                RoomTypeModel.from_json(data["rooms"]), AssetTypeTable.from_json(data["assets"]), data.get("meta") or {}
            )
        except (OSError, ValueError, KeyError):
            return None


# ---------- applying the model to a floor ----------


@dataclass
class RoomGuess:
    room_type: str  # GENERIC when unsure
    confidence: float
    guessed: bool  # True when the type was set from the glyphs


@dataclass
class AssetGuess:
    asset_type: str
    category: str
    x_px: float
    y_px: float
    width_m: float
    depth_m: float
    rotation_deg: float
    room_index: int
    confidence: float


def asset_context(fill_class: str) -> str | None:
    """Room type that a fill colour already proves (the green outline is a balcony), else None."""
    return "balcony" if fill_class == OUTDOOR_FILL else None


def infer_floor(
    rooms: list[RoomInput], px_per_m: float, level: int, model: Model
) -> tuple[list[RoomGuess], list[AssetGuess]]:
    """Room type and asset list of every room of a floor. Only plain rooms (CLASSIFIED_FILLS) get a type; corridor,
    stair, lift and outdoor rooms keep what their colour says. Assets are listed only at or above ASSET_CONFIDENCE."""
    guesses, assets = [], []
    for index, room in enumerate(rooms):
        if room.fill_class in CLASSIFIED_FILLS:
            label, confidence = model.rooms.predict(room_tokens(room, px_per_m, level, len(rooms)))
            sure = confidence >= ROOM_CONFIDENCE and label != GENERIC
            guesses.append(RoomGuess(label if sure else GENERIC, confidence, sure))
            context = label if confidence >= ROOM_CONFIDENCE else None
        else:
            guesses.append(RoomGuess(GENERIC, 0.0, False))
            context = asset_context(room.fill_class)
        for glyph, (key, rank) in zip(room.glyphs, glyph_ranks(room.glyphs, px_per_m), strict=True):
            found = model.assets.predict(key, context, rank)
            if found is None or found[1] < ASSET_CONFIDENCE:
                continue
            width, depth = key_footprint(key)
            assets.append(
                AssetGuess(
                    found[0], CATEGORY[glyph.colour], glyph.x, glyph.y, width, depth, glyph.angle, index, found[1]
                )
            )
    return guesses, assets


# ---------- the hook: what build_from_plan and _rebuild call ----------

_MODEL_CACHE: dict[str, Model | None] = {}


def default_model() -> Model | None:
    if "model" not in _MODEL_CACHE:
        _MODEL_CACHE["model"] = Model.load()
    return _MODEL_CACHE["model"]


def _safe_text(path: Path | None) -> str | None:
    from building_agent.level4.svg_read import MAX_SVG_BYTES, UNSAFE

    try:
        if path is None or path.stat().st_size > MAX_SVG_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return None if UNSAFE.search(text) else text


def plan_furniture(extraction, image: Path, uploads_root: Path, scale, level: int, model: Model | None = None):
    """(extraction with room types, names and `plan_assets` filled from the furniture glyphs, one note for the card).

    Only plain rooms whose type is still generic are touched, and only above ROOM_CONFIDENCE; everything else stays
    as it was. A plan without furniture glyphs (or no model file) comes back unchanged with an empty note."""
    from dataclasses import replace

    from building_agent.level4.plan_files import compose_names, find_sibling

    model = model or default_model()
    text = _safe_text(find_sibling(image, uploads_root, ".svg"))
    glyphs = read_glyphs(text) if text and model is not None else []
    if not glyphs:
        return extraction, ""
    px_per_m = 1 / scale.metres_per_px
    polygons = [room.polygon_px for room in extraction.rooms]
    fills = [room.fill or "" for room in extraction.rooms]
    held = glyphs_by_room(polygons, glyphs)
    flags = corridor_flags(polygons, fills, px_per_m)
    inputs = [
        RoomInput(room.polygon_px, room.ref, fill, found, flag)
        for room, fill, found, flag in zip(extraction.rooms, fills, held, flags, strict=True)
    ]
    guesses, assets = infer_floor(inputs, px_per_m, level, model)
    rooms, typed, plain = [], 0, 0
    for room, fill, guess in zip(extraction.rooms, fills, guesses, strict=True):
        plain += fill in CLASSIFIED_FILLS
        if guess.guessed and room.room_type == GENERIC:
            room = replace(room, room_type=guess.room_type)
            typed += 1
        rooms.append(room)
    meta = model.meta or {}
    accuracy = f" (about {meta['room_precision']:.0%} right on kit buildings)" if "room_precision" in meta else ""
    note = (
        f"Furniture drawn in the plan ({len(glyphs)} pieces): {typed} of {plain} plain rooms got a room type from it"
        f"{accuracy}, the others stay generic; {len(assets)} items listed (sure enough only)."
    )
    return compose_names(replace(extraction, rooms=rooms, plan_assets=assets)), note


def attach_plan_assets(building: dict, floor_inputs) -> int:
    """Add the assets of every floor input (px guesses on its extraction) to `building["assets"]`, source 'plan'.
    An asset goes to the smallest space of its floor that holds its centre; one outside every space is dropped."""
    from building_agent.level4.convert import pixel_to_metres

    floor_ids = {floor["level"]: floor["id"] for floor in building["floors"]}
    added = 0
    for item in floor_inputs:
        guesses = getattr(item.extraction, "plan_assets", None)
        floor_id = floor_ids.get(item.level)
        if not guesses or floor_id is None:
            continue
        to_m = pixel_to_metres(item.extraction, item.scale.metres_per_px)
        spaces = sorted(
            (
                (Polygon(space["polygon"]), space)
                for space in building["spaces"]
                if space["floor_id"] == floor_id and len(space["polygon"]) >= 3
            ),
            key=lambda pair: pair[0].area,
        )
        per_space: Counter[tuple[str, str]] = Counter()
        for guess in guesses:
            x, y = to_m(guess.x_px, guess.y_px)
            point = Point(x, y)
            space = next((s for shape, s in spaces if shape.is_valid and shape.contains(point)), None)
            if space is None:
                continue
            label = guess.asset_type.replace("_", " ").capitalize()
            where = space.get("ref") or space["name"]
            per_space[(space["id"], guess.asset_type)] += 1
            number = per_space[(space["id"], guess.asset_type)]
            added += 1
            building["assets"].append(
                {
                    "id": f"{building['building']['id']}-P{len(building['assets']) + 1:05d}",
                    "name": f"{label} {where}" + ("" if number == 1 else f"-{chr(64 + min(number, 26))}"),
                    "category": guess.category,
                    "type": guess.asset_type,
                    "space_id": space["id"],
                    "floor_id": floor_id,
                    "position": [round(x, 3), round(y, 3)],
                    "footprint": {
                        "width_m": guess.width_m,
                        "depth_m": guess.depth_m,
                        "rotation_deg": round((-guess.rotation_deg) % 180, 1),
                    },
                    "source": "plan",
                }
            )
    return added
