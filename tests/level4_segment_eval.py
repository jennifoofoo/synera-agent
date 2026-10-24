"""Measure room segmentation against the true polygons of the dev floors (offline).

  uv run python -m tests.level4_segment_eval            # every dev floor, table per source
"""

import statistics
import sys

from shapely.geometry import Polygon

from building_agent.level4.segment import SegmentResult, segment_rooms
from tests.level4_helpers import DATA_DEV, MATCH_MIN_IOU, load_building
from tests.level4_segment_truth import image_path, truth_in_image

MERGE_SHARE = 0.5  # of a true room that must lie inside one region to count as part of it


def source_of(building_id: str) -> str:
    return building_id.split("-")[0].replace("proc", "procedural")


def all_floors() -> list[tuple[str, int]]:
    floors = []
    for folder in sorted(DATA_DEV.iterdir()):
        if (folder / "building.json").exists():
            floors += [(folder.name, item["level"]) for item in load_building(folder.name)["floors"]]
    return [floor for floor in floors if image_path(*floor).exists()]


def iou_match(true_shapes: list[Polygon], found_shapes: list[Polygon]) -> list[tuple[int, int, float]]:
    """Greedy one-to-one by IoU (same threshold as tests.level4_helpers.match_rooms): (true idx, found idx, iou)."""
    pairs = []
    for i, truth in enumerate(true_shapes):
        for j, found in enumerate(found_shapes):
            if truth.intersects(found):
                union = truth.union(found).area
                iou = truth.intersection(found).area / union if union else 0.0
                if iou >= MATCH_MIN_IOU:
                    pairs.append((iou, i, j))
    used_i, used_j, out = set(), set(), []
    for iou, i, j in sorted(pairs, reverse=True):
        if i not in used_i and j not in used_j:
            used_i.add(i)
            used_j.add(j)
            out.append((i, j, iou))
    return out


def measure_segment(true_spaces: list[dict], segment: SegmentResult) -> dict:
    true_shapes = [Polygon(space["polygon_px"]).buffer(0) for space in true_spaces]
    found = [region.shape.buffer(0) for region in segment.regions]
    matches = iou_match(true_shapes, found)
    ious = [iou for _, _, iou in matches]
    area_errors = [abs(found[j].area - true_shapes[i].area) / true_shapes[i].area for i, j, _ in matches]
    merges = 0
    for shape in found:
        inside = sum(
            1 for truth in true_shapes if truth.area and shape.intersection(truth).area / truth.area >= MERGE_SHARE
        )
        merges += inside >= 2
    return {
        "true": len(true_shapes),
        "found": len(found),
        "matched": len(matches),
        "recall": len(matches) / len(true_shapes) if true_shapes else 1.0,
        "precision": len(matches) / len(found) if found else 0.0,
        "ious": ious,
        "area_errors": area_errors,
        "missing": len(true_shapes) - len(matches),
        "merges": merges,
        "seconds": segment.seconds,
    }


def run(floors: list[tuple[str, int]]) -> list[dict]:
    rows = []
    for building_id, level in floors:
        truth = truth_in_image(building_id, level)
        if truth is None:
            continue
        row = measure_segment(truth, segment_rooms(image_path(building_id, level)))
        rows.append({"floor": f"{building_id}:{level}", "source": source_of(building_id), **row})
    return rows


def summarise(rows: list[dict]) -> list[str]:
    lines = [
        "| Source | Floors | True rooms | Recall | Precision | IoU median | Area err median | Floors with a missed room "
        "| Regions merging 2 true rooms | Seconds median (max) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for source in sorted({row["source"] for row in rows}) + ["all"]:
        part = [row for row in rows if source in ("all", row["source"])]
        true = sum(row["true"] for row in part)
        ious = [x for row in part for x in row["ious"]]
        errors = [x for row in part for x in row["area_errors"]]
        found = sum(row["found"] for row in part)
        matched = sum(row["matched"] for row in part)
        seconds = [row["seconds"] for row in part]
        lines.append(
            f"| {source} | {len(part)} | {true} | {matched / true:.3f} | {matched / found:.3f} "
            f"| {statistics.median(ious):.3f} | {statistics.median(errors):.1%} "
            f"| {sum(row['missing'] > 0 for row in part)} | {sum(row['merges'] for row in part)} "
            f"| {statistics.median(seconds):.2f} ({max(seconds):.2f}) |"
        )
    return lines


if __name__ == "__main__":
    result = run(all_floors())
    print("\n".join(summarise(result)))
    if "-v" in sys.argv:
        for row in sorted(result, key=lambda r: r["recall"]):
            print(row["floor"], row["true"], row["found"], f"{row['recall']:.2f} {row['precision']:.2f}", row["merges"])
