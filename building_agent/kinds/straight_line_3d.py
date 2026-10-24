import math

from building_agent.geometry import space_polygon
from building_agent.registry import Kind
from starter_agent.building_map import BuildingMap


def _centre(bm: BuildingMap, space_id: str) -> tuple[float, float, float]:
    centroid = space_polygon(bm, space_id).centroid
    elevation = bm.floors[bm.spaces[space_id]["floor_id"]]["elevation_m"]
    return (centroid.x, centroid.y, elevation)


def straight_line_3d(bm: BuildingMap, first: str, second: str) -> dict:
    """Euclidean distance between the floor-plan centroids of two rooms, each at its floor's elevation."""
    a = _centre(bm, first)
    b = _centre(bm, second)
    return {
        "distance_m": round(math.dist(a, b), 2),
        "first": {"x": round(a[0], 2), "y": round(a[1], 2), "elevation_m": a[2]},
        "second": {"x": round(b[0], 2), "y": round(b[1], 2), "elevation_m": b[2]},
    }


KIND = Kind(
    name="straight_line_3d",
    fn=straight_line_3d,
    description=(
        "Straight-line (3D, through walls and floors) distance in metres between the centres of two rooms "
        "`first` and `second` (space ids): each room's floor-plan centroid at its floor's elevation. "
        "Returns distance_m plus both centres."
    ),
)
