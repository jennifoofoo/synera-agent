"""Voice output for the 2D page: shorten an agent reply for speaking, and turn text into MP3 via ElevenLabs.

Stdlib only. The API key is read from the environment at request time and never logged or put in messages.
language_code is not sent: eleven_flash_v2_5 detects German and English from the text itself.
"""

import json
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
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
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


ROOM_WORDS = (
    r"labs?|offices?|rooms?|halls?|kitchens?|toilets?|staircases?|lifts?|räume?|raum|büros?|labore?|küche|"
    r"treppenhaus|aufzug"
)
ROOM_REF_LIST = re.compile(
    rf"\b(?:{ROOM_WORDS})\s+\d+\.\d+(?:\s*(?:,|and|und|or|oder)\s*\d+\.\d+)*(?!\d)", re.IGNORECASE
)
DOTTED_NUMBER = re.compile(r"\d+\.\d+(?!\d)(?!\s*(?:m\b|m2|m²|metres|meters|square|meter|quadratmeter))")
DIGIT_WORDS = {
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "point"),
    "de": ("null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "Punkt"),
}


def _spell_room_refs(text: str, lang: str) -> str:
    """Room refs like 0.12 are read digit by digit; measurements (63.4 m) keep normal number reading."""
    words = DIGIT_WORDS.get(lang, DIGIT_WORDS[DEFAULT_LANG])

    def spell(match: re.Match) -> str:
        return " ".join(words[10] if c == "." else words[int(c)] for c in match.group())

    return ROOM_REF_LIST.sub(lambda group: DOTTED_NUMBER.sub(spell, group.group()), text)


def _pronounce(text: str, lang: str = DEFAULT_LANG) -> str:
    text = _spell_room_refs(text, lang)
    square, metres, toilet = UNITS.get(lang, UNITS[DEFAULT_LANG])
    text = SQUARE_METRES.sub(square, text)
    text = METRES.sub(metres, text)
    return WC.sub(toilet, text)


def _sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(text.strip()) if s]


def _card_core(text: str) -> str:
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
    return " ".join(core)


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


def spoken_version(reply: str, max_chars: int = 400, lang: str = DEFAULT_LANG) -> str:
    """Turn an agent reply into a short text that is worth reading aloud."""
    prose: list[str] = []
    steps: list[str] = []
    for raw in reply.splitlines():
        if ANSWER_LINE.match(raw) or TABLE_ROW.match(raw) or RULE_LINE.match(raw):
            continue
        numbered = NUMBERED.match(raw.replace("**", "").replace("__", ""))
        if numbered:
            step = _remove_ids(_strip_markdown(numbered.group(1)))
            if step:
                steps.append(step if step[-1] in ".!?" else step + ".")
            continue
        line = _strip_markdown(BULLET.sub("", raw))
        if line:
            prose.append(line)
    text = _remove_ids(" ".join(prose))
    if CARD_MARKER.search(text) and not steps:
        text = _card_core(text)
    shown = steps[:MAX_STEPS]
    body = _pronounce(" ".join(part for part in (text, *shown) if part), lang)
    if not body:
        return ""
    if len(steps) <= MAX_STEPS:
        return _cap(body, max_chars)
    tail = _more_steps(len(steps) - MAX_STEPS, lang)
    result = _cap(body, max_chars - len(tail) - 1)
    # Only announce the remaining steps if the last shown step survived the cap.
    if _pronounce(shown[-1], lang) in result:
        return f"{result} {tail}"
    return result


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
    body = json.dumps({"text": text, "model_id": model_id}).encode("utf-8")
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
