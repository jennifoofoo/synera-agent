"""Shared plausibility limits for dimensions in a building.

Two readers use this module:
- building_agent/level4/validate.py checks freshly converted floor plans (strict human-scale limits).
- building_agent/preflight.py checks a finished building.json (limits widened to what the kit data really contains,
  so real kit buildings do not warn).

The strict constants below are the level4 ones, unchanged. The PREFLIGHT_* ones were derived from all 200 kit
buildings in data/ (train, dev, test; measured 2026-10-25) and sit just outside the observed extremes:
- door kind "door": 0.41 .. 3.0 m (Swiss Dwellings has narrow cupboard doors and 3 m patio doors)
- kind "entrance": up to 5.0 m (factory gates); kind "opening" (open passage, no leaf): up to 20.0 m (factory bays)
- room area: 0.51 m2 (small closet) .. 2524 m2 (OSM hall mapped as plain "room"); hall/corridor/outdoor up to 73425 m2
  (one OSM corridor that is really the whole ground plan)
- asset footprint side: 0.06 .. 6.0 m (conveyor)
- storey rise between floors: 3.0 .. 6.0 m, which drives the length of stairs (2 m per m) and lifts
Anything beyond these is a typo, a unit mix-up (mm instead of m) or a broken import, not a real building."""

MIN_AREA_M2 = 1.0
PLAUSIBLE_AREA_M2 = (2.0, 300.0)
PLAUSIBLE_DOOR_WIDTH_M = (0.7, 2.5)
PLAUSIBLE_FOOTPRINT_M = (4.0, 400.0)
LARGE_ROOM_TYPES = {"hall", "outdoor", "corridor"}

PREFLIGHT_DOOR_WIDTH_M = (0.3, 3.5)  # kind "door"
PREFLIGHT_WIDE_OPENING_WIDTH_M = (0.3, 25.0)  # kinds "entrance" and "opening" (gates, factory bays)
PREFLIGHT_AREA_M2 = (0.5, 3000.0)  # ordinary rooms
PREFLIGHT_LARGE_AREA_M2 = (0.5, 100_000.0)  # LARGE_ROOM_TYPES: halls, corridors, outdoor
PREFLIGHT_ASSET_SIDE_M = (0.05, 10.0)  # width and depth of an asset footprint
PREFLIGHT_STOREY_RISE_M = (2.0, 8.0)  # elevation step between neighbouring stops of a stair or lift
