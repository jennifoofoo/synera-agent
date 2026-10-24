"""Draw one floor of a building.json in foreign drawing styles, to stress-test the Level 4 pipeline.

The kit draws flat coloured rooms with coloured dot markers. Real architect plans look different: thin black walls,
hatching, door swing arcs, dimension chains, scans. These renders are SYNTHETIC (our own drawing of known truth), so
the exact metres-to-pixels transform is known and saved in the result.

  uv run python scripts/render_plan_styles.py --buildings resplan-439 --styles lines,scan

Styles: lines, hatched, dims, scan, lowres. Everything is seeded and deterministic."""

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polylabel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STYLES = ("lines", "hatched", "dims", "scan", "lowres")
FLOORS = [
    ("proc-campus-dev-000", 0),
    ("proc-factory-dev-003", 0),
    ("resplan-439", 0),
    ("resplan-1465", 0),
    ("swiss-31", 0),
    ("osm-way27326387", 0),
]
OUT_DIRECTORY = Path("agent_output") / "level4_styles"
DATA_DEV = Path("data/dev")
LONG_SIDE_PX_AT_100_DPI = 1400
SCAN_ROTATION_DEG = 1.5
LOWRES_FACTOR = 0.4
SCAN_JPEG_QUALITY = 70
SEED = 7
INK, PAPER = 0, 255


@dataclass
class Render:
    """A drawn image plus the exact truth in its pixel frame."""

    path: Path
    style: str
    building_id: str
    level: int
    width_px: int
    height_px: int
    matrix: np.ndarray  # 3x3: [x_m, y_m, 1] -> [x_px, y_px, 1], y of the image points down
    px_per_m: float
    spaces: list[dict] = field(default_factory=list)  # building.json spaces of the floor plus polygon_px
    openings: list[dict] = field(default_factory=list)  # building.json openings of the floor plus position_px
    scale_bar: tuple[float, float] | None = None  # (length in px, length in metres) if one is printed

    def to_px(self, x: float, y: float) -> tuple[float, float]:
        px = self.matrix @ np.array([x, y, 1.0])
        return float(px[0]), float(px[1])


def _load(building) -> dict:
    if isinstance(building, dict):
        return building
    path = Path(building)
    if path.is_dir():
        path = path / "building.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _font(size: int):
    return ImageFont.load_default(size=max(size, 8))


def _unit(vector: np.ndarray) -> np.ndarray:
    length = float(np.hypot(*vector))
    return vector / length if length else np.array([1.0, 0.0])


def _wall_direction(point: tuple[float, float], polygons: list[Polygon]) -> np.ndarray:
    """Unit direction of the polygon edge nearest to `point`."""
    best, direction = math.inf, np.array([1.0, 0.0])
    for polygon in polygons:
        ring = list(polygon.exterior.coords)
        for a, b in itertools.pairwise(ring):
            distance = LineString([a, b]).distance(Point(point))
            if distance < best:
                best, direction = distance, _unit(np.array(b) - np.array(a))
    return direction


def _arrow(draw: ImageDraw.ImageDraw, start: np.ndarray, end: np.ndarray, width: int = 2) -> None:
    draw.line([tuple(start), tuple(end)], fill=INK, width=width)
    d = _unit(end - start)
    n = np.array([-d[1], d[0]])
    head = 9
    draw.polygon([tuple(end), tuple(end - d * head + n * head / 2), tuple(end - d * head - n * head / 2)], fill=INK)


def _draw_stair(draw: ImageDraw.ImageDraw, polygon: Polygon) -> None:
    rectangle = polygon.minimum_rotated_rectangle
    corners = np.array(rectangle.exterior.coords)[:4]
    sides = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    long_side = max(sides, key=lambda s: np.hypot(*(s[1] - s[0])))
    along = _unit(long_side[1] - long_side[0])
    across = np.array([-along[1], along[0]])
    length = float(np.hypot(*(long_side[1] - long_side[0])))
    centre = np.array(rectangle.centroid.coords[0])
    reach = float(np.hypot(*(corners[2] - corners[0])))
    step = 7.0
    for k in range(1, int(length // step)):
        origin = centre - along * length / 2 + along * k * step
        cut = LineString([tuple(origin - across * reach), tuple(origin + across * reach)]).intersection(polygon)
        if not cut.is_empty and cut.geom_type == "LineString":
            draw.line(list(cut.coords), fill=INK, width=1)
    _arrow(draw, centre - along * length * 0.35, centre + along * length * 0.35)


def _draw_lift(draw: ImageDraw.ImageDraw, polygon: Polygon) -> None:
    corners = [tuple(c) for c in polygon.minimum_rotated_rectangle.exterior.coords][:4]
    draw.line(corners + [corners[0]], fill=INK, width=2)
    draw.line([corners[0], corners[2]], fill=INK, width=1)
    draw.line([corners[1], corners[3]], fill=INK, width=1)


def _draw_text(image: Image.Image, text: str, xy: tuple[float, float], size: int, angle: int = 0) -> None:
    font = _font(size)
    if angle == 0:
        ImageDraw.Draw(image).text(xy, text, fill=INK, font=font, anchor="mm")
        return
    box = ImageDraw.Draw(image).textbbox((0, 0), text, font=font)
    layer = Image.new("L", (box[2] + 6, box[3] + 6), PAPER)
    ImageDraw.Draw(layer).text((3, 3), text, fill=INK, font=font)
    layer = layer.rotate(angle, expand=True, fillcolor=PAPER)
    x, y = int(xy[0] - layer.width / 2), int(xy[1] - layer.height / 2)
    region = image.crop((x, y, x + layer.width, y + layer.height))
    image.paste(Image.fromarray(np.minimum(np.asarray(region), np.asarray(layer))), (x, y))


def _hatch_pattern(width: int, height: int, period: int = 4) -> np.ndarray:
    ys, xs = np.mgrid[0:height, 0:width]
    return ((xs + ys) % period < period // 2 + 1).astype(np.uint8) * 255


def _walls(size: tuple[int, int], polygons: list[Polygon], hatched: bool) -> Image.Image:
    """Ink layer (L, 255 = ink) with the wall outlines or the hatched wall bands."""
    thin = Image.new("L", size, 0)
    thin_draw = ImageDraw.Draw(thin)
    for polygon in polygons:
        ring = [tuple(c) for c in polygon.exterior.coords]
        thin_draw.line(ring, fill=255, width=2, joint="curve")
    if not hatched:
        return thin
    band = Image.new("L", size, 0)
    band_draw = ImageDraw.Draw(band)
    for polygon in polygons:
        band_draw.line([tuple(c) for c in polygon.exterior.coords], fill=255, width=9, joint="curve")
    pattern = _hatch_pattern(*size)
    return Image.fromarray(np.maximum(np.asarray(thin), np.minimum(np.asarray(band), pattern)))


def _nice_length(max_m: float) -> float:
    options = [0.5, 1, 2, 5, 10, 20, 50]
    return max([o for o in options if o <= max_m], default=0.5)


def _breakpoints(values: list[float], low: float, high: float, gap: float = 0.6, limit: int = 9) -> list[float]:
    kept = [low]
    for value in sorted({round(v, 2) for v in values}):
        if value - kept[-1] >= gap and high - value >= gap:
            kept.append(value)
    kept.append(high)
    while len(kept) > limit:
        del kept[1 + (len(kept) - 2) // 2]
    return kept


def _dimension_chains(image: Image.Image, render: "Render", rooms_m: list[Polygon]) -> None:
    draw = ImageDraw.Draw(image)
    ppm = render.px_per_m
    xs = [x for p in rooms_m for x in (p.bounds[0], p.bounds[2])]
    ys = [y for p in rooms_m for y in (p.bounds[1], p.bounds[3])]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    left, bottom = render.to_px(x0, y0)[0], render.to_px(x0, y0)[1]
    size = 13
    chain_y, overall_y = bottom + 38, bottom + 78
    cuts = _breakpoints(xs, x0, x1)
    for line_y, points in ((chain_y, cuts), (overall_y, [x0, x1])):
        px = [render.to_px(x, y0)[0] for x in points]
        draw.line([(px[0], line_y), (px[-1], line_y)], fill=INK, width=1)
        for u in px:
            draw.line([(u, bottom + 8), (u, line_y + 5)], fill=INK, width=1)
            draw.line([(u - 5, line_y + 5), (u + 5, line_y - 5)], fill=INK, width=2)
        for (a, b), (ua, ub) in zip(itertools.pairwise(points), itertools.pairwise(px)):
            if ub - ua > 30:
                _draw_text(image, f"{b - a:.2f}", ((ua + ub) / 2, line_y - 9), size)
    chain_x, overall_x = left - 38, left - 78
    cuts = _breakpoints(ys, y0, y1)
    for line_x, points in ((chain_x, cuts), (overall_x, [y0, y1])):
        py = [render.to_px(x0, y)[1] for y in points]
        draw.line([(line_x, py[0]), (line_x, py[-1])], fill=INK, width=1)
        for v in py:
            draw.line([(left - 8, v), (line_x - 5, v)], fill=INK, width=1)
            draw.line([(line_x - 5, v + 5), (line_x + 5, v - 5)], fill=INK, width=2)
        for (a, b), (va, vb) in zip(itertools.pairwise(points), itertools.pairwise(py)):
            if va - vb > 30:
                _draw_text(image, f"{b - a:.2f}", (line_x - 10, (va + vb) / 2), size, angle=90)
    length_m = _nice_length(0.18 * (x1 - x0))
    length_px = length_m * ppm
    base_x, base_y = image.width - 40 - length_px, image.height - 30
    half = length_px / 2
    draw.rectangle([base_x, base_y, base_x + half, base_y + 6], fill=INK, outline=INK)
    draw.rectangle([base_x + half, base_y, base_x + length_px, base_y + 6], fill=PAPER, outline=INK)
    _draw_text(image, "0", (base_x, base_y - 9), size)
    _draw_text(image, f"{length_m:g} m", (base_x + length_px, base_y - 9), size)
    render.scale_bar = (length_px, length_m)


def _rotation(theta_deg: float, width: int, height: int) -> np.ndarray:
    """Matrix of PIL Image.rotate(theta_deg) (counter-clockwise on screen) around the image centre, as px -> px."""
    t = math.radians(theta_deg)
    c, s = math.cos(t), math.sin(t)
    cx, cy = width / 2, height / 2
    return np.array([[c, s, cx - c * cx - s * cy], [-s, c, cy + s * cx - c * cy], [0, 0, 1.0]])


def render(building, floor_level: int, style: str, out_png, dpi: int = 100) -> Render:
    """Draw one floor in `style` and write it to `out_png` (scan is always written as .jpg). Returns the truth."""
    if style not in STYLES:
        raise ValueError(f"style must be one of {STYLES}")
    data = _load(building)
    floor = next(f for f in data["floors"] if f["level"] == floor_level)
    spaces = [s for s in data["spaces"] if s["floor_id"] == floor["id"]]
    openings = [o for o in data["openings"] if o["floor_id"] == floor["id"]]
    xs = [x for s in spaces for x, _ in s["polygon"]]
    ys = [y for s in spaces for _, y in s["polygon"]]
    min_x, max_y = min(xs), max(ys)
    ppm = LONG_SIDE_PX_AT_100_DPI * dpi / 100 / max(max(xs) - min_x, max_y - min(ys))
    margin = round(170 * dpi / 100) if style == "dims" else round(60 * dpi / 100)
    width = math.ceil((max(xs) - min_x) * ppm) + 2 * margin
    height = math.ceil((max_y - min(ys)) * ppm) + 2 * margin
    matrix = np.array([[ppm, 0, margin - ppm * min_x], [0, -ppm, margin + ppm * max_y], [0, 0, 1.0]])
    result = Render(Path(out_png), style, data["building"]["id"], floor_level, width, height, matrix, ppm)
    polygons_px = {s["id"]: Polygon([result.to_px(x, y) for x, y in s["polygon"]]).buffer(0) for s in spaces}
    walls = _walls((width, height), list(polygons_px.values()), hatched=style == "hatched")
    erase = ImageDraw.Draw(walls)
    marks: list = []
    for opening in openings:
        point = result.to_px(*opening["position"])
        adjacent = [polygons_px[i] for i in opening["space_ids"] if i in polygons_px]
        d = _wall_direction(point, adjacent)
        n = np.array([-d[1], d[0]])
        w = max(opening["width_m"] * ppm, 10.0)
        p = np.array(point)
        entrance = opening["kind"] == "entrance"
        reach = w * (0.65 if entrance else 0.5)
        erase.line([tuple(p - d * reach), tuple(p + d * reach)], fill=0, width=14 if style == "hatched" else 6)
        marks.append((opening["kind"], p, d, n, w, adjacent))
    image = Image.new("L", (width, height), PAPER)
    image.paste(INK, mask=walls)
    draw = ImageDraw.Draw(image)
    for kind, p, d, n, w, adjacent in marks:
        half = w / 2
        if kind == "entrance":
            for end in (p - d * w * 0.65, p + d * w * 0.65):
                draw.line([tuple(end - n * 6), tuple(end + n * 6)], fill=INK, width=4)
            continue
        draw.line([tuple(p - d * half - n * 4), tuple(p - d * half + n * 4)], fill=INK, width=1)
        draw.line([tuple(p + d * half - n * 4), tuple(p + d * half + n * 4)], fill=INK, width=1)
        if kind != "door" or not adjacent:
            continue
        probe = p + n * 4
        if not adjacent[0].contains(Point(tuple(probe))):
            n = -n
        hinge, tip = p - d * half, p - d * half + n * w
        draw.line([tuple(hinge), tuple(tip)], fill=INK, width=2)
        a1 = math.degrees(math.atan2(*(tip - hinge)[::-1]))
        a2 = math.degrees(math.atan2(*((p + d * half) - hinge)[::-1]))
        start, end = (a1, a2) if (a2 - a1) % 360 <= 180 else (a2, a1)
        box = [hinge[0] - w, hinge[1] - w, hinge[0] + w, hinge[1] + w]
        draw.arc(box, start, end, fill=INK, width=1)
    size = round(14 * dpi / 100)
    for space in spaces:
        polygon = polygons_px[space["id"]]
        if polygon.is_empty or polygon.geom_type != "Polygon":
            continue
        if space["type"] == "stair":
            _draw_stair(draw, polygon)
        elif space["type"] == "lift":
            _draw_lift(draw, polygon)
        elif space.get("ref") and math.sqrt(polygon.area) > 18:
            _draw_text(image, str(space["ref"]), tuple(polylabel(polygon, 1.0).coords[0]), size)
    if style == "hatched":
        for asset in [a for a in data["assets"] if a["floor_id"] == floor["id"] and a["category"] == "furniture"][:300]:
            fp = asset["footprint"]
            cx, cy = result.to_px(*asset["position"])
            angle = math.radians(fp.get("rotation_deg", 0.0))
            hw, hd = fp["width_m"] * ppm / 2, fp["depth_m"] * ppm / 2
            corners = [
                (cx + dx * math.cos(angle) - dy * math.sin(angle), cy - (dx * math.sin(angle) + dy * math.cos(angle)))
                for dx, dy in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))
            ]
            draw.line(corners + [corners[0]], fill=110, width=1)
    if style == "dims":
        _dimension_chains(image, result, [Polygon(s["polygon"]) for s in spaces])
    if style == "scan":
        image, result = _scan(image, result)
    if style == "lowres":
        new = (round(width * LOWRES_FACTOR), round(height * LOWRES_FACTOR))
        image = image.resize(new, Image.Resampling.LANCZOS)
        result.matrix = np.diag([new[0] / width, new[1] / height, 1.0]) @ result.matrix
        result.px_per_m = ppm * LOWRES_FACTOR
    result.width_px, result.height_px = image.size
    result.path.parent.mkdir(parents=True, exist_ok=True)
    if style == "scan":
        result.path = result.path.with_suffix(".jpg")
        image.save(result.path, "JPEG", quality=SCAN_JPEG_QUALITY)
    else:
        image.save(result.path)
    result.spaces = [{**s, "polygon_px": [list(result.to_px(x, y)) for x, y in s["polygon"]]} for s in spaces]
    result.openings = [{**o, "position_px": list(result.to_px(*o["position"]))} for o in openings]
    return result


def _scan(image: Image.Image, result: Render) -> tuple[Image.Image, Render]:
    rng = np.random.default_rng(SEED)
    image = image.filter(ImageFilter.GaussianBlur(0.8))
    image = image.rotate(SCAN_ROTATION_DEG, resample=Image.Resampling.BICUBIC, fillcolor=PAPER)
    result.matrix = _rotation(SCAN_ROTATION_DEG, *image.size) @ result.matrix
    array = np.asarray(image, dtype=float) * (236 / 255)  # off-white paper
    array += rng.normal(0, 4, array.shape)
    speckle = rng.random(array.shape)
    array[speckle < 0.0015] = rng.uniform(20, 120, int((speckle < 0.0015).sum()))
    array[speckle > 0.9985] = 255
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)), result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--styles", default=",".join(STYLES))
    parser.add_argument("--buildings", default=",".join(b for b, _ in FLOORS))
    parser.add_argument("--dpi", type=int, default=100)
    args = parser.parse_args()
    levels = dict(FLOORS)
    for style in args.styles.split(","):
        for building_id in args.buildings.split(","):
            level = levels.get(building_id, 0)
            out = OUT_DIRECTORY / style / f"{building_id}-L{level}.png"
            made = render(DATA_DEV / building_id / "building.json", level, style, out, args.dpi)
            print(made.path, made.width_px, made.height_px)


if __name__ == "__main__":
    main()
