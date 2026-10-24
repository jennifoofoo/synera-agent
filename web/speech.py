"""Voice output for the 2D page: shorten an agent reply for speaking, and turn text into MP3 via ElevenLabs.

Stdlib only. The API key is read from the environment at request time and never logged or put in messages.
language_code is not sent: eleven_flash_v2_5 detects German and English from the text itself.
"""

import json
import os
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Callable

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={output_format}"
TIMEOUT_SECONDS = 5
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
RAW_ID = re.compile(r"\b(?=[\w-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}\b")
BRACKETED = re.compile(r"\s*\[[^\]]*\]")
EMPTY_PARENS = re.compile(r"\s*\(\s*[,;]?\s*\)")
CARD_MARKER = re.compile(r"i understood|ich habe verstanden", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
SQUARE_METRES = re.compile(r"(?<=\d)\s*(?:m2|m²)(?!\w)")
METRES = re.compile(r"(?<=\d)\s*m(?![\w²])")
WC = re.compile(r"\bWC\b")


def _strip_markdown(line: str) -> str:
    line = HEADING.sub("", line)
    line = line.replace("**", "").replace("__", "").replace("`", "")
    return line.strip()


def _remove_ids(text: str) -> str:
    text = BRACKETED.sub("", text)
    text = RAW_ID.sub("", text)
    text = EMPTY_PARENS.sub("", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _pronounce(text: str) -> str:
    text = SQUARE_METRES.sub(" Quadratmeter", text)
    text = METRES.sub(" Meter", text)
    return WC.sub("W C", text)


def _sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(text.strip()) if s]


def _card_core(text: str) -> str:
    """Confirmation card: keep the first sentence from the marker on plus the closing question."""
    sentences = _sentences(text)
    start = next((i for i, s in enumerate(sentences) if CARD_MARKER.search(s)), 0)
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


def _more_steps(count: int) -> str:
    if count == 1:
        return "und ein weiterer Schritt, siehe Bildschirm."
    return f"und {count} weitere Schritte, siehe Bildschirm."


def spoken_version(reply: str, max_chars: int = 400) -> str:
    """Turn an agent reply into a short text that is worth reading aloud."""
    prose: list[str] = []
    steps: list[str] = []
    for raw in reply.splitlines():
        if ANSWER_LINE.match(raw):
            continue
        numbered = NUMBERED.match(_strip_markdown(raw) if raw.lstrip().startswith("#") else raw)
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
    tail = _more_steps(len(steps) - MAX_STEPS) if len(steps) > MAX_STEPS else ""
    steps_text = " ".join(steps[:MAX_STEPS])
    body = " ".join(part for part in (text, steps_text) if part)
    body = _pronounce(body)
    room = max_chars - len(tail) - 1 if tail else max_chars
    result = _cap(body, room) if body else ""
    return " ".join(part for part in (result, tail) if part)


# ---------- ElevenLabs text-to-speech ----------


def _urllib_http(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
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
        raise SpeechError("ElevenLabs did not answer within 5 seconds.") from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise SpeechError("ElevenLabs did not answer within 5 seconds.") from None
        raise SpeechError("Could not reach ElevenLabs.") from None
    except OSError:
        raise SpeechError("Could not reach ElevenLabs.") from None
    if status != 200:
        raise SpeechError(_error_for_status(status))
    if not payload:
        raise SpeechError("ElevenLabs returned no audio.")
    return payload
