"""Time words in the person's own message. Scheduling a change does not exist (docs/specs/live-updates.md), so a
message that names a time never changes the building. Decided here on the user's text, not on what the model passes.

'now', 'right now', 'today', 'jetzt', 'heute' are not time words in this sense: the change is meant for now."""

import re

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
