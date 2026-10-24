"""Voice output for the 2D page: shorten an agent reply for speaking, and turn text into MP3 via ElevenLabs.

Stdlib only. The API key is read from the environment at request time and never logged or put in messages.
language_code is not sent: eleven_flash_v2_5 detects German and English from the text itself.
spoken_version() puts <break time="..." /> tags into the text for pauses; both models accept them.
"""

import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={output_format}"
TIMEOUT_SECONDS = 5
TOTAL_DEADLINE_SECONDS = 8
MAX_STEPS = 3

# http(url, headers, body, timeout) -> (status, bytes)
HttpFunction = Callable[[str, dict, bytes, float], tuple[int, bytes]]


class SpeechError(Exception):
    """Text-to-speech failed. The message is safe to show to the page (never contains the key)."""


# ---------- shortening for speech ----------

ANSWER_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?answer(?:\*\*)?\s*:", re.IGNORECASE)
# A route step: "1. Go left" or "Step 1: Go left". Steps are read as "Step one, ..." (a sequence of actions),
# unlike list items ("First, ...").
NUMBERED = re.compile(r"^\s*(?:[-*]\s*)?(?:\d+[.)]|(?:step|schritt)\s+\d+\s*[:.)-]?)\s+(.*)$", re.IGNORECASE)
STEP_LABEL = re.compile(r"^(?:step|schritt)\s+\d+\s*[:.)-]?\s+", re.IGNORECASE)
STEP_WORD = {"en": "Step", "de": "Schritt"}
BULLET = re.compile(r"^\s*[-*+]\s+")
HEADING = re.compile(r"^\s*#{1,6}\s*")
# Dataset ids: a source prefix plus hyphenated segments with a digit, or a trailing -F<n>-S<nnn> shape.
# Dates (2026-10-24) and refs (0-12-B) do not match.
RAW_ID = re.compile(
    r"\b(?:(?=[\w-]*\d)(?:proc|osm|resplan|swiss)(?:-[A-Za-z0-9]+)+|[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-F-?\d+-S\d{3,})\b"
)
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
TABLE_ROW = re.compile(r"^\s*\|")
RULE_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
BRACKETED = re.compile(r"\s*\[[^\]]*\]")
EMPTY_PARENS = re.compile(r"\s*\(\s*[,;]?\s*\)")
CARD_START = (re.compile(r"i understood", re.IGNORECASE), re.compile(r"ich habe verstanden", re.IGNORECASE))
CARD_MARKER = re.compile(
    r"i understood|effect on your last route|waiting for the person's yes|ich habe verstanden", re.IGNORECASE
)
DEFAULT_LANG = "en"
# Split after . ! ? but not after common abbreviations.
SENTENCE_END = re.compile(
    r"(?<=[.!?])(?<!\bz\. B\.)(?<!\bz\.B\.)(?<!\bd\. h\.)(?<!\bd\.h\.)(?<!\bbzw\.)(?<!\bca\.)"
    r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bapprox\.)(?<!\betc\.)(?<!\bvs\.)\s+"
)
SQUARE_METRES = re.compile(r"(?<=\d)\s*(?:m2|m²)(?!\w)")
METRES = re.compile(r"(?<=\d)\s*m(?![\w²])")
WC = re.compile(r"\bWC\b")


def _strip_markdown(line: str) -> str:
    line = HEADING.sub("", line)
    line = line.replace("**", "").replace("__", "").replace("`", "")
    return line.strip()


def _remove_ids(text: str) -> str:
    text = MD_LINK.sub(r"\1", text)
    text = BRACKETED.sub("", text)
    text = RAW_ID.sub("", text)
    text = EMPTY_PARENS.sub("", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


UNITS = {
    "en": (" square metres", " metres", "toilet"),
    "de": (" Quadratmeter", " Meter", "W C"),
}

# ---------- pauses ----------
# Pause lengths in seconds. Tags are only ever generated here, never copied from a reply.
PAUSE_HEADLINE = 0.8  # after the headline sentence (destination and length)
PAUSE_ITEM = 0.8  # between steps and between list items
PAUSE_QUESTION = 1.2  # before a closing question, so the person can answer
TAG_LIKE = re.compile(r"<[^<>]*>")

# ---------- numbers and codes (all spelling lives here) ----------

ROOM_WORDS = (
    r"labs?|offices?|rooms?|halls?|kitchens?|toilets?|staircases?|lifts?|räume?|raum|büros?|labore?|küche|"
    r"treppenhaus|aufzug|corridors?|flur|korridor"
)
# A room word, up to two more words ("Office corridor 0.16"), then one or more dotted refs.
UNIT_WORDS = r"(?i:m\b|m2|m²|metres|meters|square|meter|quadratmeter)"
ROOM_REF_LIST = re.compile(
    rf"\b(?:{ROOM_WORDS})(?:\s+[A-Za-zäöüß]+){{0,2}}?\s+\d+\.\d+(?:\s*(?:,|and|und|or|oder)\s*\d+\.\d+)*"
    rf"(?!\d)(?!\s*{UNIT_WORDS})",
    re.IGNORECASE,
)
UNIT_FOLLOWS = re.compile(rf"\s*{UNIT_WORDS}")
DOTTED_NUMBER = re.compile(rf"(?<![\d.])\d+\.\d+(?!\d)(?!\s*{UNIT_WORDS})")
PLAIN_DECIMAL = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?!\d)(?!\.\d)")
ZONE_CODE = re.compile(r"\b([A-Z])-([A-Z])(\d+)\b")
SHORT_REF = re.compile(r"\b([A-Z])(\d{3,5})\b")
FLOOR_LABEL = re.compile(r"\b(?:(?i:floor|level|storey|etage|geschoss)\s+)?F(-?)(\d)\b")
FLOOR_NUMBER = re.compile(r"\b(floor|level|storey|etage|geschoss)(\s+)(-?)(\d)\b", re.IGNORECASE)
DIGIT_WORDS = {
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
    "de": ("null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"),
}
POINT_WORD = {"en": "point", "de": "Punkt"}  # room refs: 0.12 -> zero point one two
DECIMAL_WORD = {"en": "point", "de": "Komma"}  # measurements: 36.48 -> thirty six point four eight
MINUS_WORD = {"en": "minus", "de": "minus"}
FLOOR_WORD = {"en": "floor", "de": "Etage"}
TEENS_AND_TENS = {
    "en": (
        ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"],
        ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"],
    ),
    "de": (
        ["zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"],
        ["zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"],
    ),
}


def _digit_words(digits: str, lang: str) -> str:
    words = DIGIT_WORDS[lang]
    return " ".join(words[int(c)] for c in digits)


def _int_words(number: int, lang: str) -> str:
    """0..999 in words; larger numbers stay as digits (the voice reads them fine)."""
    if number > 999:
        return str(number)
    teens, tens = TEENS_AND_TENS[lang]
    ones = DIGIT_WORDS[lang]
    hundreds, rest = divmod(number, 100)
    parts = []
    if hundreds:
        parts.append(
            f"{ones[hundreds]} hundred" if lang == "en" else f"{'ein' if hundreds == 1 else ones[hundreds]}hundert"
        )
    if rest or not hundreds:
        ten, one = divmod(rest, 10)
        if rest < 10:
            parts.append(ones[rest])
        elif rest < 20:
            parts.append(teens[rest - 10])
        elif not one:
            parts.append(tens[ten - 2])
        elif lang == "en":
            parts.append(f"{tens[ten - 2]} {ones[one]}")
        else:
            parts.append(f"{'ein' if one == 1 else ones[one]}und{tens[ten - 2]}")
    return (" " if lang == "en" else "").join(parts)


def _spell_ref(whole: str, fraction: str, lang: str) -> str:
    return f"{_digit_words(whole, lang)} {POINT_WORD[lang]} {_digit_words(fraction, lang)}"


def _spell_room_refs(text: str, lang: str) -> str:
    """Room refs like 0.12 are read digit by digit; measurements (63.4 m) are read as numbers."""

    def spell(match: re.Match) -> str:
        return _spell_ref(*match.group().split("."), lang)

    return ROOM_REF_LIST.sub(lambda group: DOTTED_NUMBER.sub(spell, group.group()), text)


def _spell_decimals(text: str, lang: str) -> str:
    """Leftover decimals: a bare 1.30 is a room ref, anything else (36.48 metres, 12.5) is a number."""

    def spell(match: re.Match) -> str:
        whole, fraction = match.group(1), match.group(2)
        unit_follows = UNIT_FOLLOWS.match(text, match.end())
        if len(whole) == 1 and len(fraction) == 2 and not unit_follows:
            return _spell_ref(whole, fraction, lang)
        return f"{_int_words(int(whole), lang)} {DECIMAL_WORD[lang]} {_digit_words(fraction, lang)}"

    return PLAIN_DECIMAL.sub(spell, text)


def _spell_codes(text: str, lang: str) -> str:
    """Zone codes (H-A1), short refs (N3806) and floor labels (F1, floor 2)."""
    text = ZONE_CODE.sub(lambda m: f"{m.group(1)} {m.group(2)} {_digit_words(m.group(3), lang)}", text)
    text = SHORT_REF.sub(lambda m: f"{m.group(1)} {_digit_words(m.group(2), lang)}", text)
    text = FLOOR_LABEL.sub(
        lambda m: (
            f"{FLOOR_WORD[lang]} {MINUS_WORD[lang] + ' ' if m.group(1) else ''}{DIGIT_WORDS[lang][int(m.group(2))]}"
        ),
        text,
    )
    return FLOOR_NUMBER.sub(
        lambda m: (
            f"{m.group(1)}{m.group(2)}{MINUS_WORD[lang] + ' ' if m.group(3) else ''}{DIGIT_WORDS[lang][int(m.group(4))]}"
        ),
        text,
    )


def _pronounce(text: str, lang: str = DEFAULT_LANG) -> str:
    lang = lang if lang in UNITS else DEFAULT_LANG
    square, metres, toilet = UNITS[lang]
    text = SQUARE_METRES.sub(square, text)
    text = METRES.sub(metres, text)
    text = _spell_room_refs(text, lang)
    text = _spell_decimals(text, lang)
    text = _spell_codes(text, lang)
    return WC.sub(toilet, text)


# ---------- lists ----------

# "Welding station H-A1 in Production zone H-A1 Welding station H-A4 in ...": a zone code followed by a
# capitalised word without punctuation starts the next list item.
RUN_ON_BOUNDARY = re.compile(r"(\b(?i:zone|bereich)\s+[A-Z]-[A-Z]\d+)\s+(?=[A-Z][a-zäöü])")
ORDINALS = {
    "en": ("First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"),
    "de": (
        "Erstens",
        "Zweitens",
        "Drittens",
        "Viertens",
        "Fünftens",
        "Sechstens",
        "Siebtens",
        "Achtens",
        "Neuntens",
        "Zehntens",
    ),
}


def _end_sentence(text: str) -> str:
    return text if text[-1] in ".!?" else text + "."


def _split_run_on(sentence: str) -> list[str]:
    """Split a run-on list into its items. A lead-in before a colon becomes its own piece."""
    marked = RUN_ON_BOUNDARY.sub(r"\1|", sentence)
    if "|" not in marked:
        return [sentence]
    pieces = [p.strip() for p in marked.split("|") if p.strip()]
    lead, sep, rest = pieces[0].partition(": ")
    if sep and rest:
        pieces[0:1] = [lead + ":", rest]
    return pieces


def _number_items(items: list[str], lang: str) -> list[str]:
    words = ORDINALS.get(lang, ORDINALS[DEFAULT_LANG])
    if len(items) < 2 or len(items) > len(words):
        return items
    numbered = []
    for word, item in zip(words, items, strict=False):
        head = item[0].lower() + item[1:] if item[1:2].islower() else item
        numbered.append(f"{word}, {head}")
    return numbered


# ---------- building the spoken text ----------


def _sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(text.strip()) if s]


def _card_core(text: str) -> list[str]:
    """Confirmation card: keep the first sentence from the marker on plus the closing question."""
    sentences = _sentences(text)
    start = 0
    for marker in (*CARD_START, CARD_MARKER):  # English wording first, German second
        found = next((i for i, s in enumerate(sentences) if marker.search(s)), None)
        if found is not None:
            start = found
            break
    core = [sentences[start]]
    question = next((s for s in reversed(sentences[start + 1 :]) if s.endswith("?")), None)
    if question:
        core.append(question)
    return core


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    kept = ""
    for sentence in _sentences(text):
        candidate = f"{kept} {sentence}".strip()
        if len(candidate) > limit:
            break
        kept = candidate
    if kept:
        return kept
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return (cut or text[:limit]) + "."


def _more_steps(count: int, lang: str = DEFAULT_LANG) -> str:
    if lang == "de":
        if count == 1:
            return "und ein weiterer Schritt, siehe Bildschirm."
        return f"und {count} weitere Schritte, siehe Bildschirm."
    if count == 1:
        return "and one more step, see the screen."
    return f"and {count} more steps, see the screen."


# A unit is (text, kind) with kind "s" (sentence), "step" (numbered step) or "item" (list item).
Unit = tuple[str, str]


def _blocks(reply: str) -> list[tuple[str, str]]:
    """Lines to (kind, text) blocks in reading order, kind is prose, step or bullet.
    Consecutive prose lines are joined."""
    blocks: list[tuple[str, str]] = []
    for raw in reply.splitlines():
        if ANSWER_LINE.match(raw) or TABLE_ROW.match(raw) or RULE_LINE.match(raw):
            continue
        numbered = NUMBERED.match(raw.replace("**", "").replace("__", ""))
        if numbered:
            step = _remove_ids(STEP_LABEL.sub("", _strip_markdown(numbered.group(1))))
            if step:
                blocks.append(("step", _end_sentence(step)))
            continue
        bullet = bool(BULLET.match(raw))
        line = _strip_markdown(BULLET.sub("", raw))
        if not line:
            continue
        if bullet:
            blocks.append(("bullet", line))
        elif blocks and blocks[-1][0] == "prose":
            blocks[-1] = ("prose", f"{blocks[-1][1]} {line}")
        else:
            blocks.append(("prose", line))
    return blocks


def _units(reply: str, lang: str) -> list[Unit]:
    blocks = _blocks(reply)
    # A lone bullet is just prose; two or more in a row are list items.
    resolved: list[tuple[str, str]] = []
    for index, (kind, text) in enumerate(blocks):
        if kind == "bullet":
            near = (index > 0 and blocks[index - 1][0] == "bullet") or (
                index + 1 < len(blocks) and blocks[index + 1][0] == "bullet"
            )
            kind = "item" if near else "prose"
        if kind == "prose" and resolved and resolved[-1][0] == "prose":
            resolved[-1] = ("prose", f"{resolved[-1][1]} {text}")
        else:
            resolved.append((kind, text))
    only_prose = all(kind == "prose" for kind, _ in resolved)
    units: list[Unit] = []
    run: list[str] = []

    def flush_run() -> None:
        units.extend((item, "item") for item in _number_items(run, lang))
        run.clear()

    for kind, text in resolved:
        if kind == "item":
            item = _remove_ids(text)
            if item:
                run.append(_end_sentence(item))
            continue
        flush_run()
        if kind == "step":
            units.append((text, "step"))
            continue
        text = _remove_ids(text)
        if not text:
            continue
        sentences = _card_core(text) if only_prose and CARD_MARKER.search(text) else _sentences(text)
        for sentence in sentences:
            pieces = _split_run_on(sentence)
            if len(pieces) < 2:
                units.append((sentence, "s"))
                continue
            if pieces[0].endswith(":") and not RUN_ON_BOUNDARY.search(pieces[0]):
                units.append((pieces[0], "s"))
                pieces = pieces[1:]
            units.extend((item, "item") for item in _number_items([_end_sentence(p) for p in pieces], lang))
    flush_run()
    return _number_steps(units, lang)


def _number_steps(units: list[Unit], lang: str) -> list[Unit]:
    """Prefix route steps with "Step one, ..." when there are at least two of them."""
    if sum(kind == "step" for _, kind in units) < 2:
        return units
    word = STEP_WORD.get(lang, STEP_WORD[DEFAULT_LANG])
    out: list[Unit] = []
    count = 0
    for text, kind in units:
        if kind == "step":
            count += 1
            head = text[0].lower() + text[1:] if text[1:2].islower() else text
            text = f"{word} {_int_words(count, lang if lang in UNITS else DEFAULT_LANG)}, {head}"
        out.append((text, kind))
    return out


def _gaps(units: list[Unit]) -> list[float]:
    """Pause in seconds between unit i and i+1, 0 for none. One gap per boundary, so never doubled,
    and none before the first or after the last unit."""
    gaps = [0.0] * max(len(units) - 1, 0)
    for i in range(len(gaps)):
        here, after = units[i][1], units[i + 1][1]
        if i == 0:
            gaps[i] = PAUSE_HEADLINE
        if here != "s" or after != "s":
            gaps[i] = max(gaps[i], PAUSE_ITEM)
        if i + 1 == len(units) - 1 and units[i + 1][0].endswith("?"):
            gaps[i] = PAUSE_QUESTION
    return gaps


def _break_tag(seconds: float) -> str:
    return f'<break time="{seconds:.1f}s" />'


def _fit(units: list[Unit], limit: int) -> list[Unit]:
    """Keep whole units while they fit; if even the first does not, cut it at a word."""
    kept: list[Unit] = []
    length = 0
    for unit in units:
        add = len(unit[0]) + (1 if kept else 0)
        if length + add > limit:
            break
        kept.append(unit)
        length += add
    if not kept and units:
        kept = [(_cap(units[0][0], limit), units[0][1])]
    return kept


def _render(units: list[Unit], gaps: list[float]) -> str:
    out = units[0][0]
    for gap, (text, _) in zip(gaps, units[1:], strict=True):
        out += (f" {_break_tag(gap)} " if gap else " ") + text
    return out


def spoken_version(reply: str, max_chars: int = 400, lang: str = DEFAULT_LANG) -> str:
    """Turn an agent reply into a short text that is worth reading aloud, with pause tags.

    max_chars counts spoken characters only, the pause tags do not count. Tags in the reply are
    removed first, so every tag in the result was generated here.
    """
    reply = TAG_LIKE.sub(" ", reply).replace("<", " ").replace(">", " ")
    units = [(_pronounce(text, lang), kind) for text, kind in _units(reply, lang)]
    units = [unit for unit in units if unit[0].strip()]
    if not units:
        return ""
    steps = [unit for unit in units if unit[1] == "step"]
    tail = ""
    if len(steps) > MAX_STEPS:
        shown = {id(step) for step in steps[:MAX_STEPS]}
        units = [unit for unit in units if unit[1] != "step" or id(unit) in shown]
        tail = _more_steps(len(steps) - MAX_STEPS, lang)
        fitted = _fit(units, max_chars - len(tail) - 1)
        # Only announce the remaining steps if the last shown step survived the cap.
        last = steps[MAX_STEPS - 1]
        fitted = [(f"{u[0]} {tail}", u[1]) if u is last else u for u in fitted]
    else:
        fitted = _fit(units, max_chars)
    return _render(fitted, _gaps(fitted))


# ---------- ElevenLabs text-to-speech ----------


def _urllib_http(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, bytes]:
    """POST with a per-socket timeout plus an overall deadline (the body is read in chunks)."""
    deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            chunks = []
            while chunk := response.read(16384):
                chunks.append(chunk)
                if time.monotonic() > deadline:
                    raise TimeoutError("overall deadline")
            return response.status, b"".join(chunks)
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, b""


def _error_for_status(status: int) -> str:
    if status == 401:
        return "ElevenLabs rejected the API key (401)."
    if status in (402, 429):
        return f"ElevenLabs quota or rate limit reached ({status})."
    if status >= 500:
        return f"ElevenLabs is having trouble ({status})."
    return f"ElevenLabs returned an error ({status})."


DEFAULT_SPEED = 0.85
MIN_SPEED, MAX_SPEED = 0.7, 1.2
STABILITY = 0.5
SIMILARITY_BOOST = 0.75


def speech_speed() -> float:
    """Speaking speed from ELEVENLABS_SPEED, clamped to 0.7..1.2. Invalid values fall back to the default."""
    try:
        speed = float(os.environ.get("ELEVENLABS_SPEED", ""))
    except ValueError:
        return DEFAULT_SPEED
    if not math.isfinite(speed):
        return DEFAULT_SPEED
    return min(max(speed, MIN_SPEED), MAX_SPEED)


def synthesize(
    text: str,
    voice_id: str,
    model_id: str = "eleven_flash_v2_5",
    output_format: str = "mp3_44100_128",
    http: HttpFunction | None = None,
) -> bytes:
    """Return MP3 bytes for the text. Raises SpeechError; messages never contain the key."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SpeechError("ELEVENLABS_API_KEY is not set.")
    if not voice_id:
        raise SpeechError("No voice id given (set ELEVENLABS_VOICE_ID).")
    if not text.strip():
        raise SpeechError("Nothing to say.")
    url = API_URL.format(voice_id=voice_id, output_format=output_format)
    headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    voice_settings = {"speed": speech_speed(), "stability": STABILITY, "similarity_boost": SIMILARITY_BOOST}
    body = json.dumps({"text": text, "model_id": model_id, "voice_settings": voice_settings}).encode("utf-8")
    try:
        status, payload = (http or _urllib_http)(url, headers, body, TIMEOUT_SECONDS)
    except TimeoutError:
        raise SpeechError("ElevenLabs did not answer in time.") from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise SpeechError("ElevenLabs did not answer in time.") from None
        raise SpeechError("Could not reach ElevenLabs.") from None
    except Exception:  # noqa: BLE001 - ValueError, InvalidURL, BadStatusLine...: their text may hold the key
        raise SpeechError("Could not reach ElevenLabs.") from None
    if status != 200:
        raise SpeechError(_error_for_status(status))
    if not payload:
        raise SpeechError("ElevenLabs returned no audio.")
    return payload
