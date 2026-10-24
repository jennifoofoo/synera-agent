"""From what a person wants to DO (or half remembers) to the devices of one building.

`types_for_task` maps words to device types deterministically (exact phrases, word hits, typo-tolerant fuzzy hits).
`find_for_task` finds those devices, groups them like `find_asset`, and gently corrects wrong hints (floor, room).
`describe_asset` explains a device TYPE in general terms. Nothing here knows specs, state or capacity of a unit."""

import difflib
import itertools
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cache

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.asset_catalog import ASSET_CATALOG
from building_agent.asset_knowledge import ASSET_KNOWLEDGE
from building_agent.find_tools import MAX_GROUPS, MAX_ITEMS_PER_GROUP, natural_key
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

MAX_CHARS = 300
MAX_TOKENS = 40
MAX_LOCATED = 20
FUZZY_CUTOFF = 0.8
NAME_CUTOFF = 0.75
RELATIVE_CUTOFF = 0.5
CLOSE_SHARE = 0.67
GENERAL_NOTE = (
    "General description of this type of device; nothing is known about this unit's settings, state or specifications."
)
STOP = set(
    re.split(
        r"\s+",
        "a an the i me my we you it is are be to of in on at for and or with from by this that there here some any "
        "want need would like please can could do does how where what which get go have has find show tell "
        "ich will moechte brauche mal der die das den dem ein eine einen einer und oder mit von zu im am an auf "
        "wo wie was ist es gibt kann kannst koennte bitte hier dort mir mich wir hab habe haben",
    )
)
WEAK_WORDS = {
    "turn",
    "join",
    "connect",
    "charge",
    "laden",
    "lift",
    "cool",
    "press",
    "brand",
    "fire",
    "cut",
    "heat",
    "plastic",
    "metal",
    "wood",
    "glass",
    "stone",
    "sheet",
    "part",
    "material",
    "work",
    "make",
    "put",
    "get",
    "move",
    "handle",
    "check",
    "hold",
    "give",
    "take",
    "use",
    "keep",
    "fill",
    "clean",
    "start",
    "stop",
    "bend",
    "cure",
    "belt",
    "truck",
    "trocknen",
    "messen",
}  # everyday words: never a match on their own, only inside a longer phrase
GENERIC = {"machine", "station", "table", "unit", "room", "maschine", "stand", "type"}
UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
REF = re.compile(r"\b[a-z]{1,2}-[a-z]?\d+(?:-[a-z])?\b|\b\d+\.\d+\b")
ROOM_KINDS = (
    "hall|halle|room|raum|zone|bay|lab|labor|office|buero|workshop|werkstatt|building|gebaeude|area|bereich|"
    "production|produktion|warehouse|lager|kitchen|kueche|canteen|kantine|lobby|corridor|flur"
)
GENERIC_KINDS = {
    "hall",
    "halle",
    "room",
    "raum",
    "zone",
    "bay",
    "building",
    "gebaeude",
    "area",
    "bereich",
    "production",
    "produktion",
    "warehouse",
    "lager",
}
ROOM_HINT = re.compile(
    rf"\b(?:in|im|at|bei|auf|on|inside|near|nahe)\s+(?:the\s+|der\s+|dem\s+|einer\s+|a\s+)?"
    rf"((?:{ROOM_KINDS})\b(?:\s+(?=[\w.\-]*\d)[\w.\-]+)?)"
)
ORDINAL_FLOOR = re.compile(
    r"\b(first|second|third|fourth|1st|2nd|3rd|4th|erste[nrs]?|zweite[nrs]?|dritte[nrs]?|vierte[nrs]?)\s+"
    r"(?:floor|level|stock|etage|og|obergeschoss|stockwerk)\b"
)
NUMBER_FLOOR = re.compile(r"\b(?:floor|level|og)\s*(-?\d+)\b|\b(\d+)\.?\s*(?:og|obergeschoss)\b")
AMBIGUOUS_FLOOR = re.compile(r"\b(?:etage|stock|stockwerk)\s*(\d+)\b|\b(\d+)\.?\s*(?:stock|etage|stockwerk)\b")
GROUND_FLOOR = re.compile(r"\b(?:ground floor|groundfloor|erdgeschoss|eg)\b")
BASEMENT = re.compile(r"\b(?:basement|cellar|keller|untergeschoss|ug)\b")
ORDINAL_NUMBERS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
GERMAN_ORDINALS = {"erste": 1, "zweite": 2, "dritte": 3, "vierte": 4}


# ---------- normalising ----------


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower().translate(UMLAUTS)
    return "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", fold(text))


def undouble(word: str) -> str:
    return word[:-1] if len(word) > 2 and word[-1] == word[-2] and word[-1] not in "lsz" else word


def stem(word: str) -> str:
    """Cheap symmetric stemming (applied to phrases and queries alike): plural, -ing, -ed, German -en, final e."""
    if len(word) >= 6 and word.endswith("ing"):
        word = undouble(word[:-3])
    elif len(word) >= 5 and word.endswith("ed"):
        word = undouble(word[:-2])
    elif len(word) >= 5 and word.endswith(("sses", "xes", "zes", "ches", "shes")):
        word = word[:-2]
    elif len(word) >= 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    elif len(word) >= 7 and word.endswith("en"):
        word = word[:-2]
    if len(word) >= 5 and word.endswith("e"):
        word = word[:-1]
    return word


def content_word(token: str) -> bool:
    return token not in STOP and (len(token) >= 3 or any(char.isdigit() for char in token)) and token != "000"


# ---------- phrase index ----------


@dataclass(frozen=True)
class TypeMatch:
    type: str
    score: float
    confidence: str  # "exact" (a whole phrase), "word" (a word of a phrase) or "weak" (typo-tolerant guess)
    matched: tuple[str, ...]


@dataclass(frozen=True)
class Index:
    phrases: dict
    nostop: dict
    word_types: dict
    fuzzy_types: dict
    max_len: int


@cache
def index() -> Index:
    phrases: dict[tuple, dict] = {}
    for asset_type, knowledge in ASSET_KNOWLEDGE.items():
        for phrase in (*knowledge.tasks, asset_type.replace("_", " "), ASSET_CATALOG[asset_type]["label"]):
            tokens = words(phrase)
            if tokens:
                entry = phrases.setdefault(
                    tuple(stem(token) for token in tokens), {"text": " ".join(tokens), "types": set()}
                )
                entry["types"].add(asset_type)
    word_types: dict[str, set] = defaultdict(set)
    fuzzy_types: dict[str, set] = defaultdict(set)
    nostop: dict[tuple, dict] = {}
    weak_roots = {stem(word) for word in WEAK_WORDS}
    name_roots = {
        asset_type: {
            stem(token) for token in words(asset_type.replace("_", " ") + " " + ASSET_CATALOG[asset_type]["label"])
        }
        for asset_type in ASSET_KNOWLEDGE
    }
    for key in [key for key in phrases if len(key) == 1 and key[0] in weak_roots]:
        del phrases[key]
    for key, entry in phrases.items():
        trimmed = tuple(root for token, root in zip(entry["text"].split(), key, strict=True) if token not in STOP)
        if trimmed and trimmed != key:
            merged = nostop.setdefault(trimmed, {"text": entry["text"], "types": set()})
            merged["types"] |= entry["types"]
        fuzzy_types[entry["text"]] |= entry["types"]
        for token, root in zip(entry["text"].split(), key, strict=True):
            if content_word(token) and token not in GENERIC and root not in weak_roots:
                owners = {kind for kind in entry["types"] if len(token) >= 7 or root in name_roots[kind]}
                if owners:
                    word_types[root] |= owners
                    if len(token) >= 4:
                        fuzzy_types[token] |= owners
    return Index(phrases, nostop, dict(word_types), dict(fuzzy_types), max(len(key) for key in phrases))


def analyse(text: str) -> tuple[list[TypeMatch], list[str]]:
    """Score every type against the text; also return the content words nothing could explain."""
    idx = index()
    tokens = words(REF.sub(" ", fold(text)))[:MAX_TOKENS]
    roots = [stem(token) for token in tokens]
    covered: dict[str, set[int]] = defaultdict(set)
    phrases_of: dict[str, list[str]] = defaultdict(list)
    for start in range(len(roots)):
        for length in range(min(idx.max_len, len(roots) - start), 0, -1):
            entry = idx.phrases.get(tuple(roots[start : start + length]))
            if entry:
                for asset_type in entry["types"]:
                    covered[asset_type].update(range(start, start + length))
                    if entry["text"] not in phrases_of[asset_type]:
                        phrases_of[asset_type].append(entry["text"])
    content = [
        (position, root) for position, (token, root) in enumerate(zip(tokens, roots, strict=True)) if token not in STOP
    ]
    for start in range(len(content)):
        for length in range(min(idx.max_len, len(content) - start), 1, -1):
            chunk = content[start : start + length]
            entry = idx.nostop.get(tuple(root for _, root in chunk)) or (
                idx.phrases.get(tuple(root for _, root in chunk)) if length > 1 else None
            )
            if entry:
                for asset_type in entry["types"]:
                    covered[asset_type].update(position for position, _ in chunk)
                    if entry["text"] not in phrases_of[asset_type]:
                        phrases_of[asset_type].append(entry["text"])
    explained = set().union(*covered.values()) if covered else set()
    word_score: dict[str, float] = defaultdict(float)
    word_hits: dict[str, list[str]] = defaultdict(list)
    for position, (token, root) in enumerate(zip(tokens, roots, strict=True)):
        owners = idx.word_types.get(root)
        if not owners or not content_word(token) or token in GENERIC:
            continue
        for asset_type in owners:
            if position not in covered.get(asset_type, ()):
                word_score[asset_type] += 0.9 / len(owners) ** 0.5
                word_hits[asset_type].append(token)
                explained.add(position)
    fuzzy_score: dict[str, float] = defaultdict(float)
    fuzzy_hits: dict[str, list[str]] = defaultdict(list)
    open_positions = [
        position
        for position, token in enumerate(tokens)
        if position not in explained
        and content_word(token)
        and len(token) >= 4
        and not token.isdigit()
        and len(token) <= 40
    ]
    windows = [(position, position + 1) for position in open_positions]
    windows += [(a, a + 2) for a, b in itertools.pairwise(open_positions) if b == a + 1]
    for start, end in windows:
        window = " ".join(tokens[start:end])
        close = difflib.get_close_matches(window, list(idx.fuzzy_types), n=5, cutoff=fuzzy_cutoff(window))
        for found in [name for name in close if name[0] == window[0]][:3]:
            ratio = difflib.SequenceMatcher(None, window, found).ratio()
            for asset_type in idx.fuzzy_types[found]:
                fuzzy_score[asset_type] = max(fuzzy_score[asset_type], 0.5 * ratio * (end - start))
                fuzzy_hits[asset_type].append(found)
            explained.update(range(start, end))
    ranked = []
    for asset_type in set(covered) | set(word_score) | set(fuzzy_score):
        exact = len(covered.get(asset_type, ())) + 0.1 * len(phrases_of.get(asset_type, ()))
        score = exact + word_score.get(asset_type, 0) + fuzzy_score.get(asset_type, 0)
        confidence = "exact" if asset_type in covered else "word" if asset_type in word_score else "weak"
        matched = (*phrases_of.get(asset_type, ()), *word_hits.get(asset_type, ()), *fuzzy_hits.get(asset_type, ()))
        ranked.append(TypeMatch(asset_type, round(score, 3), confidence, tuple(dict.fromkeys(matched))))
    ranked.sort(key=lambda match: (-match.score, match.type))
    if ranked:
        floor = max(0.3, RELATIVE_CUTOFF * ranked[0].score)
        ranked = [match for match in ranked if match.score >= floor]
    unexplained = [
        token
        for position, token in enumerate(tokens)
        if position not in explained and content_word(token) and (not token.isdigit() or len(token) >= 3)
    ]
    return ranked, unexplained


def fuzzy_cutoff(window: str) -> float:
    return 0.88 if len(window) <= 6 else 0.84 if len(window) <= 8 else FUZZY_CUTOFF


def types_for_task(text: str) -> list[TypeMatch]:
    """Device types that fit what the person wants to do, best first. Empty when nothing fits."""
    return analyse(text)[0]


# ---------- hints: rooms and floors ----------


def parse_hints(text: str) -> tuple[str, list[str], list[tuple[str, set[int]]]]:
    """Split a request into the task words, room mentions and floor mentions (with the levels they could mean)."""
    text = fold(text)
    floors: list[tuple[str, set[int]]] = []

    def take_ordinal(match: re.Match) -> str:
        word = match.group(1)
        number = ORDINAL_NUMBERS.get(word) or GERMAN_ORDINALS.get(word.rstrip("nrs"), 1)
        exact = match.group(0).endswith(("og", "obergeschoss"))
        floors.append((match.group(0), {number} if exact else {number - 1, number}))
        return " "

    def take_ambiguous(match: re.Match) -> str:
        number = int(match.group(1) or match.group(2))
        floors.append((match.group(0), {number - 1, number}))
        return " "

    def take_number(match: re.Match) -> str:
        floors.append((match.group(0), {int(match.group(1) or match.group(2))}))
        return " "

    text = ORDINAL_FLOOR.sub(take_ordinal, text)
    text = NUMBER_FLOOR.sub(take_number, text)
    text = AMBIGUOUS_FLOOR.sub(take_ambiguous, text)
    for pattern, level in ((GROUND_FLOOR, 0), (BASEMENT, -1)):
        for match in pattern.finditer(text):
            floors.append((match.group(0), {level}))
        text = pattern.sub(" ", text)
    rooms = [
        match.group(1)
        for match in ROOM_HINT.finditer(text)
        if " " in match.group(1).strip() or match.group(1).strip() not in GENERIC_KINDS
    ]
    text = ROOM_HINT.sub(" ", text)
    rooms += REF.findall(text)
    return text, rooms, floors


def space_tokens(space: dict) -> set[str]:
    ref = fold(space.get("ref") or "")
    return set(words(space["name"])) | set(words(space["room_type"])) | set(words(ref)) | ({ref} if ref else set())


def resolve_rooms(bm: BuildingMap, said: str) -> list[dict]:
    lowered = fold(said).strip()
    if not lowered:
        return []
    exact = [
        space
        for space in bm.spaces.values()
        if lowered in (space["id"].lower(), fold(space.get("ref") or ""), fold(space["name"]))
    ]
    if exact:
        return exact
    tokens = re.findall(r"[\w.\-]+", lowered)
    ids = {token for token in tokens if any(char.isdigit() for char in token)}
    wanted = ids or {token for token in tokens if token not in {"room", "raum", "area", "bereich"}}
    if not wanted:
        return []
    short = {re.sub(r"-[a-z]$", "", token) for token in wanted}
    for target in (wanted, short):
        found = [
            space
            for space in bm.spaces.values()
            if target <= space_tokens(space) | set(re.findall(r"[\w.\-]+", fold(space["name"])))
        ]
        if found:
            return found
    return []


def similar_rooms(bm: BuildingMap, said: str, limit: int = 3) -> list[str]:
    names = {fold(space["name"]): space["name"] for space in bm.spaces.values()}
    close = difflib.get_close_matches(fold(said), list(names), n=limit, cutoff=0.5)
    return [names[name] for name in close]


def room_contents(bm: BuildingMap, space: dict, limit: int = 5) -> str:
    counts = Counter(asset["type"] for asset in bm.assets.values() if asset["space_id"] == space["id"])
    if not counts:
        return "no assets"
    order = sorted(
        counts.items(),
        key=lambda item: (ASSET_CATALOG.get(item[0], {}).get("category") == "furniture", -item[1], item[0]),
    )
    return ", ".join(f"{count} x {ASSET_CATALOG.get(kind, {}).get('label', kind)}" for kind, count in order[:limit])


# ---------- grouping and building facts ----------


def label_of(asset_type: str) -> str:
    return ASSET_CATALOG.get(asset_type, {}).get("label", asset_type.replace("_", " "))


def make_groups(bm: BuildingMap, assets: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for asset in assets:
        grouped[(asset["space_id"], asset["type"])].append(asset)
    groups = []
    for (space_id, asset_type), members in grouped.items():
        space = bm.spaces[space_id]
        ordered = sorted(members, key=lambda asset: (natural_key(asset["name"]), asset["id"]))
        groups.append(
            {
                "zone": space["name"],
                "space_id": space_id,
                "floor": bm.floor_name(space["floor_id"]),
                "level": bm.floors[space["floor_id"]]["level"],
                "type": asset_type,
                "items": [
                    {"ordinal": number, "id": asset["id"], "name": asset["name"]}
                    for number, asset in enumerate(ordered, start=1)
                ],
            }
        )
    groups.sort(key=lambda group: (natural_key(group["zone"]), natural_key(group["type"])))
    return groups


def where_text(groups: list[dict], limit: int = 3) -> str:
    seen = []
    for group in groups:
        text = f"{group['zone']} ({group['floor']})"
        if text not in seen:
            seen.append(text)
    return "; ".join(seen[:limit]) + (" and more" if len(seen) > limit else "")


def knowledge_words(asset_type: str) -> set[str]:
    knowledge = ASSET_KNOWLEDGE[asset_type]
    found = set()
    for phrase in (*knowledge.tasks, knowledge.summary):
        found |= {stem(token) for token in words(phrase) if content_word(token) and token not in GENERIC}
    return found


def closest_present(bm: BuildingMap, missing: list[str], limit: int = 5) -> list[dict]:
    present = Counter(asset["type"] for asset in bm.assets.values() if asset["type"] in ASSET_KNOWLEDGE)
    scored = []
    for asset_type in present:
        best = 0.0
        for gone in missing:
            overlap = len(knowledge_words(gone) & knowledge_words(asset_type))
            bonus = 1 if ASSET_KNOWLEDGE[gone].kind == ASSET_KNOWLEDGE[asset_type].kind else 0
            if overlap >= 2 and bonus:
                best = max(best, overlap + bonus)
        if best:
            scored.append((-best, asset_type))
    scored.sort()
    return [with_places(bm, type_summary(asset_type, present[asset_type])) for _, asset_type in scored[:limit]]


def with_places(bm: BuildingMap, entry: dict, keep_groups: bool = True) -> dict:
    groups = make_groups(bm, [asset for asset in bm.assets.values() if asset["type"] == entry["type"]])
    for group in groups:
        group.pop("level", None)
    return {**entry, "where": where_text(groups), **({"groups": groups[:MAX_GROUPS]} if keep_groups else {})}


def building_has(bm: BuildingMap, limit: int = 10) -> list[dict]:
    present = Counter(asset["type"] for asset in bm.assets.values() if asset["type"] in ASSET_KNOWLEDGE)
    useful = [
        (kind, count) for kind, count in present.items() if ASSET_KNOWLEDGE[kind].kind in {"machine", "equipment"}
    ]
    useful.sort(key=lambda item: (ASSET_KNOWLEDGE[item[0]].kind != "machine", -item[1], item[0]))
    return [with_places(bm, type_summary(kind, count), keep_groups=False) for kind, count in useful[:limit]]


def type_summary(asset_type: str, count: int | None = None) -> dict:
    return {
        "type": asset_type,
        "label": label_of(asset_type),
        "summary": ASSET_KNOWLEDGE[asset_type].summary,
        **({"count": count} if count is not None else {}),
    }


def candidate_entry(bm: BuildingMap, match: TypeMatch, assets: list[dict]) -> dict:
    knowledge = ASSET_KNOWLEDGE[match.type]
    groups = make_groups(bm, assets)
    return {
        **type_summary(match.type),
        "safety": knowledge.safety,
        "confidence": match.confidence,
        "matched": list(match.matched)[:5],
        "count": len(assets),
        "groups": groups,
    }


# ---------- find_for_task ----------


def find_for_task(bm: BuildingMap, task: str, floor_level: int | None = None, room_hint: str | None = None) -> dict:
    """Devices for what the person wants to do or half remembers, with gentle corrections of wrong hints."""
    raw = str(task or "")[:MAX_CHARS]
    if not words(raw):
        raise MapError("Empty request. Say what to do, e.g. 'weld two parts' or 'get coffee'.")
    clean, rooms_said, floors_said = parse_hints(raw)
    if room_hint and room_hint.strip():
        rooms_said.append(fold(room_hint.strip())[:80])
    matches, unexplained = analyse(clean)
    by_type: dict[str, list[dict]] = defaultdict(list)
    for asset in bm.assets.values():
        by_type[asset["type"]].append(asset)
    corrections: list[dict] = []
    notes: list[str] = []
    present = [match for match in matches if match.type in by_type]
    absent = [match for match in matches if match.type not in by_type]

    def on_floor(assets: list[dict]) -> list[dict]:
        return [asset for asset in assets if bm.floors[asset["floor_id"]]["level"] == floor_level]

    if floor_level is not None and present and not any(on_floor(by_type[match.type]) for match in present):
        levels = sorted({bm.floors[asset["floor_id"]]["level"] for match in present for asset in by_type[match.type]})
        corrections.append(
            {
                "said": f"level {floor_level}",
                "actual": "level " + ", ".join(str(level) for level in levels),
                "note": f"Nothing like that on level {floor_level}; it is on level {', '.join(str(level) for level in levels)}.",
            }
        )
    elif floor_level is not None:
        by_type = defaultdict(list, {kind: on_floor(assets) for kind, assets in by_type.items()})
        gone = [match for match in present if not by_type[match.type]]
        present = [match for match in present if by_type[match.type]]
        if gone:
            notes.append(f"No {', '.join(label_of(match.type) for match in gone)} on level {floor_level}.")

    candidates = [candidate_entry(bm, match, by_type[match.type]) for match in present]
    resolved = [(said, resolve_rooms(bm, said)) for said in dict.fromkeys(rooms_said)]
    hinted_ids = {space["id"] for _, spaces in resolved for space in spaces}
    said_levels = set().union(*(levels for _, levels in floors_said)) if floors_said else set()

    def rank(group: dict) -> tuple:
        return (group["space_id"] not in hinted_ids, bool(said_levels) and group["level"] not in said_levels)

    for candidate in candidates:
        candidate["groups"].sort(key=rank)
    scores = {match.type: match.score for match in matches}
    candidates.sort(key=lambda candidate: (rank(candidate["groups"][0]), -scores[candidate["type"]], candidate["type"]))
    all_groups = [group for candidate in candidates for group in candidate["groups"]]
    top_label = candidates[0]["label"] if candidates else ""
    actual = where_text(sorted(all_groups, key=rank)) if all_groups else ""
    wanted_labels = " or ".join(candidate["label"] for candidate in candidates[:2]) or "such a device"

    for said, spaces in resolved:
        if not spaces:
            near = similar_rooms(bm, said)
            note = f"No room matches '{said}' in this building. " + (
                f"Similar rooms: {', '.join(near)}." if near else "I found no similarly named room."
            )
            corrections.append({"said": said, "actual": actual, "note": note})
        elif not any(group["space_id"] in {space["id"] for space in spaces} for group in all_groups):
            space = spaces[0]
            where = f" {wanted_labels} is in {actual}." if actual else ""
            no_such = f"no {wanted_labels}" if actual else "no device of that kind"
            corrections.append(
                {
                    "said": said,
                    "actual": actual,
                    "note": f"{space['name']} exists but has {no_such}. It holds: {room_contents(bm, space)}.{where}",
                }
            )
    for said, levels in floors_said:
        if all_groups and not any(group["level"] in levels for group in all_groups):
            corrections.append(
                {
                    "said": said,
                    "actual": actual,
                    "note": f"{top_label} is not on {said} but in {actual}.",
                }
            )

    result: dict = {
        "task": raw[:MAX_CHARS],
        "candidates": [],
        "needs_choice": False,
        "question": "",
        "corrections": corrections,
    }
    if absent:
        result["not_in_building"] = [type_summary(match.type) for match in absent[:3]]
    if not candidates:
        bm.located_asset_ids = []
        result["note"], result["building_has"] = no_device_note(bm, raw, matches, absent)
        return result

    preferred = [
        candidate for candidate in candidates if rank(candidate["groups"][0]) == rank(candidates[0]["groups"][0])
    ]
    top_score = scores[preferred[0]["type"]]
    close = [candidate for candidate in preferred if scores[candidate["type"]] >= CLOSE_SHARE * top_score]
    in_scope = [
        group for candidate in close for group in candidate["groups"] if rank(group) == rank(close[0]["groups"][0])
    ]
    weak = candidates[0]["confidence"] != "exact"
    outranked = bool(absent) and absent[0].score >= top_score
    content = [token for token in words(clean) if content_word(token)]
    name_like = bool(unexplained) and len(content) <= 3 and len(unexplained) / max(1, len(content)) >= 0.34
    needs_choice = len(close) > 1 or len(in_scope) > 1 or weak or name_like or outranked
    question = ""
    if needs_choice:
        listed = "; ".join(
            f"{group['type'].replace('_', ' ')} in {group['zone']} ({group['floor']})" for group in in_scope[:6]
        )
        if outranked:
            question = (
                f"There is no {label_of(absent[0].type)} in this building. The closest that exists: {listed}. "
                "Is one of these what you mean?"
            )
        elif weak or name_like:
            odd = ", ".join(f"'{token}'" for token in unexplained) if unexplained else f"'{raw[:40]}'"
            question = f"{odd} is not an exact name here. Do you mean the {close[0]['label']}? Here: {listed}."
        else:
            question = f"Several places match: {listed}. Which one do you mean?"
    if absent:
        labels = ", ".join(label_of(match.type) for match in absent[:3])
        notes.insert(0, f"No {labels} in this building." if outranked else f"Not in this building: {labels}.")
    notes.append(GENERAL_NOTE.replace("this unit's", "any unit's"))
    if not needs_choice:
        located = [item["id"] for group in in_scope for item in group["items"]]
    else:
        located = [item["id"] for candidate in close for group in candidate["groups"] for item in group["items"]]
    bm.located_asset_ids = located[:MAX_LOCATED] if needs_choice else located
    for candidate in candidates:
        candidate["groups"] = [
            {**group, "items": group["items"][:MAX_ITEMS_PER_GROUP]} for group in candidate["groups"][:MAX_GROUPS]
        ]
        for group in candidate["groups"]:
            group.pop("level", None)
    result.update(
        {"candidates": candidates, "needs_choice": needs_choice, "question": question, "note": " ".join(notes)}
    )
    return result


def no_device_note(
    bm: BuildingMap, raw: str, matches: list[TypeMatch], absent: list[TypeMatch]
) -> tuple[str, list[dict]]:
    if absent:
        labels = ", ".join(label_of(match.type) for match in absent[:3])
        near = closest_present(bm, [match.type for match in absent[:3]])
        if near:
            names = "; ".join(f"{item['label']} in {item['where']} ({item['summary']})" for item in near)
            return f"No {labels} in this building. Closest types that exist here: {names}", near
        return f"No {labels} in this building, and I found no similar device type here.", building_has(bm)
    listed = ", ".join(item["label"] for item in building_has(bm))
    return (
        f"I do not know a device type for '{raw[:60]}'. This building has, among others: {listed}.",
        building_has(bm),
    )


# ---------- match_description ----------


def match_description(bm: BuildingMap, text: str) -> dict:
    """What does a half-remembered or misspelled name most likely refer to? Never a silent guess below the threshold."""
    raw = str(text or "")[:MAX_CHARS]
    if not words(raw):
        raise MapError("Empty description. Give a name or a few words, e.g. 'kafeeautomat' or 'mill H-A1'.")
    clean, rooms_said, _ = parse_hints(raw)
    matches, unexplained = analyse(clean)
    lowered = fold(raw).strip()
    by_type: dict[str, list[dict]] = defaultdict(list)
    for asset in bm.assets.values():
        by_type[asset["type"]].append(asset)
    spaces_hinted = [space for said in rooms_said for space in resolve_rooms(bm, said)]
    hinted_ids = {space["id"] for space in spaces_hinted}
    candidates: list[dict] = []
    names = {fold(asset["name"]): asset for asset in bm.assets.values()}
    exact_asset = names.get(lowered)
    if exact_asset:
        candidates.append(asset_candidate(bm, exact_asset, 1.0, "exact"))
    else:
        for name in difflib.get_close_matches(lowered, list(names), n=3, cutoff=NAME_CUTOFF):
            ratio = difflib.SequenceMatcher(None, lowered, name).ratio()
            candidates.append(asset_candidate(bm, names[name], ratio, "weak"))
    room_names = {fold(space["name"]): space for space in bm.spaces.values()}
    for name in difflib.get_close_matches(lowered, list(room_names), n=3, cutoff=NAME_CUTOFF):
        space = room_names[name]
        ratio = difflib.SequenceMatcher(None, lowered, name).ratio()
        candidates.append(
            {
                "kind": "room",
                "id": space["id"],
                "name": space["name"],
                "floor": bm.floor_name(space["floor_id"]),
                "score": round(ratio, 2),
                "confidence": "exact" if ratio == 1 else "weak",
            }
        )
    for match in matches[:5]:
        units = by_type.get(match.type, [])
        if hinted_ids:
            narrowed = [asset for asset in units if asset["space_id"] in hinted_ids]
            units = narrowed or units
        entry = {
            "kind": "type",
            "type": match.type,
            "label": label_of(match.type),
            "summary": ASSET_KNOWLEDGE[match.type].summary,
            "count_here": len(units),
            "where": where_text(make_groups(bm, units)) if units else "",
            "score": match.score,
            "confidence": match.confidence,
        }
        candidates.append(entry)
    strong = [item for item in candidates if item["confidence"] == "exact"]
    unclear = bool(unexplained) and len(unexplained) / max(1, len([t for t in words(clean) if content_word(t)])) >= 0.34
    if not candidates:
        return {
            "text": raw,
            "confidence": "none",
            "candidates": [],
            "needs_choice": True,
            "question": "Nothing here is called or does that. Can you describe what you want to do with it?",
            "note": "No name, room or device type matched closely enough, so I am not guessing.",
        }
    if strong and not unclear and len({item.get("type") or item["id"] for item in strong}) == 1:
        confidence, needs_choice, question = "exact", False, ""
    else:
        confidence = "partial" if strong else "weak"
        needs_choice = True
        top = candidates[0]
        label = top.get("label") or top.get("name")
        question = f"'{raw[:40]}' is not an exact match. Do you mean {label}?"
        if unclear:
            question = f"'{', '.join(unexplained)}' does not match anything here. Do you mean {label}?"
    if len({item.get("type") for item in strong if item["kind"] == "type"}) > 1:
        confidence, needs_choice = "exact", True
        question = (
            "Several kinds fit: "
            + ", ".join(item["label"] for item in strong if item["kind"] == "type")
            + ". Which one?"
        )
    return {
        "text": raw,
        "confidence": confidence,
        "candidates": candidates[:8],
        "needs_choice": needs_choice,
        "question": question,
        "note": GENERAL_NOTE.replace("this unit's", "any unit's"),
    }


def asset_candidate(bm: BuildingMap, asset: dict, score: float, confidence: str) -> dict:
    space = bm.spaces[asset["space_id"]]
    return {
        "kind": "asset",
        "id": asset["id"],
        "name": asset["name"],
        "type": asset["type"],
        "zone": space["name"],
        "floor": bm.floor_name(space["floor_id"]),
        "score": round(score, 2),
        "confidence": confidence,
    }


# ---------- describe_asset ----------


def type_from_reference(text: str) -> str | None:
    lowered = fold(text).strip()
    for asset_type, entry in ASSET_CATALOG.items():
        if lowered in (fold(asset_type.replace("_", " ")), fold(entry["label"])):
            return asset_type
    matches, unexplained = analyse(text)
    clear = len(matches) == 1 or (len(matches) > 1 and matches[1].score < CLOSE_SHARE * matches[0].score)
    return matches[0].type if matches and matches[0].confidence == "exact" and not unexplained and clear else None


def describe_asset(bm: BuildingMap, ref: str) -> dict:
    """General description of one asset (by id or exact name) or of a device type (type name or label)."""
    key = str(ref or "").strip()[:MAX_CHARS]
    if not key:
        raise MapError("Empty reference. Give an asset id, an exact asset name or a device type like 'press brake'.")
    asset = bm.assets.get(key)
    if asset is None:
        named = [item for item in bm.assets.values() if fold(item["name"]) == fold(key)]
        if len(named) > 1:
            listed = ", ".join(f"{item['name']} ({item['id']})" for item in named[:10])
            raise MapError(f"Several assets are called '{key}': {listed}. Use one of the ids.")
        asset = named[0] if named else None
    if asset is not None:
        knowledge = ASSET_KNOWLEDGE.get(asset["type"])
        space = bm.spaces[asset["space_id"]]
        footprint = asset.get("footprint") or {}
        return {
            "id": asset["id"],
            "name": asset["name"],
            "type": asset["type"],
            "category": asset.get("category"),
            "room": space["name"],
            "space_id": space["id"],
            "floor": bm.floor_name(space["floor_id"]),
            "size_m": {"width": footprint.get("width_m"), "depth": footprint.get("depth_m")},
            "summary": knowledge.summary if knowledge else "",
            "safety": knowledge.safety if knowledge else "",
            "note": GENERAL_NOTE,
        }
    asset_type = type_from_reference(key)
    if asset_type is None:
        close = [match.type for match in types_for_task(key)[:5]]
        hint = f" Did you mean one of: {', '.join(label_of(kind) for kind in close)}?" if close else ""
        raise MapError(f"No asset or device type matches '{key[:60]}'.{hint}")
    units = [item for item in bm.assets.values() if item["type"] == asset_type]
    knowledge = ASSET_KNOWLEDGE[asset_type]
    return {
        "type": asset_type,
        "label": label_of(asset_type),
        "category": ASSET_CATALOG[asset_type]["category"],
        "summary": knowledge.summary,
        "safety": knowledge.safety,
        "in_this_building": {"count": len(units), "where": where_text(make_groups(bm, units)) if units else "none"},
        "note": GENERAL_NOTE,
    }


# ---------- tools ----------


def make_task_tools(bm: BuildingMap) -> list:
    @beta_tool
    def find_for_task_tool(task: str, floor_level: int | None = None, room_hint: str | None = None) -> str:
        """Find the devices for what the person wants to DO or half remembers ("I want to weld", "where can I copy
        something", "where do I get coffee", "someone said there is a laser thing in hall 3"). Use it BEFORE searching
        by words whenever the person names a task, a vague or misspelled device, or a hint like a room or floor.
        Works in English and German, tolerates typos. Pass the person's own words in `task`.
        Answer in this order: 1) say what exists and where, 2) gently correct what differs (see `corrections`:
        wrong room or floor, a device type that is not in this building and what is here instead), 3) say what the
        device is for, from `summary` (general knowledge about the TYPE; say it is general). Put the true location
        first. If needs_choice is true, ask the returned question in one short sentence (if the message contains
        'Answer:' nobody can reply: take the most plausible candidate and say which). Technical data, state,
        settings, capacity, availability or who uses a unit are NOT available: never state or invent them.

        Args:
            task: What the person wants to do or the device they half remember, in their words.
            floor_level: Floor they mention (0 = ground floor, -1 = basement). Wrong floors are corrected, omit if unknown.
            room_hint: Room, zone or hall they mention ("hall 3", "H-A4"). Wrong rooms are corrected, omit if unknown.
        """
        try:
            return as_json(find_for_task(bm, task, floor_level, room_hint))
        except MapError as error:
            raise ToolError(str(error)) from error

    find_for_task_tool.name = "find_for_task"

    @beta_tool
    def describe_asset_tool(ref: str) -> str:
        """Explain what an asset or a type of device is for ("what is this?", "what does a press brake do?").
        `ref` is an asset id, an exact asset name, or a device type or label. The answer is GENERAL knowledge of
        the type (summary and safety note): say that it is general. Specifications, settings, current state,
        capacity and condition of a unit are NOT available: never state or invent them.

        Args:
            ref: Asset id, exact asset name, or a device type or label such as "press brake".
        """
        try:
            return as_json(describe_asset(bm, ref))
        except MapError as error:
            raise ToolError(str(error)) from error

    describe_asset_tool.name = "describe_asset"
    return [find_for_task_tool, describe_asset_tool]
