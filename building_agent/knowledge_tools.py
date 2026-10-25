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

from building_agent.find_space import find_space
from building_agent.find_tools import find_asset, words_of
from building_agent.time_words import clock_of, names_a_time, until_time, when_is_later
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
        (
            rf"\b(?:{UNTIL_WORD} (?:the )?(?:end of (?:the |my |this )?(?:day|shift)|feierabend|schichtende|"
            r"dienstschluss|schicht(?:ende)?)|for the rest of the day|den rest des tages)\b"
        ),
    ),
    ("noon", rf"\b{UNTIL_WORD} (?:noon|midday|mittag)\b"),
    ("midnight", rf"\b{UNTIL_WORD} (?:midnight|mitternacht)\b"),
    ("clock", rf"\b{UNTIL_WORD} (\d{{1,2}})(?:[:.](\d{{2}}))? ?(uhr|h|am|pm|o'?clock)?(?!\S*\d)"),
    ("span", rf"\b{FOR_WORD} (\d+|{_COUNTS}|half an?|eine halbe) ?({_UNITS})\b"),
    (
        "unclear",
        (
            rf"\b(?:{UNTIL_WORD} (?:later|next \w+|nächste\w* \w+|naechste\w* \w+|später|spaeter|soon|bald|"
            rf"whenever|irgendwann|then|dann)|{FOR_WORD} (?:a while|some time|a bit|eine weile|einige zeit|"
            r"a few \w+|ein paar \w+))\b"
        ),
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
    """The end time in `text` ('bis morgen', 'until 14:00', 'for two hours'), or None if it names none.

    The phrase is found here; its time comes from time_words.until_time (the store's rules), with a fallback for
    the shift words it does not know ('bis Feierabend', 'until noon')."""
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
        shared = until_time(phrase, current)
        if shared is not None:
            return Until(phrase, shared)
        return own_until(kind, phrase, current)
    return None


def own_until(kind: str, phrase: str, current: datetime) -> Until:
    """Shift words time_words.until_time does not read ('bis Feierabend', 'until noon'). Anything else it could not
    read, or a time that is not in the future, is unclear and asked back."""
    if kind == "midnight":
        return Until(phrase, at_clock(current + timedelta(days=1), time(0, 0)))
    if kind in ("tonight", "shift", "noon"):
        clock = {"tonight": time(22, 0), "noon": time(12, 0)}.get(kind, SHIFT_END)
        end = at_clock(current, clock)
        if end > current:
            return Until(phrase, end)
    return Until(phrase, unclear=True)


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
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
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


def asset_in_text(bm: BuildingMap, space_id: str, text: str) -> str | None:
    """The one asset of this room the words name ('the drill press drips' in a zone with one drill press), else
    None. Several of that kind in the room, or none named: the note stays on the room."""
    said = f" {' '.join(words_of(text))} "
    named = [
        asset["id"]
        for asset in bm.assets.values()
        if asset["space_id"] == space_id
        and (f" {' '.join(words_of(asset['name']))} " in said or f" {' '.join(words_of(asset['type']))} " in said)
    ]
    kinds = {bm.assets[asset_id]["type"] for asset_id in named}
    return named[0] if len(named) == 1 and len(kinds) == 1 else None


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
    lowered = place.lower()
    rooms = [s["id"] for s in bm.spaces.values() if lowered in (s["name"].lower(), str(s.get("ref") or "").lower())]
    if len(rooms) == 1:  # an exact room name or number wins over a word search in the assets
        return space_anchor(bm, rooms[0])
    exact = [a["id"] for a in bm.assets.values() if a["name"].lower() == lowered]
    if len(exact) == 1:
        return asset_anchor(bm, exact[0])
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
    from building_agent.knowledge import building_of

    return building_of(bm)


def node_id(anchor: "Anchor") -> str:
    """The one id the store's `related` takes for a place: the asset, else the element, else the room."""
    return anchor.asset_id or anchor.element_id or anchor.space_id


def stored(call):
    """Run a store call; a refusal of the store (KnowledgeError, a ValueError) becomes a ToolError to read out."""
    try:
        return call()
    except ValueError as error:
        raise ToolError(f"Not stored: {error}") from error


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


# ---------- events and room bookings (docs/specs/events.md) ----------

NOW_WHEN = re.compile(r"\b(now|right now|currently|at the moment|jetzt|gerade|momentan|aktuell)\b", re.IGNORECASE)
CLOCK_AT = re.compile(
    r"\b(?:(?P<pre>at|um|gegen|ab|from|by)\s+)?(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))?\s*"
    r"(?P<ampm>am|pm|a\.m\.|p\.m\.)?\s*(?P<uhr>uhr|h\b|o'?clock)?",
    re.IGNORECASE,
)
DAY_PARTS = [  # (pattern, from hour, to hour) on the named day
    (r"\b(morning|vormittag|früh|frueh)\b", 6, 12),
    (r"\b(noon|midday|lunch ?time|mittag)\b", 11, 14),
    (r"\b(afternoon|nachmittag)\b", 12, 18),
    (r"\b(evening|tonight|abend)\b", 18, 24),
]
DAY_AFTER = re.compile(r"(?:\b|^)(übermorgen|uebermorgen|day after tomorrow)\b", re.IGNORECASE)
TOMORROW = re.compile(r"(?<![\wäöüß])(tomorrow|morgen)\b", re.IGNORECASE)
YESTERDAY = re.compile(r"\b(yesterday|gestern)\b", re.IGNORECASE)
WEEKDAY_WORD = re.compile(rf"\b({_DAYS})\b", re.IGNORECASE)
DATE_WORD = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?(?!\d)|\b(\d{4})-(\d{2})-(\d{2})\b")
AFTERNOON_HOURS = range(1, 7)  # 'at 2', 'um 3' without am/pm during a working day mean the afternoon
ASK_WHEN = "Which day and time do you mean? For example today at 15:00 or tomorrow morning."
TITLE_STOP = {"the", "a", "an", "der", "die", "das", "event", "events", "session", "is", "ist", "wann", "when", "where"}


@dataclass
class EventWindow:
    """The moment or period a question means; start == end for a moment ('at 14:00', 'now')."""

    start: datetime
    end: datetime
    words: str


def clock_in(text: str) -> tuple[int, int] | None:
    """(hour, minute) of a clock time in the words ('at 14:00', 'um 15 Uhr', '3pm', '14.30'), None without one.
    'at 2' or 'um 3' (1 to 6, no am/pm, no leading zero) is the afternoon: 14:00, 15:00."""
    for match in CLOCK_AT.finditer(text):
        if match.group("pre") or match.group("minute") or match.group("ampm") or match.group("uhr"):
            clock = clock_of(match)
            if clock is None:
                continue
            raw = match.group("hour")
            if not match.group("ampm") and clock[0] in AFTERNOON_HOURS and not raw.startswith("0"):
                return clock[0] + 12, clock[1]
            return clock
    return None


def named_day(text: str, midnight: datetime) -> tuple[datetime | None, str]:
    """The day the words name (today, tomorrow, übermorgen, yesterday, a weekday, 25.10. or 2026-10-25) at
    midnight, and the words with a date removed (so '12.10.' is never read as 12:10). None when no day is named."""
    date = DATE_WORD.search(text)
    if date:
        rest = text[: date.start()] + " " + text[date.end() :]
        try:
            if date.group(4):
                day = midnight.replace(year=int(date.group(4)), month=int(date.group(5)), day=int(date.group(6)))
            else:
                year = date.group(3)
                year = midnight.year if not year else int(year) + (2000 if len(year) == 2 else 0)
                day = midnight.replace(year=year, month=int(date.group(2)), day=int(date.group(1)))
        except ValueError:
            return None, rest
        return day, rest
    if DAY_AFTER.search(text):
        return midnight + timedelta(days=2), text
    if YESTERDAY.search(text):
        return midnight - timedelta(days=1), text
    if TOMORROW.search(text) and "heute morgen" not in text and "this morgen" not in text:
        return midnight + timedelta(days=1), text
    weekday = WEEKDAY_WORD.search(text)
    if weekday:
        return midnight + timedelta(days=(WEEKDAY[weekday.group(1).lower()] - midnight.weekday()) % 7), text
    if re.search(r"\b(today|heute)\b", text):
        return midnight, text
    return None, text


def forward_period(text: str, current: datetime) -> tuple[datetime, datetime] | None:
    """'this week' / 'this month' for events: the whole week or month, so upcoming events count too."""
    midnight = at_clock(current, time(0, 0))
    if re.search(r"\b(this week|diese woche|dieser woche|the week|der woche)\b", text):
        monday = midnight - timedelta(days=current.weekday())
        return monday, monday + timedelta(days=7)
    if re.search(r"\b(this month|diesen monat|diesem monat)\b", text):
        first = midnight.replace(day=1)
        return first, (first + timedelta(days=32)).replace(day=1)
    if re.search(r"\b(next week|nächste woche|naechste woche|nächsten woche|naechsten woche)\b", text):
        monday = midnight - timedelta(days=current.weekday()) + timedelta(days=7)
        return monday, monday + timedelta(days=7)
    return period_bounds(text, current)


def event_window(when: str | None, current: datetime) -> EventWindow | None:
    """What 'now', 'at 14:00', 'this afternoon', 'today', 'tomorrow morning', 'übermorgen', 'Friday', '25.10.',
    'this week' mean for events; None when the words name no time the tool can read (the caller asks back).
    'morgen früh' is tomorrow morning, 'heute morgen' this morning."""
    text = " ".join(str(when or "").lower().split())
    if not text:
        return None
    midnight = at_clock(current, time(0, 0))
    day, rest = named_day(text, midnight)
    clock = clock_in(rest)
    if NOW_WHEN.search(text) and clock is None and day is None:
        return EventWindow(current, current, "now")
    if day is None and DATE_WORD.search(text):
        return None  # an impossible date ('31.02.')
    base = day if day is not None else midnight
    label = day_words(base, current)
    if clock is not None:
        moment = base.replace(hour=clock[0], minute=clock[1])
        return EventWindow(moment, moment, f"{label} {clock_words(moment)}")
    for pattern, begin, finish in DAY_PARTS:
        if re.search(pattern, rest) or ("heute morgen" in text and begin == 6):
            return EventWindow(base + timedelta(hours=begin), base + timedelta(hours=finish), f"{label} {text}")
    if day is not None:
        return EventWindow(day, day + timedelta(days=1), label)
    bounds = forward_period(text, current)
    if bounds:
        return EventWindow(bounds[0], bounds[1], text)
    return None


def event_spaces(bm: BuildingMap, fact: dict) -> list[str]:
    """Rooms of an event: its anchor room first, then the rooms of its related places."""
    from building_agent.knowledge import node_spaces

    found = [(fact.get("anchor") or {}).get("space_id")]
    for node in fact.get("related") or []:
        found += node_spaces(bm, node)
    return [space for space in dict.fromkeys(found) if space in bm.spaces]


def stem(word: str) -> str:
    for ending in ("es", "s", "en", "e"):
        if len(word) > 4 and word.endswith(ending):
            return word[: -len(ending)]
    return word


def title_score(query: str | None, title: str) -> int:
    """How many of the query's words the title has (plural and German endings ignored)."""
    wanted = {stem(word) for word in words_of(query or "") if word not in TITLE_STOP and len(word) > 1}
    have = {stem(word) for word in words_of(title)}
    return len(wanted & have)


def event_line(bm: BuildingMap, fact: dict, current: datetime) -> dict:
    """One event as Wanda reads it: title, rooms, start and end in words, running now, by."""
    start, end = as_time(fact.get("valid_from")), as_time(fact.get("valid_to"))
    starts = f"{day_words(start, current)} {clock_words(start)}"
    ends = f"{day_words(end, current)} {clock_words(end)}" if end else "open end"
    same_day = end is not None and start.date() == end.date()
    running = start <= current and (end is None or current < end)
    return {
        "title": fact.get("text"),
        "rooms": [room_label(bm, space) for space in event_spaces(bm, fact)],
        "when": f"{starts} to {clock_words(end)}" if same_day else f"{starts} to {ends}",
        "starts": starts,
        "ends": ends,
        "running_now": running,
        "status": "running now" if running else ("ended" if end is not None and end <= current else "upcoming"),
        "by": fact.get("author") or "unknown",
    }


def overlaps(fact: dict, start: datetime, end: datetime) -> bool:
    """The event runs at the moment `start` (start == end) or overlaps the period [start, end)."""
    begins, ends = as_time(fact.get("valid_from")), as_time(fact.get("valid_to"))
    if start == end:
        return begins <= start and (ends is None or start < ends)
    return begins < end and (ends is None or ends > start)


def all_events(bm: BuildingMap, store, current: datetime) -> list[dict]:
    """Every event of the building (past, running, upcoming), never a resolved one."""
    return [
        fact_dict(fact)
        for fact in store.query(bm, status="all", at=current)
        if fact.kind == "event" and not fact.resolves and fact.status != "resolved"
    ]


def search_events(
    bm: BuildingMap,
    store,
    current: datetime,
    query: str | None = None,
    when: str | None = None,
    space_ids: set[str] | None = None,
) -> tuple[list[dict], EventWindow | None]:
    """Events (store dicts) matching title words, time and rooms, sorted by start. Without a time: every matching
    event when a title is named, else the ones not ended yet."""
    window = event_window(when, current)
    events = all_events(bm, store, current)
    if space_ids:
        events = [fact for fact in events if set(event_spaces(bm, fact)) & space_ids]
    if window is not None:
        events = [fact for fact in events if overlaps(fact, window.start, window.end)]
    if query and title_score(query, query):
        scores = [title_score(query, fact.get("text") or "") for fact in events]
        best = max(scores, default=0)
        events = [fact for fact, score in zip(events, scores, strict=True) if best and score == best]
    elif window is None:
        events = [fact for fact in events if as_time(fact.get("valid_to")) > current]
    events.sort(key=lambda fact: (as_time(fact.get("valid_from")), fact.get("text") or ""))
    return events, window


def room_free(bm: BuildingMap, store, space_id: str, current: datetime, when: str | None = None) -> dict:
    """Is the room free at that moment (or for that whole period)? {free, time, busy_with: [event lines]}; without
    `when` it means now. Time words it cannot read give only the question back, never a guess at `free`."""
    window = event_window(when, current)
    if window is None and when and str(when).strip():
        return {"time_not_understood": when, "question": ASK_WHEN}
    window = window or EventWindow(current, current, "now")
    busy = [
        fact
        for fact in all_events(bm, store, current)
        if space_id in event_spaces(bm, fact) and overlaps(fact, window.start, window.end)
    ]
    return {
        "free": not busy,
        "time": window.words,
        "busy_with": [event_line(bm, fact, current) for fact in busy],
    }


# ---------- confirm_change calls this for remember and resolve ----------


def apply_pending(bm: BuildingMap, state, pending) -> dict:
    """Store what the card said, after the clear yes. Returns the tool result body."""
    store = store_of(state)
    extra = pending.extra or {}
    current = now()
    if pending.action == "remember":
        fact = stored(
            lambda: store.add(
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
        ).to_dict()
        state.last_fact = {"id": fact.get("id"), "at": current, "building": building_key(bm)}
        return {"stored": True, "fact": spoken_fact(bm, fact, current), "say": "Say in one short sentence it is noted."}
    stored(
        lambda: store.resolve(
            bm, extra["fact_id"], text=extra.get("text") or "resolved", author=author_of(state), now=current
        )
    )
    state.last_fact = None
    if extra.get("kind") == "closure":  # the element opens again for routes right now
        from building_agent.knowledge import apply_timed_closures

        apply_timed_closures(bm, store, current)
    return {
        "resolved": True,
        "fact": {"text": extra.get("old_text"), "place": extra.get("place"), "resolved": "now"},
        "say": "Say in one short sentence it is marked fixed.",
    }


def store_closure(bm: BuildingMap, state, element_id: str, until: datetime, reason: str | None) -> dict:
    """A confirmed timed closure becomes a closure fact, so it ends by itself at `until`."""
    store = store_of(state)
    current = now()
    anchor = element_anchor(bm, element_id, state) if element_id not in bm.spaces else space_anchor(bm, element_id)
    data = anchor.as_dict()
    data["element_id"] = element_id
    data["point"] = None
    fact = stored(
        lambda: store.add(
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
    ).to_dict()
    state.last_fact = {"id": fact.get("id"), "at": current, "building": building_key(bm)}
    # closed by apply_change already; mark it as a fact closure so apply_timed_closures reopens it at the end
    bm.fact_closed = set(getattr(bm, "fact_closed", set())) | {element_id}
    return fact


def end_closures(bm: BuildingMap, state, element_id: str) -> int:
    """A confirmed reopen ends the closure facts of that element, so they do not close it again."""
    store = getattr(state, "knowledge", None)
    if store is None:
        return 0
    current = now()
    ended = 0
    for fact in store.query(bm, element_id=element_id, at=current):
        if fact.kind == "closure" and (fact.anchor or {}).get("element_id") == element_id:
            stored(lambda f=fact: store.resolve(bm, f.id, text="reopened", author=author_of(state), now=current))
            ended += 1
    return ended


def undo_fact(bm: BuildingMap, state, snapshot) -> None:
    """Undo of a stored fact: only right after it was made (2 minutes), else it has to be resolved instead."""
    made = getattr(snapshot, "fact_at", None)
    if made is None:
        return
    if now().timestamp() - made.timestamp() > UNDO_WINDOW.total_seconds():  # real seconds, also across DST
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
            if anchor.asset_id is None and anchor.element_id is None:  # 'here: the drill press drips'
                named = asset_in_text(bm, anchor.space_id, clean)
                anchor = asset_anchor(bm, named) if named else anchor
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
                "related": [node_id(other) for other in others],
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
        return [f for f in facts if f.get("status") == "open" and f.get("kind") != "event"]

    def only_open_match(place: str | None) -> Anchor | None:
        """The anchor of the one open fact whose place the words name, when the words alone match several places."""
        wanted = set(words_of(place or "")) - {"the", "a", "der", "die", "das"}
        if not wanted:
            return None
        anchors = {}
        for fact in store_of(state).query(bm, at=now()):
            if fact.kind == "event":  # a booking is never 'fixed'
                continue
            found = fact.anchor or {}
            label = anchor_label(bm, found)
            if wanted <= set(words_of(label)):
                anchors[(found.get("asset_id"), found.get("element_id"), found.get("space_id"))] = found
        if len(anchors) != 1:
            return None
        found = next(iter(anchors.values()))
        if found.get("asset_id") in bm.assets:
            return asset_anchor(bm, found["asset_id"])
        if found.get("element_id") in bm.connectors or found.get("element_id") in bm.openings:
            return element_anchor(bm, found["element_id"], state)
        return space_anchor(bm, found["space_id"])

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
            single = only_open_match(place)  # 'the drill press is fixed': only one drill press has an open problem
            if single is None:
                return as_json({**asked.payload, "resolved": False})
            anchor = single
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
            extra={
                "fact_id": fact.get("id"),
                "text": " ".join(str(text or "resolved").split())[:MAX_TEXT],
                "kind": fact.get("kind"),
                "old_text": fact.get("text"),
                "place": anchor_label(bm, fact.get("anchor")),
            },
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
            facts = [
                fact_dict(f) for f in store.query(bm, at=current) if f.kind == "closure" and f.anchor.get("element_id")
            ]
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
        filters: dict = {"at": current, "history": bool(history or (period and not status))}
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
            facts = [fact_dict(f) for f in store.query(bm, **filters) if f.kind != "event"]  # events: find_events
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
            photos = [{"fact_id": line["id"], "photo": line["photo"]} for line in lines if line.get("photo")]
            bm.open_photo = photos[0] if photos else None
            result["photo"] = bm.open_photo
            result["say"] = "Say the photo is on screen." if photos else "Say there is no photo there."
        return as_json(result)

    def event_rooms(place: str) -> set[str] | dict:
        """The room(s) a place names for events; a name several rooms share is narrowed to rooms with events,
        else the question to ask comes back as a dict."""
        if is_here(place):
            here = getattr(getattr(state, "position", None), "space_id", None)
            if here is None:
                return {"where_are_you": True, "question": "Where are you? Name the room."}
            return {here}
        try:
            return {resolve_anchor(bm, state, place).space_id}
        except NeedsAnswer as asked:
            wanted = set(words_of(place)) - TITLE_STOP
            rooms = {
                space
                for fact in all_events(bm, store_of(state), now())
                for space in event_spaces(bm, fact)
                if wanted
                and wanted
                <= {stem(w) for w in words_of(bm.spaces[space]["name"])} | set(words_of(bm.spaces[space]["name"]))
            }
            return rooms if len(rooms) == 1 else asked.payload

    @beta_tool
    def find_events(query: str | None = None, when: str | None = None, place: str | None = None) -> str:
        """Events, sessions, deadlines and room bookings with their time and room: 'where are the pitches?'
        (query='pitches'), 'wann ist der Code Freeze?' (query='code freeze'), 'what is on this afternoon?'
        (when='this afternoon'), 'what is happening now?' (when='now'), 'is the Project Room free at 10:00?'
        (place='Project Room', when='at 10:00'; the result says free and busy_with). Say title, room and time from
        the result only, then offer the way there (give_directions to the room). Never for a message with 'Answer:'.

        Args:
            query: Words of the event's title as the person said them ('pitches', 'lunch', 'code freeze'); leave it
                out for 'is room X free'.
            when: The person's time words ('now', 'today', 'at 14:00', 'um 15 Uhr', 'this afternoon').
            place: A room the person asks about ('Project Room', 'seminar room').
        """
        if benchmark(state):
            raise ToolError("No events in a message with 'Answer:'. Answer the question only.")
        store = store_of(state)
        current = now()
        rooms = event_rooms(place) if place else None
        if isinstance(rooms, dict):
            return as_json(rooms)
        if when and str(when).strip() and event_window(when, current) is None:
            return as_json({"time_not_understood": when, "question": ASK_WHEN, "say": "Ask this question only."})
        events, window = search_events(bm, store, current, query, when, rooms)
        lines = [event_line(bm, fact, current) for fact in events]
        bm.found_facts = events
        result: dict = {"now": f"today {clock_words(current)}", "count": len(lines), "events": lines[:5]}
        if window is not None:
            result["time"] = window.words
        if rooms:
            space_id = min(rooms)
            result["place"] = room_label(bm, space_id)
            if not query:
                result.update(room_free(bm, store, space_id, current, when))
        if lines:
            result["say"] = (
                "Name each event with title, room and time from this result only (at most three), then offer the "
                "way to its room."
            )
        elif result.get("free"):
            result["say"] = "Say the room is free then; invent nothing."
        else:
            result["say"] = "Nothing matching is planned; say so, invent no event, time or room."
        return as_json(result)

    return [remember_here, resolve_here, facts_here, find_events]
