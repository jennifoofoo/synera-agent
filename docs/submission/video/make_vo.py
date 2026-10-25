"""Render the narrator voiceover of the 2-minute video with ElevenLabs, one MP3 per line of vo_lines.json.

    uv run --env-file .env python docs/submission/video/make_vo.py --list-voices
    uv run --env-file .env python docs/submission/video/make_vo.py --samples VOICE_ID [VOICE_ID ...]
    uv run --env-file .env python docs/submission/video/make_vo.py --voice VOICE_ID [--only S03 S08] [--speed 1.0]

Default: every line with NARRATOR_VOICE_ID (env) or --voice, model eleven_multilingual_v2, into
docs/submission/video/vo/ (git-ignored), then a table of each line's length against its storyboard slot.
The narrator must not be Wanda's app voice (ELEVENLABS_VOICE_ID): the jury has to tell narrator and product apart.
Stdlib only, like web/speech.py. ELEVENLABS_API_KEY is read from the environment and never printed.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINES_FILE = HERE / "vo_lines.json"
OUT_DIR = HERE / "vo"
API = "https://api.elevenlabs.io/v1"
MODEL = "eleven_multilingual_v2"
# Constant bit rate, so the length follows from the file size (no audio library needed).
OUTPUT_FORMAT = "mp3_44100_128"
BITRATE = 128_000
WANDA_VOICE_ID = "jqcCZkN6Knx8BJ5TBdYR"
SETTINGS = {"stability": 0.55, "similarity_boost": 0.75, "style": 0.15, "use_speaker_boost": True}
TIMEOUT = 60


def load_lines(path: Path = LINES_FILE) -> list[dict]:
    lines = json.loads(path.read_text())["lines"]
    ids = [line["id"] for line in lines]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"Duplicate ids in {path.name}.")
    return lines


def mp3_seconds(size_bytes: int, bitrate: int = BITRATE) -> float:
    return size_bytes * 8 / bitrate


def slot_seconds(slot: str) -> float:
    """'1:32-1:42' -> 10.0"""

    def seconds(text: str) -> int:
        minutes, secs = text.split(":")
        return int(minutes) * 60 + int(secs)

    start, end = slot.split("-")
    return float(seconds(end) - seconds(start))


def report(rows: list[tuple[str, float, float]]) -> list[str]:
    """rows: (id, real seconds, target seconds) -> printable lines, overruns flagged."""
    out = [f"{'id':<5}{'real':>7}{'target':>8}  "]
    for line_id, real, target in rows:
        flag = "  OVER by %.1f s" % (real - target) if real > target + 0.2 else ""
        out.append(f"{line_id:<5}{real:>6.1f}s{target:>7.1f}s{flag}")
    total_real = sum(real for _, real, _ in rows)
    total_target = sum(target for _, _, target in rows)
    out.append(f"{'sum':<5}{total_real:>6.1f}s{total_target:>7.1f}s  (narrator only; the round 0:48-1:28 has none)")
    return out


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set. Run with: uv run --env-file .env python ...")
    return key


def request(path: str, body: dict | None = None) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"xi-api-key": api_key(), "Content-Type": "application/json"}
    req = urllib.request.Request(API + path, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        raise SystemExit(f"ElevenLabs {error.code} on {path.split('?')[0]}: {detail}") from None


def tts(voice_id: str, text: str, speed: float) -> bytes:
    body = {"text": text, "model_id": MODEL, "voice_settings": {**SETTINGS, "speed": speed}}
    return request(f"/text-to-speech/{voice_id}?output_format={OUTPUT_FORMAT}", body)


def check_not_wanda(voice_id: str) -> None:
    if voice_id in {WANDA_VOICE_ID, os.environ.get("ELEVENLABS_VOICE_ID", "").strip()}:
        raise SystemExit("That is Wanda's app voice. Pick a different narrator voice (--list-voices).")


def list_voices() -> None:
    voices = json.loads(request("/voices"))["voices"]
    for voice in sorted(voices, key=lambda v: (v.get("labels", {}).get("gender", ""), v["name"])):
        labels = voice.get("labels") or {}
        tags = ", ".join(f"{k}={v}" for k, v in sorted(labels.items()) if k in {"gender", "accent", "age", "use_case"})
        mark = "  <- Wanda (app)" if voice["voice_id"] == WANDA_VOICE_ID else ""
        print(f"{voice['voice_id']}  {voice['name']:<24} {tags}{mark}")


def samples(voice_ids: list[str], speed: float) -> None:
    hook = load_lines()[0]["text"]
    folder = OUT_DIR / "samples"
    folder.mkdir(parents=True, exist_ok=True)
    for voice_id in voice_ids:
        check_not_wanda(voice_id)
        path = folder / f"{voice_id}.mp3"
        path.write_bytes(tts(voice_id, hook, speed))
        print(f"{path.relative_to(HERE.parent.parent.parent)}  {mp3_seconds(path.stat().st_size):.1f}s")


def render(voice_id: str, only: list[str], speed: float) -> None:
    check_not_wanda(voice_id)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for line in load_lines():
        path = OUT_DIR / f"{line['id']}.mp3"
        if not only or line["id"] in only:
            path.write_bytes(tts(voice_id, line["text"], speed))
        if path.exists():
            rows.append((line["id"], mp3_seconds(path.stat().st_size), float(line["target_s"])))
    print(f"Rendered into {OUT_DIR}")
    print("\n".join(report(rows)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list-voices", action="store_true", help="list the voices this account can use")
    parser.add_argument("--samples", nargs="+", metavar="VOICE_ID", help="render the hook line with each voice")
    parser.add_argument("--voice", default=os.environ.get("NARRATOR_VOICE_ID", ""), help="narrator voice id")
    parser.add_argument("--only", nargs="+", default=[], metavar="ID", help="re-render only these lines (S03 ...)")
    parser.add_argument("--speed", type=float, default=1.0, help="0.7 to 1.2, 1.0 = natural")
    args = parser.parse_args()
    if args.list_voices:
        list_voices()
    elif args.samples:
        samples(args.samples, args.speed)
    elif args.voice:
        render(args.voice, args.only, args.speed)
    else:
        parser.error("set NARRATOR_VOICE_ID in .env or pass --voice VOICE_ID (see --list-voices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
