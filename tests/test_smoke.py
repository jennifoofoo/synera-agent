from pathlib import Path

from starter_agent.building_map import BuildingMap

DEV = Path("data/dev")


def test_every_dev_building_loads():
    buildings = sorted(DEV.glob("*/building.json"))
    assert buildings, "data/dev is missing, see README setup"
    for path in buildings:
        BuildingMap.load(path)
