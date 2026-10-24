import json
from functools import cache
from pathlib import Path

from starter_agent.building_map import BuildingMap

DATA = Path("data")
LABELLED_SPLITS = ("train", "dev")


WALKS_CACHE: dict[Path, dict] = {}


@cache
def load_map(building_dir: str) -> BuildingMap:
    """One map per building and process; the walking lengths are computed once per building."""
    return BuildingMap.load_cached(Path(building_dir), WALKS_CACHE)


def labelled_questions(kind: str) -> list[tuple[str, dict]]:
    """(building directory, question) for every train/dev question of one kind."""
    found = []
    for split in LABELLED_SPLITS:
        for path in sorted((DATA / split).glob("*/questions.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    question = json.loads(line)
                    if question["kind"] == kind:
                        found.append((str(path.parent), question))
    return found
