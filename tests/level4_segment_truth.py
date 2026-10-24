"""Ground truth for room segmentation: true room polygons in the pixel frame of a kit plan image.

The kit writes floor_<n>.svg next to the png (matplotlib, same drawing, 72 dpi points vs 100 dpi pixels). The room
patches come in the order of building.json spaces, so an exact affine fit from metres to pixels is possible."""

import re
from pathlib import Path

import numpy as np

from tests.level4_helpers import DATA_DEV, load_building

PATCH = re.compile(r'<g id="patch_\d+">\s*<path d="([^"]+)"[^>]*style="fill: (#[0-9a-f]{6})')
PNG_PER_PT = 100 / 72


def _svg_rooms(svg: Path) -> list[np.ndarray]:
    rooms = []
    for path, fill in PATCH.findall(svg.read_text(encoding="utf-8")):
        numbers = np.array(re.findall(r"-?\d+\.?\d*", path), dtype=float)
        if len(numbers) % 2 or len(numbers) < 6 or fill == "#ffffff":
            continue
        rooms.append(numbers.reshape(-1, 2) * PNG_PER_PT)
    return rooms


def truth_in_image(building_id: str, level: int) -> list[dict] | None:
    """True spaces of one floor with `polygon_px` in the plain png frame, or None if the svg does not line up."""
    building = load_building(building_id)
    floor = next(item for item in building["floors"] if item["level"] == level)
    spaces = [space for space in building["spaces"] if space["floor_id"] == floor["id"]]
    svg = DATA_DEV / building_id / f"floor_{level}.svg"
    if not svg.exists():
        return None
    patches = _svg_rooms(svg)
    if len(patches) < len(spaces):
        return None
    patches = patches[: len(spaces)]
    metres = np.vstack([np.array(space["polygon"]) for space in spaces])
    pixels = np.vstack([patch[: len(space["polygon"])] if len(patch) >= len(space["polygon"]) else patch for patch, space in zip(patches, spaces)])
    if len(metres) != len(pixels):
        return None
    design = np.column_stack([metres[:, 0], -metres[:, 1], np.ones(len(metres))])
    scale_x, *_ = np.linalg.lstsq(design[:, [0, 2]], pixels[:, 0], rcond=None)
    scale_y, *_ = np.linalg.lstsq(design[:, [1, 2]], pixels[:, 1], rcond=None)
    if abs(scale_x[0] - scale_y[0]) > 1e-3 * abs(scale_x[0]):
        return None
    fitted = np.column_stack([metres[:, 0] * scale_x[0] + scale_x[1], -metres[:, 1] * scale_y[0] + scale_y[1]])
    if np.abs(fitted - pixels).max() > 2.0:
        return None
    out = []
    for space in spaces:
        points = np.array(space["polygon"])
        px = np.column_stack([points[:, 0] * scale_x[0] + scale_x[1], -points[:, 1] * scale_y[0] + scale_y[1]])
        out.append({**space, "polygon_px": px.tolist()})
    return out


def image_path(building_id: str, level: int) -> Path:
    return DATA_DEV / building_id / f"floor_{level}_plain.png"
