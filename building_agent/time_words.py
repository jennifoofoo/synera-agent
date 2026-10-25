"""Time words in the person's own message. Scheduling a change does not exist (docs/specs/live-updates.md), so a
message that names a time never changes the building. Decided here on the user's text, not on what the model passes.

'now', 'right now', 'today', 'jetzt', 'heute' are not time words in this sense: the change is meant for now."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|wochenende"
PATTERN = re.compile(
    r"\b(?:"
    r"tomorrow|day after tomorrow|tonight|this (?:evening|afternoon|weekend)"
    rf"|next (?:week|month|year|{WEEKDAYS})"
    rf"|(?:from|on|until|till|by|every) (?:{WEEKDAYS}|midnight|noon)"
    r"|in \d+ (?:minutes?|hours?|days?|weeks?)"
    r"|(?:at )?\d{1,2}(?::\d{2})? ?(?:am|pm)"
    r"|übermorgen|uebermorgen"
    r"|nächste[nrms]? (?:woche|monat|jahr)|naechste[nrms]? (?:woche|monat|jahr)"
    rf"|(?:ab|am|bis|jeden|nächsten|naechsten) (?:{WEEKDAYS})"
    r"|um \d{1,2}(?::\d{2})? uhr"
    r"|heute (?:abend|nacht)"
    r"|in \d+ (?:minuten|stunden|tagen|wochen)"
    r")\b"
    r"|(?<!guten )\bmorgen\b",
    re.IGNORECASE,
)
NOW_WORDS = {"now", "right now", "today", "jetzt", "heute", "sofort", "immediately", "at once"}
SCHEDULED_REPLY = {
    "scheduled": False,
    "note": "The building can only be changed now, scheduling does not exist. Tell the person, offer to make the "
    "change now (then propose it) or to leave it. Change nothing.",
}


def names_a_time(text: str | None) -> bool:
    """True if the text names a point in time other than now."""
    return bool(text) and PATTERN.search(str(text)) is not None


def when_is_later(when: str | None) -> bool:
    """The model's `when` argument: anything except an empty value or a now-word means later."""
    cleaned = " ".join(str(when or "").lower().split())
    return bool(cleaned) and cleaned not in NOW_WORDS


# ---------- end of a validity window ("bis morgen", "for 2 hours"), see docs/specs/place-knowledge.md ----------

BERLIN = ZoneInfo("Europe/Berlin")
SHIFT_END_HOUR = 18  # "bis morgen" / "bis Freitag" mean the end of that day's shift
MORNING_HOUR = 8
TONIGHT_HOUR = 22
DAY_NAMES = {
    "monday": 0, "montag": 0, "tuesday": 1, "dienstag": 1, "wednesday": 2, "mittwoch": 2,
    "thursday": 3, "donnerstag": 3, "friday": 4, "freitag": 4, "saturday": 5, "samstag": 5,
    "sunday": 6, "sonntag": 6,
}  # fmt: skip
NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "ein": 1, "eine": 1, "einen": 1, "einer": 1, "two": 2, "zwei": 2, "three": 3,
    "drei": 3, "four": 4, "vier": 4, "five": 5, "fünf": 5, "fuenf": 5, "six": 6, "sechs": 6, "seven": 7,
    "sieben": 7, "eight": 8, "acht": 8, "nine": 9, "neun": 9, "ten": 10, "zehn": 10, "twelve": 12, "zwölf": 12,
    "zwoelf": 12, "couple of": 2, "paar": 2,
}  # fmt: skip
UNITS = {
    "minute": 60, "minutes": 60, "minuten": 60, "min": 60, "hour": 3600, "hours": 3600, "stunde": 3600,
    "stunden": 3600, "h": 3600, "day": 86400, "days": 86400, "tag": 86400, "tage": 86400, "tagen": 86400,
    "week": 604800, "weeks": 604800, "woche": 604800, "wochen": 604800,
}  # fmt: skip
UNTIL = r"(?:bis|until|till|til|through|by)"
CLOCK = r"(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)?\s*(?:uhr|h\b|o'?clock)?"
DURATION = re.compile(
    r"\b(?:für|fuer|for|noch)\s+(?:die\s+nächsten\s+|die\s+naechsten\s+|the\s+next\s+)?"
    rf"(?P<count>\d+(?:[.,]\d+)?|{'|'.join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True))})"
    rf"\s*(?P<unit>{'|'.join(sorted(UNITS, key=len, reverse=True))})\b",
    re.IGNORECASE,
)
HALF_HOUR = re.compile(r"\b(?:für|fuer|for)\s+(?:eine\s+halbe\s+stunde|half\s+an\s+hour)\b", re.IGNORECASE)
DAY_WORD = re.compile(
    rf"\b{UNTIL}\s+(?:(?:end\s+of\s+(?:the\s+)?week|ende\s+der\s+woche|(?:zum\s+)?wochenende|the\s+weekend)"
    r"|(?P<day>übermorgen|uebermorgen|day after tomorrow|heute\s+abend|tonight|morgen|tomorrow|heute|today"
    rf"|{'|'.join(DAY_NAMES)}))"
    r"(?:\s+(?P<part>früh|frueh|morgen|morning|abend|evening|mittag|noon|nachmittag|afternoon))?"
    rf"(?:\s*(?:um|at|,)?\s*{CLOCK})?",
    re.IGNORECASE,
)
UNTIL_CLOCK = re.compile(rf"\b{UNTIL}\s+(?:um\s+|at\s+)?{CLOCK}", re.IGNORECASE)
PART_HOURS = {
    "früh": MORNING_HOUR, "frueh": MORNING_HOUR, "morgen": MORNING_HOUR, "morning": MORNING_HOUR,
    "mittag": 12, "noon": 12, "nachmittag": 15, "afternoon": 15, "abend": 20, "evening": 20,
}  # fmt: skip


def berlin_now(now: datetime | None = None) -> datetime:
    """`now` as an aware Europe/Berlin time; a naive value counts as Berlin local time."""
    if now is None:
        return datetime.now(BERLIN)
    return now.replace(tzinfo=BERLIN) if now.tzinfo is None else now.astimezone(BERLIN)


def clock_of(match: re.Match) -> tuple[int, int] | None:
    """(hour, minute) of a CLOCK group, None if absent or impossible."""
    if not match.group("hour"):
        return None
    hour, minute = int(match.group("hour")), int(match.group("minute") or 0)
    ampm = (match.group("ampm") or "").replace(".", "").lower()
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if hour == 24 and minute == 0:
        hour, minute = 23, 59
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def at_clock(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def until_time(text: str | None, now: datetime | None = None) -> datetime | None:
    """End of a validity window named in the person's words, as an aware Europe/Berlin datetime.

    'bis morgen' / 'until tomorrow' -> tomorrow 18:00; 'bis Freitag' -> the next Friday 18:00 (today if it is
    Friday before 18:00); 'bis 14 Uhr' -> today 14:00 (tomorrow if that has passed); 'für 2 Stunden' -> now + 2 h;
    'bis morgen 10 Uhr', 'bis Freitag früh', 'bis Ende der Woche' (Friday 18:00) work too. Anything unclear or a
    time that is not in the future -> None, and the caller asks back."""
    if not text:
        return None
    current = berlin_now(now)
    lowered = " ".join(str(text).lower().split())
    if HALF_HOUR.search(lowered):
        return (current.astimezone(UTC) + timedelta(minutes=30)).astimezone(BERLIN)
    found = DURATION.search(lowered)
    if found:
        raw = found.group("count").replace(",", ".")
        count = float(raw) if raw[0].isdigit() else NUMBER_WORDS[raw]
        seconds = count * UNITS[found.group("unit")]
        if not 0 < seconds <= 366 * 86400:
            return None
        return (current.astimezone(UTC) + timedelta(seconds=seconds)).astimezone(BERLIN)  # real hours over DST
    found = DAY_WORD.search(lowered)
    if found:
        return day_word_time(found, current)
    found = UNTIL_CLOCK.search(lowered)
    if found:
        clock = clock_of(found)
        if clock is None:
            return None
        target = at_clock(current, *clock)
        return target if target > current else target + timedelta(days=1)
    return None


def day_word_time(found: re.Match, current: datetime) -> datetime | None:
    day = " ".join((found.group("day") or "").split())
    whole = found.group(0)
    if not day:  # end of the week / weekend
        if "wochenende" in whole or "weekend" in whole:
            return at_clock(current + timedelta(days=(6 - current.weekday()) % 7), 23, 59)
        target = at_clock(current + timedelta(days=(4 - current.weekday()) % 7), SHIFT_END_HOUR)
        return target if target > current else target + timedelta(days=7)
    if day in ("heute abend", "tonight"):
        base, default_hour = current, TONIGHT_HOUR
    elif day in ("heute", "today"):
        base, default_hour = current, SHIFT_END_HOUR
    elif day in ("morgen", "tomorrow"):
        base, default_hour = current + timedelta(days=1), SHIFT_END_HOUR
    elif day in ("übermorgen", "uebermorgen", "day after tomorrow"):
        base, default_hour = current + timedelta(days=2), SHIFT_END_HOUR
    else:
        base, default_hour = current + timedelta(days=(DAY_NAMES[day] - current.weekday()) % 7), SHIFT_END_HOUR
    if found.group("hour") and clock_of(found) is None:
        return None
    part = found.group("part")
    hour, minute = clock_of(found) or ((PART_HOURS[part], 0) if part else (default_hour, 0))
    target = at_clock(base, hour, minute)
    if target <= current and day in DAY_NAMES:  # "bis Freitag" said on Friday evening: next week's Friday
        target += timedelta(days=7)
    return target if target > current else None
