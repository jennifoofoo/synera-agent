"""One Claude vision call: floor plan PNG -> extraction JSON. Usage:
uv run --env-file .env python -m spikes.level4.extract <building_id> <floor_index> [tag] [v2]
Stops at the first API error (no retry loops)."""

import base64
import json
import struct
import sys
import time
from pathlib import Path

import anthropic

from spikes.level4.schema import EXTRACTION_SCHEMA, PROMPT, PROMPT_V2_EXTRA

MODEL = "claude-sonnet-5-5"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "outputs"


def find_building(building_id: str) -> Path:
    return next((ROOT / "data").glob(f"*/{building_id}"))


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    return struct.unpack(">II", header[16:24])


def parse_json(text: str) -> dict:
    """Last JSON object in the text that has a "rooms" list (v2 prompts emit an inventory object first)."""
    decoder, position, found = json.JSONDecoder(), 0, None
    while (start := text.find("{", position)) != -1:
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            position = start + 1
            continue
        if isinstance(value, dict) and value.get("rooms") and isinstance(value["rooms"][0], dict):
            found = value
        position = end
    if found is None:
        raise ValueError("no JSON object with rooms")
    return found


def main() -> None:
    building_id, floor = sys.argv[1], int(sys.argv[2])
    tag = sys.argv[3] if len(sys.argv) > 3 else "run1"
    image_path = find_building(building_id) / f"floor_{floor}_plain.png"
    width, height = png_size(image_path)
    prompt = PROMPT.format(width=width, height=height, schema=json.dumps(EXTRACTION_SCHEMA, indent=1))
    if len(sys.argv) > 4 and sys.argv[4] == "v2":
        prompt += PROMPT_V2_EXTRA
    client = anthropic.Anthropic(max_retries=1)
    data = base64.standard_b64encode(image_path.read_bytes()).decode()
    started = time.time()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except anthropic.APIError as error:
        print(f"API error, stopping: {type(error).__name__} {getattr(error, 'status_code', '')}")
        sys.exit(1)
    seconds = time.time() - started
    text = "".join(block.text for block in response.content if block.type == "text")
    record = {
        "building_id": building_id,
        "floor_index": floor,
        "model": MODEL,
        "image": str(image_path.relative_to(ROOT)),
        "image_size_px": [width, height],
        "seconds": round(seconds, 1),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "stop_reason": response.stop_reason,
        "raw_text": text,
    }
    try:
        record["extraction"] = parse_json(text)
    except ValueError as error:
        record["parse_error"] = str(error)
    OUT.mkdir(exist_ok=True)
    (OUT / f"{building_id}_f{floor}_{tag}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
    print(
        building_id,
        record["seconds"],
        "s",
        record["input_tokens"],
        "in",
        record["output_tokens"],
        "out",
        record["stop_reason"],
    )


if __name__ == "__main__":
    main()
