"""The storey height of a building built from plans.

The plan images carry no height, so it comes from (1) the floors of the building.json that travels with the plans
(`elevation_m`, `height_m`), else (2) a default by building family. Stairs cost 2 m of walking per metre climbed and
lifts 1 m, so a wrong height shifts every route and 3D distance between floors. The family is guessed from the printed
room numbers and the title of the plan, and the defaults are the measured medians of the kit data (280 buildings, step
between floors): factory halls 3.5 m, campus buildings 3.8 m, osm, swiss and resplan 3.0 m. The card says that the
height is an assumption and which value was used, and `fix_draft set_floor_height` corrects it."""

import re

ZONE_REF = re.compile(r"^[A-Z]{1,3}-[A-Z]\d+")
PLAIN_REF = re.compile(r"^-?\d+\.\d+$")
RESIDENTIAL = re.compile(r"residen", re.IGNORECASE)
NAME_AND_NUMBER = re.compile(r"^\S+ \d+$")  # one word and a number, e.g. "Lehrgebaeude 030"
DEFAULT_HEIGHT_M = 3.0
FACTORY_HEIGHT_M = 3.5
CAMPUS_HEIGHT_M = 3.8


def guess_floor_height(refs: list[str], title: str = "") -> tuple[float, str]:
    """(height in metres, reason in plain words) by the building family the room numbers and the title point to."""
    refs = [ref.strip() for ref in refs if ref and ref.strip()]
    if any(ZONE_REF.match(ref) for ref in refs):
        return FACTORY_HEIGHT_M, "the zone-style room numbers look like a factory"
    if refs and all(PLAIN_REF.match(ref) for ref in refs):
        name = title.strip()
        if name and not RESIDENTIAL.search(name) and NAME_AND_NUMBER.match(name):
            return CAMPUS_HEIGHT_M, "the plain room numbers and the plan title look like a campus building"
        return DEFAULT_HEIGHT_M, "the room numbers look like a residential building"
    return DEFAULT_HEIGHT_M, "the room numbers look like a mapped building"
