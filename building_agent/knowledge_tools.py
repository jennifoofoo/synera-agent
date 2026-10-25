"""Place knowledge for the agent (docs/specs/place-knowledge.md): remember, resolve and read facts at a place.

The store (building_agent/knowledge.py) keeps facts with a validity period. This module only turns what the person
said into store calls: which place is meant (anchor), note or issue, until when, and which filters a question
means. Nothing is stored without a card and a clear yes in the next message: remember_here and resolve_here only
make the card (state.pending), confirm_change in guide_tools applies it through `apply_pending`.

Times are Europe/Berlin. 'bis morgen' means tomorrow 18:00 (end of shift), 'bis Freitag' Friday 18:00. A time that
cannot be read ('until next week', 'bis später') is asked back, never guessed."""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from building_agent.find_tools import find_asset, words_of
from building_agent.find_space import find_space
from building_agent.time_words import names_a_time, when_is_later
from starter_agent.building_map import BuildingMap, MapError
from starter_agent.tools import as_json

TZ = ZoneInfo("Europe/Berlin")
SHIFT_END = time(18, 0)
UNDO_WINDOW = timedelta(minutes=2)
MAX_TEXT = 500
MAX_SPOKEN = 3  # facts read out per answer; the page gets all of them


def now() -> datetime:
    """The current time; tests replace `knowledge_tools.CLOCK`."""
    return CLOCK()


def _system_now() -> datetime:
    return datetime.now(TZ)


CLOCK = _system_now


# ---------- time words: until when, since when ----------

WEEKDAY = {
    "monday": 0,
    "montag": 0,
    "tuesday": 1,
    "dienstag": 1,
    "wednesday": 2,
    "mittwoch": 2,
    "thursday": 3,
    "donnerstag": 3,
    "friday": 4,
    "freitag": 4,
    "saturday": 5,
    "samstag": 5,
    "sunday": 6,
    "sonntag": 6,
}
COUNT = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "ein": 1,
    "eine": 1,
    "einen": 1,
    "einer": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "fuenf": 5,
    "sechs": 6,
}
UNIT = {
    "minute": "minutes",
    "minutes": "minutes",
    "min": "minutes",
    "minuten": "minutes",
    "hour": "hours",
    "hours": "hours",
    "stunde": "hours",
    "stunden": "hours",
    "day": "days",
    "days": "days",
    "tag": "days",
    "tage": "days",
    "tagen": "days",
    "week": "weeks",
    "weeks": "weeks",
    "woche": "weeks",
    "wochen": "weeks",
}
_DAYS = "|".join(WEEKDAY)
_COUNTS = "|".join(COUNT)
_UNITS = "|".join(sorted(UNIT, key=len, reverse=True))
UNTIL_WORD = r"(?:until|till|til|bis(?: zum| zur| um| ende| end)?|through)"
FOR_WORD = r"(?:for(?: the next)?|für(?: die nächsten| die naechsten)?)"
UNTIL_PATTERNS = [  # (kind, regex); the first that matches wins, so longer phrases come first
    (
        "open",
        rf"\b{UNTIL_WORD} (?:further notice|auf weiteres|it'?s fixed|it is fixed|es repariert ist|zur reparatur)\b",
    ),
    ("plus2", rf"\b{UNTIL_WORD} (?:the )?(?:day after tomorrow|übermorgen|uebermorgen)\b"),
    ("tomorrow_morning", rf"\b{UNTIL_WORD} (?:tomorrow morning|morgen früh|morgen frueh|morgen vormittag)\b"),
    ("tomorrow_noon", rf"\b{UNTIL_WORD} (?:tomorrow (?:at )?noon|morgen mittag)\b"),
    ("tomorrow", rf"\b{UNTIL_WORD} (?:tomorrow|morgen)(?: (?:evening|abend))?\b"),
    ("weekday", rf"\b{UNTIL_WORD} (?:next |nächsten |naechsten |kommenden |this |diesen )?({_DAYS})\b"),
    ("tonight", rf"\b{UNTIL_WORD} (?:tonight|this evening|heute abend)\b"),
    (
        "shift",
        rf"\b(?:{UNTIL_WORD} (?:the )?(?:end of (?:the |my |this )?(?:day|shift)|feierabend|schichtende|"
        r"dienstschluss|schicht(?:ende)?)|for the rest of the day|den rest des tages)\b",
    ),
    ("noon", rf"\b{UNTIL_WORD} (?:noon|midday|mittag)\b"),
    ("midnight", rf"\b{UNTIL_WORD} (?:midnight|mitternacht)\b"),
    ("clock", rf"\b{UNTIL_WORD} (\d{{1,2}})(?:[:.](\d{{2}}))? ?(uhr|h|am|pm|o'?clock)?(?!\S*\d)"),
    ("span", rf"\b{FOR_WORD} (\d+|{_COUNTS}|half an?|eine halbe) ?({_UNITS})\b"),
    (
        "unclear",
        rf"\b(?:{UNTIL_WORD} (?:later|next \w+|nächste\w* \w+|naechste\w* \w+|später|spaeter|soon|bald|whenever|"
        rf"irgendwann|then|dann)|{FOR_WORD} (?:a while|some time|a bit|eine weile|einige zeit|a few \w+|"
        r"ein paar \w+))\b",
    ),
]
UNTIL_RES = [(kind, re.compile(pattern, re.IGNORECASE)) for kind, pattern in UNTIL_PATTERNS]
ASK_UNTIL = "Until when exactly? For example until 18:00 today, until tomorrow or for two hours."


@dataclass
class Until:
    """An end time the person named. `at` is None for an open end ('until further notice') or when unclear."""

    phrase: str
    at: datetime | None = None
    unclear: bool = False


def at_clock(day: datetime, clock: time) -> datetime:
    return day.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)


def parse_until(text: str | None, current: datetime) -> Until | None:
    """The end time in `text` ('bis morgen', 'until 14:00', 'for two hours'), or None if it names none."""
    text = " ".join(str(text or "").split())[:2000]
    for kind, pattern in UNTIL_RES:
        match = pattern.search(text)
        if match is None:
            continue
        phrase = match.group(0)
        if kind == "open":
            return Until(phrase)
        if kind == "unclear":
            return Until(phrase, unclear=True)
        if kind == "plus2":
            return Until(phrase, at_clock(current + timedelta(days=2), SHIFT_END))
        if kind.startswith("tomorrow"):
            clock = {"tomorrow_morning": time(8, 0), "tomorrow_noon": time(12, 0)}.get(kind, SHIFT_END)
            return Until(phrase, at_clock(current + timedelta(days=1), clock))
        if kind == "weekday":
            ahead = (WEEKDAY[match.group(1).lower()] - current.weekday()) % 7
            end = at_clock(current + timedelta(days=ahead), SHIFT_END)
            return Until(phrase, end if end > current else end + timedelta(days=7))
        if kind in ("tonight", "shift", "noon"):
            clock = {"tonight": time(22, 0), "noon": time(12, 0)}.get(kind, SHIFT_END)
            end = at_clock(current, clock)
            return Until(phrase, end) if end > current else Until(phrase, unclear=True)
        if kind == "midnight":
            return Until(phrase, at_clock(current + timedelta(days=1), time(0, 0)))
        if kind == "clock":
            hour, minute, suffix = int(match.group(1)), int(match.group(2) or 0), (match.group(3) or "").lower()
            if not suffix and match.group(2) is None:  # 'bis 3' alone could be a room or a count
                return Until(phrase, unclear=True)
            if suffix == "pm" and hour < 12:
                hour += 12
            elif suffix == "am" and hour == 12:
                hour = 0
            if hour > 23 or minute > 59:
                return Until(phrase, unclear=True)
            end = at_clock(current, time(hour, minute))
            return Until(phrase, end if end > current else end + timedelta(days=1))
        if kind == "span":
            amount = match.group(1).lower()
            number = 0.5 if "hal" in amount else int(amount) if amount.isdigit() else COUNT[amount]
            unit = UNIT[match.group(2).lower()]
            if number <= 0:
                return Until(phrase, unclear=True)
            return Until(phrase, current + timedelta(**{unit: number}))
    return None


@dataclass
class ClosureTime:
    """What the time words around a closure mean: scheduled for later (refused), unclear (ask), or until `at`."""

    scheduled: bool = False
    unclear: bool = False
    at: datetime | None = None
    phrase: str = ""


def closure_time(text: str | None, until: str | None, when: str | None, current: datetime) -> ClosureTime:
    """A closure from now until a named time is allowed; any other time word still means 'later' and is refused.

    The person's own message decides (as for every closure); the model's `until` is only a fallback when the message
    has no end time, and its `when` only counts when it is not the end time itself."""
    found = parse_until(text, current) or parse_until(until, current)
    if found is None and until and str(until).strip():
        found = parse_until(f"until {until}", current) or Until(str(until), unclear=True)
    rest = str(text or "").replace(found.phrase, " ") if found and found.phrase in str(text or "") else text
    when_is_end = bool(found) and bool(when) and parse_until(str(when), current) is not None
    if names_a_time(rest) or (when_is_later(when) and not when_is_end):
        return ClosureTime(scheduled=True)
    if found is None:
        return ClosureTime()
    if found.unclear:
        return ClosureTime(unclear=True, phrase=found.phrase)
    return ClosureTime(at=found.at, phrase=found.phrase)


PERIODS = [
    ("today", r"\b(today|heute)\b"),
    ("yesterday", r"\b(yesterday|gestern)\b"),
    ("last_week", r"\b(last week|letzte woche|letzten woche|vorige woche|vorigen woche)\b"),
    ("this_week", r"\b(this week|diese woche|dieser woche|the week|der woche)\b"),
    ("this_month", r"\b(this month|diesen monat|diesem monat)\b"),
    ("days", r"\b(?:last|past|letzten|vergangenen) (\d+) (?:days|tage|tagen)\b"),
]


def period_bounds(text: str | None, current: datetime) -> tuple[datetime, datetime] | None:
    """(since, until) for 'this week', 'today', 'gestern', 'last 3 days'; None if the words name no period."""
    text = str(text or "").lower()
    midnight = at_clock(current, time(0, 0))
    for kind, pattern in PERIODS:
        match = re.search(pattern, text)
        if match is None:
            continue
        if kind == "today":
            return midnight, current
        if kind == "yesterday":
            return midnight - timedelta(days=1), midnight
        monday = midnight - timedelta(days=current.weekday())
        if kind == "this_week":
            return monday, current
        if kind == "last_week":
            return monday - timedelta(days=7), monday
        if kind == "this_month":
            return midnight.replace(day=1), current
        return midnight - timedelta(days=int(match.group(1))), current
    return None


def as_time(value) -> datetime | None:
    if value is None or value == "":
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=TZ)).astimezone(TZ)


def day_words(moment: datetime, current: datetime) -> str:
    days = (moment.date() - current.date()).days
    if days == 0:
        return "today"
    if days == -1:
        return "yesterday"
    if days == 1:
        return "tomorrow"
    if -7 < days < 7:
        return moment.strftime("%A")
    return f"{moment.day} {moment.strftime('%b')}"


def clock_words(moment: datetime) -> str:
    return f"{moment.hour}:{moment.minute:02d}"


def since_words(value, current: datetime) -> str:
    """'since 8:10' today, 'since yesterday 14:05', 'since Monday 9:00', 'since 12 Oct 9:00'."""
    moment = as_time(value)
    if moment is None:
        return ""
    day = day_words(moment, current)
    return f"since {clock_words(moment)}" if day == "today" else f"since {day} {clock_words(moment)}"


def until_words(value, current: datetime) -> str:
    """'until 18:00 today', 'until tomorrow 18:00', 'until Friday 18:00'."""
    moment = as_time(value)
    if moment is None:
        return ""
    day = day_words(moment, current)
    return f"until {clock_words(moment)} today" if day == "today" else f"until {day} {clock_words(moment)}"


# ---------- note or issue ----------

PROBLEM = re.compile(
    r"\b(drip\w*|leak\w*|broken|break\w*|defect\w*|faulty|fault|out of order|not working|doesn'?t work|does not work|"
    r"won'?t|stuck|jam\w*|noise|noisy|loud|squeak\w*|smell\w*|smok\w*|overheat\w*|too hot|error\w*|alarm|"
    r"crack\w*|loose|missing|damag\w*|wet|flicker\w*|blocked|dead|failed|failure|problem|issue|"
    r"tropf\w*|undicht|leck\w*|kaputt|defekt\w*|funktioniert nicht|geht nicht|klemm\w*|laut|quietsch\w*|"
    r"riecht|gestank|rauch\w*|heiß|heiss|überhitz\w*|fehler\w*|störung|stoerung|riss|locker|fehlt|beschädigt|"
    r"beschaedigt|nass|flacker\w*|blockiert|ausgefallen|ausfall|problem)\b",
    re.IGNORECASE,
)
DONE = re.compile(
    r"\b(fixed|repaired|resolved|done|sorted|works again|working again|cleared|"
    r"repariert|behoben|erledigt|geht wieder|funktioniert wieder|wieder offen|gelöst|geloest)\b",
    re.IGNORECASE,
)


def detect_kind(text: str, said: str | None = None) -> str:
    """'issue' when the text (or the model's kind) names a problem, else 'note'. Problem words always win."""
    if PROBLEM.search(text or ""):
        return "issue"
    return "issue" if said == "issue" else "note"


# ---------- which place ----------

HERE_WORDS = {"here", "hier", "this", "place", "spot", "room", "da", "dort", "there", "where", "i", "am", "the"}
ELEMENT_WORDS = {
    "lift",
    "lifts",
    "elevator",
    "aufzug",
    "fahrstuhl",
    "stairs",
    "stair",
    "staircase",
    "treppe",
    "treppenhaus",
    "door",
    "tür",
    "tuer",
    "gate",
    "tor",
}
GERMAN_ELEMENTS = {
    "aufzug": "lift",
    "fahrstuhl": "lift",
    "treppe": "staircase",
    "treppenhaus": "staircase",
    "tür": "door",
    "tuer": "door",
}


@dataclass
class Anchor:
    space_id: str
    floor_id: str
    label: str
    asset_id: str | None = None
    element_id: str | None = None
    point: list | None = None

    def as_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "asset_id": self.asset_id,
            "element_id": self.element_id,
            "point": self.point,
            "floor_id": self.floor_id,
        }


class NeedsAnswer(Exception):
    """The place is not clear: the payload is what to ask the person."""

    def __init__(self, payload: dict) -> None:
        super().__init__(payload.get("question", ""))
        self.payload = payload


def room_label(bm: BuildingMap, space_id: str) -> str:
    space = bm.spaces[space_id]
    return f"{space['name']} ({bm.floor_name(space['floor_id'])})"


def asset_anchor(bm: BuildingMap, asset_id: str) -> Anchor:
    asset = bm.assets[asset_id]
    label = f"{asset['name']} in {room_label(bm, asset['space_id'])}"
    return Anchor(asset["space_id"], asset["floor_id"], label, asset_id=asset_id, point=list(asset["position"]))


def element_anchor(bm: BuildingMap, element_id: str, state=None) -> Anchor:
    if element_id in bm.connectors:
        connector = bm.connectors[element_id]
        here = getattr(getattr(state, "position", None), "space_id", None)
        space_id = here if here in connector["space_ids"] else connector["space_ids"][0]
        return Anchor(space_id, bm.spaces[space_id]["floor_id"], connector["name"], element_id=element_id)
    opening = bm.openings[element_id]
    inside = [space_id for space_id in opening["space_ids"] if space_id in bm.spaces]
    names = " and ".join(bm.spaces[space_id]["name"] for space_id in inside) or "outside"
    return Anchor(inside[0], bm.spaces[inside[0]]["floor_id"], f"the door of {names}", element_id=element_id)


def space_anchor(bm: BuildingMap, space_id: str, point=None) -> Anchor:
    return Anchor(
        space_id, bm.spaces[space_id]["floor_id"], room_label(bm, space_id), point=list(point) if point else None
    )


def is_here(place: str | None) -> bool:
    words = words_of(place or "")
    return not words or set(words) <= HERE_WORDS


def here_anchor(bm: BuildingMap, state) -> Anchor:
    position = getattr(state, "position", None)
    if position is None or position.space_id not in bm.spaces:
        raise NeedsAnswer({"where_are_you": True, "question": "Where are you? Name the room or the machine."})
    return space_anchor(bm, position.space_id, position.point)


def resolve_anchor(bm: BuildingMap, state, place: str | None) -> Anchor:
    """The place the person means: their position for 'here', else an asset, a lift/stair/door, or a room.

    Several matches are never guessed: NeedsAnswer carries the question."""
    if is_here(place):
        return here_anchor(bm, state)
    place = str(place).strip()[:120]
    if place in bm.assets:
        return asset_anchor(bm, place)
    if place in bm.connectors or place in bm.openings:
        return element_anchor(bm, place, state)
    if place in bm.spaces:
        return space_anchor(bm, place)
    words = words_of(place)
    if any(word in ELEMENT_WORDS for word in words):
        english = " ".join(GERMAN_ELEMENTS.get(word, word) for word in words)
        named = [c["id"] for c in bm.connectors.values() if " ".join(words_of(c["name"])) in (english, " ".join(words))]
        if len(named) == 1:
            return element_anchor(bm, named[0], state)
    kept = list(bm.located_asset_ids)
    try:
        found = find_asset(bm, place)
    except MapError:
        found = {"matches": 0}
    finally:
        bm.located_asset_ids = kept
    if found.get("matches"):
        if found["needs_choice"]:
            raise NeedsAnswer({"needs_choice": True, "question": found["question"]})
        items = found["groups"][0]["items"]
        if len(items) == 1:
            return asset_anchor(bm, items[0]["id"])
        here = getattr(getattr(state, "position", None), "space_id", None)
        names = ", ".join(item["name"] for item in items[:6])
        if here is None or found["groups"][0]["space_id"] != here:
            raise NeedsAnswer({"needs_choice": True, "question": f"Which one do you mean: {names}?"})
        raise NeedsAnswer({"needs_choice": True, "question": f"Which one here do you mean: {names}?"})
    try:
        spaces = find_space(bm, place)
    except MapError as error:
        raise NeedsAnswer({"not_found": True, "question": f"{error} Which place do you mean?"}) from error
    if "match" in spaces:
        return space_anchor(bm, spaces["match"]["id"])
    options = "; ".join(f"{item['name']} ({item['floor']})" for item in spaces["candidates"][:6])
    raise NeedsAnswer({"needs_choice": True, "question": f"Which one do you mean: {options}?"})


# ---------- the store ----------


def building_key(bm: BuildingMap) -> str:
    """The key the store files facts under (the same function the web API uses)."""
    from building_agent import knowledge

    if hasattr(knowledge, "building_key"):
        return knowledge.building_key(bm)
    return bm.data["building"]["id"]


def store_of(state):
    store = getattr(state, "knowledge", None)
    if store is None:
        raise ToolError("Place knowledge is not available here.")
    return store


def author_of(state) -> str:
    return getattr(state, "author", None) or "Technician"


def benchmark(state) -> bool:
    return "answer:" in str(getattr(state, "last_user_text", "")).lower()


def fact_dict(fact) -> dict:
    return fact.to_dict() if hasattr(fact, "to_dict") else dict(fact)


def anchor_label(bm: BuildingMap, anchor: dict) -> str:
    anchor = anchor or {}
    if anchor.get("asset_id") in bm.assets:
        return asset_anchor(bm, anchor["asset_id"]).label
    if anchor.get("element_id") in bm.connectors or anchor.get("element_id") in bm.openings:
        return element_anchor(bm, anchor["element_id"]).label
    if anchor.get("space_id") in bm.spaces:
        return room_label(bm, anchor["space_id"])
    return "an unknown place"


def spoken_fact(bm: BuildingMap, fact: dict, current: datetime) -> dict:
    """One fact as the agent reads it: no ids in the words, age and author always."""
    line = {
        "id": fact.get("id"),
        "kind": fact.get("kind"),
        "text": fact.get("text"),
        "place": anchor_label(bm, fact.get("anchor")),
        "since": since_words(fact.get("valid_from"), current),
        "by": fact.get("author") or "unknown",
        "status": fact.get("status"),
    }
    if fact.get("valid_to") and fact.get("status") != "resolved":
        line["until"] = until_words(fact["valid_to"], current)
    if fact.get("status") == "resolved" and fact.get("valid_to"):
        line["resolved"] = f"{day_words(as_time(fact['valid_to']), current)} {clock_words(as_time(fact['valid_to']))}"
    if fact.get("photo"):
        line["photo"] = fact["photo"]
    return line


def short_line(bm: BuildingMap, fact: dict, current: datetime) -> str:
    """'Issue at Press 2: valve drips (since 8:10, by Technician A)' for guiding."""
    word = {"issue": "Problem", "closure": "Closed"}.get(fact.get("kind"), "Note")
    place = anchor_label(bm, fact.get("anchor"))
    return f"{word} at {place}: {fact.get('text')} ({since_words(fact.get('valid_from'), current)}, by {fact.get('author') or 'unknown'})"


def facts_lookup(bm: BuildingMap, state):
    """For walk.py: {space_id: [short lines]} of notes and issues valid now in the given rooms."""

    def lookup(space_ids: list[str]) -> dict[str, list[str]]:
        store = getattr(state, "knowledge", None)
        if store is None or not space_ids:
            return {}
        current = now()
        found: dict[str, list[str]] = {}
        for space_id in dict.fromkeys(space_ids):
            if space_id not in bm.spaces:
                continue
            facts = [fact_dict(f) for f in store.query(bm, space_id=space_id, at=current)]
            lines = [short_line(bm, f, current) for f in facts if f.get("kind") in ("note", "issue")]
            if lines:
                found[space_id] = lines
        return found

    return lookup


# ---------- confirm_change calls this for remember and resolve ----------


def apply_pending(bm: BuildingMap, state, pending) -> dict:
    """Store what the card said, after the clear yes. Returns the tool result body."""
    store = store_of(state)
    extra = pending.extra or {}
    current = now()
    if pending.action == "remember":
        fact = fact_dict(
            store.add(
                bm,
                kind=extra["kind"],
                anchor=extra["anchor"],
                text=extra["text"],
                valid_to=extra.get("valid_to"),
                author=author_of(state),
                source=extra.get("source", "voice"),
                utterance=extra.get("utterance", ""),
                related=extra.get("related", []),
                photo_bytes=None,
                now=current,
            )
        )
        state.last_fact = {"id": fact.get("id"), "at": current, "building": building_key(bm)}
        return {"stored": True, "fact": spoken_fact(bm, fact, current), "say": "Say in one short sentence it is noted."}
    fact = fact_dict(
        store.resolve(
            bm, fact_id=extra["fact_id"], text=extra.get("text") or "resolved", author=author_of(state), now=current
        )
    )
    state.last_fact = None
    return {
        "resolved": True,
        "fact": spoken_fact(bm, fact, current),
        "say": "Say in one short sentence it is marked fixed.",
    }


def store_closure(bm: BuildingMap, state, element_id: str, until: datetime, reason: str | None) -> dict:
    """A confirmed timed closure becomes a closure fact, so it ends by itself at `until`."""
    store = store_of(state)
    current = now()
    anchor = element_anchor(bm, element_id, state) if element_id not in bm.spaces else space_anchor(bm, element_id)
    data = anchor.as_dict()
    data["element_id"] = element_id
    fact = fact_dict(
        store.add(
            bm,
            kind="closure",
            anchor=data,
            text=(reason or "closed").strip()[:MAX_TEXT],
            valid_to=until,
            author=author_of(state),
            source="voice",
            utterance=str(getattr(state, "last_user_text", ""))[:MAX_TEXT],
            related=[],
            photo_bytes=None,
            now=current,
        )
    )
    state.last_fact = {"id": fact.get("id"), "at": current, "building": building_key(bm)}
    return fact


def end_closures(bm: BuildingMap, state, element_id: str) -> int:
    """A confirmed reopen ends the closure facts of that element, so they do not close it again."""
    store = getattr(state, "knowledge", None)
    if store is None:
        return 0
    current = now()
    ended = 0
    for fact in [fact_dict(f) for f in store.active_closures(building_key(bm), at=current)]:
        if (fact.get("anchor") or {}).get("element_id") == element_id:
            store.resolve(bm, fact_id=fact["id"], text="reopened", author=author_of(state), now=current)
            ended += 1
    return ended


def undo_fact(bm: BuildingMap, state, snapshot) -> None:
    """Undo of a stored fact: only right after it was made (2 minutes), else it has to be resolved instead."""
    made = getattr(snapshot, "fact_at", None)
    if made is None:
        return
    if now() - made > UNDO_WINDOW:
        raise ToolError(
            "That note is older than two minutes, so it cannot be undone. Offer to mark it as fixed instead."
        )


def undo_fact_apply(bm: BuildingMap, state, snapshot) -> None:
    if getattr(snapshot, "fact_at", None) is None:
        return
    undo_fact(bm, state, snapshot)
    store_of(state).undo_last(building_key(bm), now=now())
    state.last_fact = None


# ---------- the tools ----------


def make_knowledge_tools(bm: BuildingMap, state) -> list:
    from building_agent.guide_tools import Pending, building_signature

    def card_guard() -> None:
        if benchmark(state):
            raise ToolError("Nothing is remembered in a message with 'Answer:'. Answer the question only.")
        if state.pending is not None and state.pending.turn == state.turn:
            raise ToolError("One proposal per message. Show the card you already made and wait for the answer.")

    @beta_tool
    def remember_here(
        text: str,
        place: str | None = None,
        kind: str | None = None,
        until: str | None = None,
        related: list[str] | None = None,
    ) -> str:
        """Prepare a note or a problem report at a place ('merk dir hier: ...', 'remember here: ...', 'the valve at
        press 2 drips'). Stores nothing yet: returns a card. Show it in one or two sentences and wait for a clear yes in
        the person's NEXT message, then call confirm_change. Never for a message with 'Answer:'.

        Args:
            text: What to remember, short, in the person's words ('valve drips').
            place: The machine, room, lift or door it is about, as the person named it; leave it out for 'here'
                (the person's position).
            kind: 'issue' for a problem, 'note' for knowledge or a hint. Problem words make it an issue anyway.
            until: Only if the person said until when it holds ('until tomorrow').
            related: Other places the person said are affected too (each like `place`).
        """
        card_guard()
        clean = " ".join(str(text or "").split())[:MAX_TEXT]
        if not clean:
            raise ToolError("text is empty: ask what to remember.")
        try:
            anchor = resolve_anchor(bm, state, place)
            others = [resolve_anchor(bm, state, other) for other in (related or [])[:5] if not is_here(other)]
        except NeedsAnswer as asked:
            return as_json({**asked.payload, "stored": False})
        current = now()
        valid_to = None
        if until:
            found = parse_until(f"until {until}", current) or parse_until(until, current)
            if found is None or found.unclear:
                return as_json({"needs_time": True, "question": ASK_UNTIL, "stored": False})
            valid_to = found.at
        fact_kind = detect_kind(clean, kind)
        word = "Problem" if fact_kind == "issue" else "Note"
        what = f"{word} at {anchor.label}: {clean}. From now" + (
            f", {until_words(valid_to, current)}" if valid_to else ""
        )
        what += ", open." if fact_kind == "issue" else "."
        card = {
            "I understood": what,
            **({"also affects": [other.label for other in others]} if others else {}),
            "by": author_of(state),
            "status": "nothing stored yet, waiting for the person's yes",
        }
        state.pending = Pending(
            "remember",
            anchor.space_id,
            None,
            True,
            card,
            state.turn,
            building_signature(bm),
            extra={
                "kind": fact_kind,
                "anchor": anchor.as_dict(),
                "text": clean,
                "valid_to": valid_to,
                "related": [other.as_dict() for other in others],
                "utterance": str(state.last_user_text)[:MAX_TEXT],
            },
        )
        return as_json(card)

    def open_facts_at(anchor: Anchor) -> list[dict]:
        store = store_of(state)
        current = now()
        filters = {"asset_id": anchor.asset_id} if anchor.asset_id else {}
        if anchor.element_id:
            filters = {"element_id": anchor.element_id}
        if not filters:
            filters = {"space_id": anchor.space_id}
        facts = [fact_dict(f) for f in store.query(bm, at=current, **filters)]
        return [f for f in facts if f.get("status") == "open"]

    @beta_tool
    def resolve_here(place: str | None = None, text: str = "") -> str:
        """The person says a reported problem or closure is fixed ('repariert', 'fixed', 'erledigt', 'works
        again'). Finds the open fact at the place and returns a card; nothing changes until the person's clear yes in
        the NEXT message and confirm_change. While guiding, a bare 'done'/'erledigt' is a step, not this.

        Args:
            place: The machine, room, lift or door, as the person named it; leave it out for 'here'.
            text: The person's words about what is fixed ('valve repaired'), used to pick the right fact.
        """
        card_guard()
        try:
            anchor = resolve_anchor(bm, state, place)
        except NeedsAnswer as asked:
            return as_json({**asked.payload, "resolved": False})
        candidates = open_facts_at(anchor)
        if not candidates:
            return as_json({"nothing_open": True, "place": anchor.label, "say": "Say nothing is open there."})
        wanted = set(words_of(text)) - set(words_of(DONE.pattern)) - {"the", "is", "ist", "der", "die", "das"}
        if len(candidates) > 1 and wanted:
            scored = sorted(candidates, key=lambda f: -len(wanted & set(words_of(f.get("text") or ""))))
            best = len(wanted & set(words_of(scored[0].get("text") or "")))
            if best and best > len(wanted & set(words_of(scored[1].get("text") or ""))):
                candidates = [scored[0]]
        current = now()
        if len(candidates) > 1:
            listed = "; ".join(f"{f.get('text')} ({since_words(f.get('valid_from'), current)})" for f in candidates[:5])
            return as_json({"needs_choice": True, "question": f"Which one is fixed: {listed}?", "resolved": False})
        fact = candidates[0]
        card = {
            "I understood": f"Mark as fixed at {anchor_label(bm, fact.get('anchor'))}: {fact.get('text')} "
            f"({since_words(fact.get('valid_from'), current)}, by {fact.get('author') or 'unknown'}).",
            "status": "nothing changed yet, waiting for the person's yes",
        }
        if fact.get("kind") == "closure":
            card["effect"] = "It opens again for routes."
        state.pending = Pending(
            "resolve",
            anchor.space_id,
            None,
            True,
            card,
            state.turn,
            building_signature(bm),
            extra={"fact_id": fact.get("id"), "text": " ".join(str(text or "resolved").split())[:MAX_TEXT]},
        )
        return as_json(card)

    @beta_tool
    def facts_here(
        place: str | None = None,
        history: bool = False,
        period: str | None = None,
        status: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        area: str | None = None,
        floor_id: str | None = None,
        person: str | None = None,
        closed_now: bool = False,
        show_photo: bool = False,
    ) -> str:
        """Read remembered notes, problems and timed closures: 'what's here?', 'notes for press 2', 'what was broken
        this week at press 2?' (history=true, period='this week'), 'open issues on pumps in hall A' (status='open',
        asset_type='pump', area='hall A'), 'what did technician A report?' (person), 'what is closed right now?'
        (closed_now=true), 'show me the photo' (show_photo=true). Say at most three, each in one short sentence with
        its 'since' and 'by' (and 'until' or 'resolved' when given). Never add facts the tool did not return.

        Args:
            place: A machine, room, lift or door; empty for 'here' when the person asks about their own place; the
                word 'all' for the whole building.
            history: True for the past too (fixed and expired), newest first.
            period: The person's time words ('this week', 'today', 'gestern', 'last 3 days').
            status: 'open', 'resolved' or 'expired' when the person asks for one.
            asset_type: Type of machine, snake_case ('pump', 'cnc_mill').
            category: Asset category when asked ('equipment').
            area: A hall, zone or area name ('hall A').
            floor_id: A floor id from the overview.
            person: Who reported it ('Technician A').
            closed_now: True for 'what is closed right now'.
            show_photo: True when the person wants to see a photo; the page opens it.
        """
        store = store_of(state)
        current = now()
        if closed_now:
            facts = [fact_dict(f) for f in store.active_closures(building_key(bm), at=current)]
            timed = {(f.get("anchor") or {}).get("element_id") for f in facts}
            lines = [spoken_fact(bm, f, current) for f in facts]
            lines += [
                {
                    "place": anchor_label(bm, {"element_id": e} if e not in bm.spaces else {"space_id": e}),
                    "until": "no end time",
                }
                for e in sorted(bm.closed)
                if e not in timed
            ]
            bm.found_facts = facts
            return as_json({"closed": lines, "count": len(lines), "say": "Name each with its until, briefly."})
        filters: dict = {"at": current, "history": bool(history or period or status in ("resolved", "expired"))}
        scope = "whole building"
        if place and str(place).strip().lower() not in ("all", "alle", "everything", "überall", "building"):
            try:
                anchor = resolve_anchor(bm, state, place)
            except NeedsAnswer as asked:
                return as_json(asked.payload)
            if anchor.asset_id:
                filters["asset_id"] = anchor.asset_id
            elif anchor.element_id:
                filters["element_id"] = anchor.element_id
            else:
                filters["space_id"] = anchor.space_id
            scope = anchor.label
        elif place is None and not any((area, floor_id, person, asset_type, category)) and state.position is not None:
            filters["space_id"] = state.position.space_id
            scope = room_label(bm, state.position.space_id)
        bounds = period_bounds(period, current)
        if bounds:
            filters["since"], filters["until"] = bounds
        for name, value in (
            ("status", status),
            ("asset_type", asset_type),
            ("category", category),
            ("area", area),
            ("floor_id", floor_id),
            ("person", person),
        ):
            if value:
                filters[name] = value.strip().lower().replace(" ", "_") if name == "asset_type" else value.strip()
        try:
            facts = [fact_dict(f) for f in store.query(bm, **filters)]
        except (MapError, ValueError, KeyError) as error:
            raise ToolError(str(error)) from error
        bm.found_facts = facts
        assets = [(f.get("anchor") or {}).get("asset_id") for f in facts]
        bm.located_asset_ids = [a for a in dict.fromkeys(assets) if a in bm.assets]
        lines = [spoken_fact(bm, f, current) for f in facts]
        result = {
            "scope": scope,
            "count": len(lines),
            "facts": lines[:MAX_SPOKEN] if not show_photo else lines,
            **({"more_on_screen": len(lines) - MAX_SPOKEN} if len(lines) > MAX_SPOKEN and not show_photo else {}),
            "say": "Nothing is noted there; say so." if not lines else "Say at most three, short, with since and by.",
        }
        if show_photo:
            photos = [line["photo"] for line in lines if line.get("photo")]
            bm.open_photo = photos[0] if photos else None
            result["photo"] = bm.open_photo
            result["say"] = "Say the photo is on screen." if photos else "Say there is no photo there."
        return as_json(result)

    return [remember_here, resolve_here, facts_here]
