"""Level 4 step 1a: one floor plan image -> `Extraction` via a Claude vision call with tool use.

Validates the upload before any API call, sends the image, parses the tool input defensively (bad model content
becomes warnings, never an exception) and returns tokens, seconds and cost next to the result."""

import base64
import io
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from PIL import Image

from building_agent.level4.schema import (
    DOOR_KINDS,
    EXTRACTION_TOOL,
    OUTSIDE,
    ROOM_TYPES,
    ExtractedDoor,
    ExtractedRoom,
    Extraction,
)

DEFAULT_MODEL = "claude-sonnet-5-5"
# Claude Sonnet 5.5 list price in USD per 1M tokens (claude-api skill, cached 2026-10-06). Not checked against an invoice.
PRICE_INPUT_PER_MTOK = 2.00
PRICE_OUTPUT_PER_MTOK = 10.00

DEFAULT_ALLOWED_ROOT = Path("agent_output/uploads")
MAX_FILE_BYTES = 10 * 1024 * 1024
MIN_SIDE_PX, MAX_SIDE_PX = 200, 8000
DOWNSCALE_TO_PX = 3000  # longer side above this is shrunk before sending
MAX_SENT_BYTES = 4_500_000  # the API rejects images over 5 MB
MAX_OUTPUT_TOKENS = 16000

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

PROMPT = """You get ONE floor plan image of a building floor ({width} x {height} px, origin top-left, y down).
Report it with the tool {tool}. Call it exactly once and write no other text.
Conventions of this drawing style:
- Each room is a filled polygon; its number is printed inside it (the ref). Colours hint at the type.
- Brown dots on walls are doors, grey dots are openings without a door leaf, red triangles are entrances from
  outside. Grey shapes without a number next to entrances are stairs or lifts (type stair or lift).
- There is usually no scale bar. Use null for the scale fields if you see none.
Work in two passes before you call the tool (think it through, do not write it out):
1. Inventory: every printed room number you can read, the count of brown dots, grey dots and red triangles, and
   the grey unlabelled shapes. Include very small rooms (narrow corridors, small bathrooms) and every stair shape.
2. Draw: the rooms and doors, so that the numbers of rooms and doors match your inventory (one door entry per
   marker). List EVERY room including corridors and stairs. Give polygon corners in pixel coordinates as exact as
   you can (all real corners, also notches). Every door joins exactly two different rooms, or a room and 'outside'
   for an entrance. Room ids are your own running ids (r1, r2, ...), unique."""


class ExtractError(Exception):
    """Plain-English failure the caller can show to the person."""


@dataclass
class ExtractResult:
    extraction: Extraction
    input_tokens: int
    output_tokens: int
    seconds: float
    cost_usd: float
    warnings: list[str] = field(default_factory=list)


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * PRICE_INPUT_PER_MTOK / 1e6 + output_tokens * PRICE_OUTPUT_PER_MTOK / 1e6


# ---------- input validation ----------


@dataclass
class _Prepared:
    data: bytes
    media_type: str
    original_size: tuple[int, int]
    sent_size: tuple[int, int]
    scale: float  # sent px = original px * scale


def _resolve_inside(image_path: str | Path, allowed_root: str | Path) -> Path:
    candidate = Path(image_path)
    if ".." in candidate.parts:
        raise ExtractError("The image path must not contain '..'.")
    try:
        root = Path(allowed_root).resolve()
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        raise ExtractError("The image path could not be resolved.") from None
    if not resolved.is_relative_to(root):
        raise ExtractError("The image is not inside the upload folder.")
    if not resolved.is_file():
        raise ExtractError("The image was not found as a regular file in the upload folder.")
    return resolved


def _encode(image: Image.Image, media_type: str) -> bytes:
    buffer = io.BytesIO()
    if media_type == "image/jpeg":
        image.convert("RGB").save(buffer, format="JPEG", quality=90)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def prepare_image(image_path: str | Path, allowed_root: str | Path = DEFAULT_ALLOWED_ROOT) -> _Prepared:
    path = _resolve_inside(image_path, allowed_root)
    suffix = path.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        raise ExtractError("Only PNG and JPG images are supported.")
    try:
        size = path.stat().st_size
    except OSError:
        raise ExtractError("The image could not be read.") from None
    if size > MAX_FILE_BYTES:
        raise ExtractError("The image is larger than 10 MB.")
    if size == 0:
        raise ExtractError("The image file is empty.")
    try:
        raw = path.read_bytes()
    except OSError:
        raise ExtractError("The image could not be read.") from None
    is_png, is_jpeg = raw.startswith(_PNG_MAGIC), raw.startswith(_JPEG_MAGIC)
    if not (is_png or is_jpeg) or (suffix == ".png") != is_png:
        raise ExtractError("The file content is not a PNG or JPG image that matches its file name.")
    media_type = "image/png" if is_png else "image/jpeg"
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            width, height = probe.size  # header only, checked before decoding pixels
            if not (MIN_SIDE_PX <= min(width, height) and max(width, height) <= MAX_SIDE_PX):
                raise ExtractError(
                    f"The image is {width} x {height} px; each side must be between {MIN_SIDE_PX} and {MAX_SIDE_PX} px."
                )
            probe.load()
            image = probe.copy()
    except ExtractError:
        raise
    except Exception:
        raise ExtractError("The image could not be read; it may be damaged.") from None

    longer = max(width, height)
    scale = 1.0
    data = raw
    if longer > DOWNSCALE_TO_PX:
        scale = DOWNSCALE_TO_PX / longer
    resized = image
    while True:
        if scale < 1.0:
            new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            resized = image.resize(new_size, Image.Resampling.LANCZOS)
            data = _encode(resized, media_type)
        if len(data) <= MAX_SENT_BYTES:
            break
        scale *= 0.8
        if min(width, height) * scale < MIN_SIDE_PX:
            raise ExtractError("The image is too detailed to send; please export a smaller version.")
    return _Prepared(data, media_type, (width, height), resized.size, scale)


# ---------- tool input parsing ----------


class _Invalid(Exception):
    pass


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _point(value, factor: float) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = _number(value[0]), _number(value[1])
    if x is None or y is None:
        return None
    return [x * factor, y * factor]


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_tool_input(tool_input, width_px: int, height_px: int, factor: float = 1.0) -> tuple[Extraction, list[str]]:
    """Validate the tool input. `factor` multiplies all pixel values (undo a downscale). Raises _Invalid if no room."""
    warnings: list[str] = []
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            raise _Invalid("tool input is not valid JSON") from None
    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("rooms"), list):
        raise _Invalid("tool input has no list of rooms")

    rooms: dict[str, ExtractedRoom] = {}
    for index, item in enumerate(tool_input["rooms"]):
        label = f"room #{index + 1}"
        if not isinstance(item, dict):
            warnings.append(f"Dropped {label}: not an object.")
            continue
        room_id = _text(item.get("id"))
        if room_id is None:
            warnings.append(f"Dropped {label}: no id.")
            continue
        if room_id == OUTSIDE:
            warnings.append(f"Dropped room '{room_id}': reserved id.")
            continue
        if room_id in rooms:
            warnings.append(f"Dropped duplicate room id '{room_id}' (kept the first).")
            continue
        raw_polygon = item.get("polygon_px")
        points = [p for p in (_point(v, factor) for v in raw_polygon) if p] if isinstance(raw_polygon, list) else []
        if len(points) < 3:
            warnings.append(f"Dropped room '{room_id}': fewer than 3 valid corners.")
            continue
        room_kind = _text(item.get("type")) or "room"
        if room_kind not in ROOM_TYPES:
            warnings.append(f"Room '{room_id}' has unknown type '{room_kind}'; using 'room'.")
            room_kind = "room"
        rooms[room_id] = ExtractedRoom(
            id=room_id,
            polygon_px=points,
            ref=_text(item.get("ref")),
            name=_text(item.get("name")),
            type=room_kind,
            room_type=_text(item.get("room_type")) or "generic_room",
        )
    if not rooms:
        raise _Invalid("no usable rooms")

    doors: list[ExtractedDoor] = []
    raw_doors = tool_input.get("doors")
    if raw_doors is not None and not isinstance(raw_doors, list):
        warnings.append("Ignored doors: not a list.")
        raw_doors = []
    for index, item in enumerate(raw_doors or []):
        label = f"door #{index + 1}"
        pair = item.get("rooms") if isinstance(item, dict) else None
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            warnings.append(f"Dropped {label}: needs exactly two rooms.")
            continue
        first, second = _text(pair[0]), _text(pair[1])
        if first is None or second is None:
            warnings.append(f"Dropped {label}: empty room id.")
            continue
        if first == second:
            warnings.append(f"Dropped {label}: joins room '{first}' to itself.")
            continue
        unknown = [r for r in (first, second) if r != OUTSIDE and r not in rooms]
        if unknown:
            warnings.append(f"Dropped {label}: unknown room '{unknown[0]}'.")
            continue
        position = _point(item.get("position_px"), factor)
        if position is None:
            warnings.append(f"Dropped {label}: no valid position.")
            continue
        kind = _text(item.get("kind")) or "door"
        if kind not in DOOR_KINDS:
            warnings.append(f"{label} has unknown kind '{kind}'; using 'door'.")
            kind = "door"
        width = _number(item.get("width_px"))
        doors.append(
            ExtractedDoor(
                rooms=(first, second),
                position_px=position,
                kind=kind,
                width_px=width * factor if width is not None and width > 0 else None,
            )
        )

    bar_px, bar_m = _number(tool_input.get("scale_bar_px")), _number(tool_input.get("scale_bar_m"))
    if bar_px is None or bar_m is None or bar_px <= 0 or bar_m <= 0:
        bar_px = bar_m = None
    else:
        bar_px *= factor
    extraction = Extraction(
        width_px=width_px,
        height_px=height_px,
        rooms=list(rooms.values()),
        doors=doors,
        scale_bar_px=bar_px,
        scale_bar_m=bar_m,
    )
    return extraction, warnings


# ---------- API call ----------

_FATAL_MESSAGE = (
    "The Claude API refused the request (key, permission, credit or usage limit). Check the API key and your "
    "usage limits, then try again."
)


def _is_transient(error: Exception) -> bool:
    if isinstance(error, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    status = getattr(error, "status_code", None)
    return isinstance(status, int) and (status >= 500 or status in (408, 409))


def _tool_input_from(response) -> dict | str:
    if getattr(response, "stop_reason", None) == "refusal":
        raise ExtractError("The model declined to read this image.")
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == EXTRACTION_TOOL["name"]:
            return block.input
    raise _Invalid("the model did not call the tool")


def extract_floor(
    image_path: str | Path,
    client=None,
    model: str = DEFAULT_MODEL,
    max_retries: int = 1,
    allowed_root: str | Path = DEFAULT_ALLOWED_ROOT,
) -> ExtractResult:
    prepared = prepare_image(image_path, allowed_root)  # raises ExtractError before any API call
    if client is None:
        try:
            client = anthropic.Anthropic(max_retries=0, timeout=180.0)
        except Exception:
            raise ExtractError("The Claude API client could not be created; is the API key set?") from None
    width, height = prepared.original_size
    prompt = PROMPT.format(width=prepared.sent_size[0], height=prepared.sent_size[1], tool=EXTRACTION_TOOL["name"])
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": prepared.media_type,
                "data": base64.standard_b64encode(prepared.data).decode(),
            },
        },
        {"type": "text", "text": prompt},
    ]
    warnings: list[str] = []
    if prepared.scale < 1.0:
        warnings.append(
            f"Image was downscaled from {width} x {height} px to {prepared.sent_size[0]} x {prepared.sent_size[1]} px."
        )
    input_tokens = output_tokens = 0
    started = time.monotonic()
    last_problem = "no answer"
    for attempt in range(max_retries + 1):
        try:
            # Forced tool_choice is rejected by Sonnet 5.5, so the prompt names the tool and "auto" is used.
            response = client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                output_config={"effort": "medium"},
                tools=[EXTRACTION_TOOL],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": content}],
            )
        except ExtractError:
            raise
        except Exception as error:
            if isinstance(error, anthropic.APIError) and _is_transient(error) and attempt < max_retries:
                last_problem = f"API error ({type(error).__name__})"
                warnings.append(f"Retried after a temporary API error ({type(error).__name__}).")
                continue
            if isinstance(error, anthropic.APIError) and _is_transient(error):
                raise ExtractError("The Claude API had a temporary problem; please try again in a moment.") from None
            raise ExtractError(_FATAL_MESSAGE) from None
        usage = getattr(response, "usage", None)
        input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        try:
            raw = _tool_input_from(response)
            extraction, parse_warnings = parse_tool_input(raw, width, height, 1.0 / prepared.scale)
        except _Invalid as problem:
            last_problem = str(problem)
            if attempt < max_retries:
                warnings.append(f"Retried because the first answer was unusable ({last_problem}).")
            continue
        return ExtractResult(
            extraction=extraction,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            seconds=time.monotonic() - started,
            cost_usd=compute_cost(input_tokens, output_tokens),
            warnings=warnings + parse_warnings,
        )
    raise ExtractError(
        f"The model did not return a usable floor plan ({last_problem}). Try again or use a clearer image."
    )
