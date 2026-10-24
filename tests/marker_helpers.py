"""Helpers for the marker tests: drawn-marker ground truth from the kit SVGs and detection scoring. No API."""

import re
from pathlib import Path

from building_agent.level4.markers import Markers

DATA_DEV = Path("data/dev")
SVG_TO_PX = 100 / 72  # the kit renders its figures at 100 dpi from point-based SVGs
FILL_KIND = {"#8b4513": "door", "#9e9e9e": "opening", "#d32f2f": "entrance"}
MATCH_PX = 4.0
_USE = re.compile(r'<use xlink:href="#m\w+" x="([\d.]+)" y="([\d.]+)" style="fill: (#\w+)')


def drawn_markers(building_id: str, level: int) -> dict[str, list[tuple[float, float]]]:
    """Where the kit drew door, opening and entrance markers, in pixels of floor_<level>_plain.png."""
    text = (DATA_DEV / building_id / f"floor_{level}.svg").read_text(encoding="utf-8")
    truth: dict[str, list[tuple[float, float]]] = {kind: [] for kind in FILL_KIND.values()}
    for x, y, fill in _USE.findall(text):
        if fill in FILL_KIND:
            truth[FILL_KIND[fill]].append((float(x) * SVG_TO_PX, float(y) * SVG_TO_PX))
    return truth


def score(found: Markers, truth: dict[str, list[tuple[float, float]]]) -> dict[str, dict[str, float]]:
    """Recall and precision per marker kind; each detection may match one drawn marker within MATCH_PX."""
    result = {}
    for kind, points in truth.items():
        free = list(points)
        hits = 0
        for marker in found.of(kind):
            best = min(free, key=lambda p: (p[0] - marker.x) ** 2 + (p[1] - marker.y) ** 2, default=None)
            if best is not None and (best[0] - marker.x) ** 2 + (best[1] - marker.y) ** 2 <= MATCH_PX**2:
                free.remove(best)
                hits += 1
        count = len(found.of(kind))
        result[kind] = {
            "recall": hits / len(points) if points else 1.0,
            "precision": hits / count if count else 1.0,
            "true": len(points),
            "found": count,
        }
    return result
