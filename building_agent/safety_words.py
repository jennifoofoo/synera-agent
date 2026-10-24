"""Safety equipment words (English and German) mapped to the four asset types, and the honest 'none here' answer.

Only whole phrases count, so everyday single words never match by accident ("first", "aid", "wash", "fire" alone
do nothing). find_nearest calls `safety_query` before its own matching."""

import re
import unicodedata
from collections import Counter

from starter_agent.building_map import BuildingMap, MapError

SAFETY_TYPES = {
    "fire_extinguisher": "fire extinguisher",
    "eyewash_station": "eyewash station",
    "defibrillator": "defibrillator",
    "shower": "shower",
}

# Folded phrases (lower case, ue/oe/ae for umlauts, ss for sharp s) -> asset type.
PHRASES = {
    "fire extinguisher": "fire_extinguisher",
    "fire extinguishers": "fire_extinguisher",
    "extinguisher": "fire_extinguisher",
    "feuerloescher": "fire_extinguisher",
    "handfeuerloescher": "fire_extinguisher",
    "defibrillator": "defibrillator",
    "defibrillators": "defibrillator",
    "defibrillator holen": "defibrillator",
    "defib": "defibrillator",
    "defi": "defibrillator",
    "aed": "defibrillator",
    "first aid": "defibrillator",
    "erste hilfe": "defibrillator",
    "eyewash": "eyewash_station",
    "eyewash station": "eyewash_station",
    "eye wash": "eyewash_station",
    "eye wash station": "eyewash_station",
    "eye shower": "eyewash_station",
    "augendusche": "eyewash_station",
    "augenspuelstation": "eyewash_station",
    "augenspuelung": "eyewash_station",
    "notdusche": "shower",
    "emergency shower": "shower",
    "safety shower": "shower",
    "shower": "shower",
    "showers": "shower",
    "dusche": "shower",
}
FILLER = {
    "the", "a", "an", "nearest", "closest", "next", "where", "is", "are", "i", "need", "to", "find", "me",
    "der", "die", "das", "den", "dem", "ein", "eine", "naechste", "naechster", "naechsten", "wo", "ist", "brauche",
    "quickly", "schnell", "please", "bitte", "nearby", "here", "hier",
}  # fmt: skip


def fold(text: str) -> str:
    text = str(text or "").lower().replace("ß", "ss")
    for umlaut, plain in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(umlaut, plain)
    text = unicodedata.normalize("NFKD", text)
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in text if not unicodedata.combining(c))))


def safety_type(text: str) -> str | None:
    """The asset type a phrase stands for, or None. The whole phrase (minus filler words) must be a known one."""
    words = [word for word in fold(text).split() if word not in FILLER]
    return PHRASES.get(" ".join(words)) if words and len(words) <= 4 else None


def present_types(bm: BuildingMap) -> Counter:
    counts = Counter(asset["type"] for asset in bm.assets.values())
    return Counter({kind: counts[kind] for kind in SAFETY_TYPES if counts[kind]})


def safety_query(bm: BuildingMap, what: str) -> str:
    """Words find_nearest should search for: the asset type when `what` is a safety phrase, else `what` unchanged.

    Raises MapError with the honest 'there is none in this building' answer when that type does not exist here."""
    kind = safety_type(what)
    if kind is None:
        return what
    have = present_types(bm)
    if kind in have:
        return kind
    label = SAFETY_TYPES[kind]
    exists = ", ".join(f"{SAFETY_TYPES[k]} ({n})" for k, n in have.items())
    rest = (
        f" Safety equipment that does exist here: {exists}."
        if exists
        else " None of the safety equipment types is in this data."
    )
    raise MapError(
        f"There is no {label} in this building.{rest} Say exactly that, with no question and no advice of your own."
    )
