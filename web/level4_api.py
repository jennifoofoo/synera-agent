"""Level 4 on the 2D page: upload floor plans, build a draft, preview it, fix it, save it after a card and a yes.

Thin layer over building_agent.level4.tools: every step calls the same tools the chat agent uses (build_from_plan,
fix_draft, preview_draft, save_building), so the confirmation rules and all geometry stay in one place.
Security: uploads are PNG/JPG only (magic bytes, Pillow), at most 10 MB, stored under a server-made name in the
upload folder. The browser only ever names an upload by its id; it never sends a path."""

import copy
import io
import json
import math
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from anthropic.lib.tools import ToolError
from PIL import Image

from building_agent.guide_tools import GuideState
from building_agent.level4 import tools as level4_tools
from building_agent.level4.extract import (
    DEFAULT_ALLOWED_ROOT,
    MAX_FILE_BYTES,
    MAX_SIDE_PX,
    MIN_SIDE_PX,
    ExtractResult,
)
from building_agent.level4.schema import OUTSIDE, ExtractedDoor, ExtractedRoom, Extraction
from building_agent.level4.tools import ALONG, BMHolder, make_level4_tools
from building_agent.level4.validate import describe, room_label
from starter_agent.building_map import BuildingMap
from web import api

BUILDINGS_ROOT = level4_tools.BUILDINGS_ROOT
USER_PREFIX = "user/"
OUTPUT_DIRECTORY = Path("agent_output") / "web"
MAX_UPLOADS = 12
MAX_FLOORS = 8
LEVEL_RANGE = (-5, 60)
MAX_KNOWN_LENGTH_M = 2000.0
NAME_MAX = 60
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
UPLOAD_ID = re.compile(r"^plan-[0-9a-f]{12}$")
SECONDS_PER_FLOOR = "10 to 20 s"
FIX_ACTIONS = ("add_door", "remove_door", "set_room_type", "set_scale")
# finding code -> what to mark red on the plan
ROOM_CODES = {
    "room_unreachable",
    "area_implausible",
    "polygon_tiny",
    "polygon_invalid",
    "connector_single_floor",
    "connector_missing_stop",
}
# The tools' messages are written for the chat agent; on the page the same step is a button.
PAGE_WORDS = {
    "Fix them, or call preview_draft and ask whether to save anyway.": "Fix them, or tick 'Save anyway' on the card.",
    "Call preview_draft, show it, and wait for the person's answer.": "Press 'Save building…' to see the card first.",
    "Call preview_draft again.": "Press 'Save building…' again.",
    "Call preview_draft.": "Press 'Save building…' again.",
    "Ask the person again, then call preview_draft anew.": "Press 'Save building…' again.",
    "Call build_from_plan with an image first.": "Read a floor plan first.",
}
PAIR_CODES = {"room_overlap", "door_not_on_wall", "door_width_implausible", "door_same_room", "door_unknown_room"}


class Level4Error(ValueError):
    """A request the page made that cannot be done; the message is shown as is."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Upload:
    upload_id: str
    path: Path
    media_type: str
    width: int
    height: int
    size: int


@dataclass
class Job:
    """One background build: a few floors, one vision call each."""

    floors: list[dict]
    state: str = "running"  # running | done | error
    index: int = 0
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    message: str = ""
    errors: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)


def sniff(data: bytes) -> str | None:
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg"
    return None


def _number(value: object, what: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise Level4Error(f"{what} must be a number.") from None
    if not math.isfinite(number):
        raise Level4Error(f"{what} must be a number.")
    return number


def _level(value: object) -> int:
    number = _number(value, "The floor (level)")
    if number != int(number) or not LEVEL_RANGE[0] <= number <= LEVEL_RANGE[1]:
        raise Level4Error(f"The floor (level) must be a whole number from {LEVEL_RANGE[0]} to {LEVEL_RANGE[1]}.")
    return int(number)


def _length(value: object) -> float:
    number = _number(value, "The known length")
    if not 0 < number <= MAX_KNOWN_LENGTH_M:
        raise Level4Error("The known length must be more than 0 and at most 2000 metres.")
    return number


def _text(value: object, limit: int = 80) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


class PlanStudio:
    """The single Level 4 draft of the page (single-user demo, like the rest of the server state)."""

    def __init__(
        self,
        uploads_root: Path = DEFAULT_ALLOWED_ROOT,
        buildings_root: Path = BUILDINGS_ROOT,
        output_directory: Path = OUTPUT_DIRECTORY,
    ) -> None:
        self.uploads_root = Path(uploads_root)
        self.buildings_root = Path(buildings_root)
        self.output_directory = Path(output_directory)
        self.uploads: dict[str, Upload] = {}
        self.lock = threading.RLock()  # draft and tools
        self.job_lock = threading.Lock()  # job fields, so polling never waits for a vision call
        self.job: Job | None = None
        self.saved_key: str | None = None
        self.building_level: int | None = None  # level being read right now (the offline fake uses it)
        self.state = GuideState()
        self.holder = BMHolder(bm=None)  # type: ignore[arg-type]
        # One set of tools for the page and the chat, so both see the same draft and the same card rules.
        self.chat_tools = make_level4_tools(
            self.holder, self.output_directory, self.state, self._on_saved, self.uploads_root, self.buildings_root
        )
        self.tools = {tool.name: tool for tool in self.chat_tools}

    # ---------- draft and tools ----------

    def new_draft(self, forget_uploads: bool = False) -> None:
        """Start over. The draft object is reset in place because the tools hold on to it."""
        with self.lock:
            self.draft.__init__()
            self.saved_key = None
            if forget_uploads:
                self.uploads.clear()

    @property
    def draft(self) -> level4_tools.Level4Draft:
        return self.state.level4

    def _on_saved(self, path: Path) -> None:
        self.saved_key = USER_PREFIX + path.parent.name

    def call(self, name: str, **kwargs) -> dict:
        try:
            return json.loads(self.tools[name](**kwargs))
        except ToolError as error:
            message = str(error)
            for agent_words, page_words in PAGE_WORDS.items():
                message = message.replace(agent_words, page_words)
            raise Level4Error(message) from None

    def begin_turn(self) -> None:
        """Every page action and every chat message is one turn, so a card is answered by the very next one."""
        with self.lock:
            self.state.begin_turn()

    # ---------- upload ----------

    def upload(self, data: bytes) -> dict:
        """Check and store one image. Returns its id and size; the file name is ours, never the browser's."""
        if not data:
            raise Level4Error("The file is empty.")
        if len(data) > MAX_FILE_BYTES:
            raise Level4Error("The image is larger than 10 MB.", 413)
        media_type = sniff(data)
        if media_type is None:
            raise Level4Error("Only PNG and JPG images are supported.", 415)
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                fmt = image.format
                image.verify()
        except Exception:  # noqa: BLE001 - Pillow raises many kinds; any of them means "not a usable image"
            raise Level4Error("The image could not be read; it may be damaged.", 415) from None
        if fmt not in ("PNG", "JPEG"):
            raise Level4Error("Only PNG and JPG images are supported.", 415)
        if not (MIN_SIDE_PX <= min(width, height) and max(width, height) <= MAX_SIDE_PX):
            raise Level4Error(
                f"The image is {width} x {height} px; each side must be between {MIN_SIDE_PX} and {MAX_SIDE_PX} px."
            )
        with self.lock:
            if len(self.uploads) >= MAX_UPLOADS:
                raise Level4Error("Too many images in this draft. Start a new building first.", 429)
            upload_id = f"plan-{uuid.uuid4().hex[:12]}"
            suffix = ".png" if media_type == "image/png" else ".jpg"
            self.uploads_root.mkdir(parents=True, exist_ok=True)
            path = self.uploads_root / f"{upload_id}{suffix}"
            with path.open("xb") as handle:  # never overwrite
                handle.write(data)
            self.uploads[upload_id] = Upload(upload_id, path, media_type, width, height, len(data))
        return {"upload_id": upload_id, "width": width, "height": height, "bytes": len(data), "type": media_type}

    def _upload(self, upload_id: object) -> Upload:
        text = str(upload_id or "")
        if not UPLOAD_ID.match(text) or text not in self.uploads:
            raise Level4Error("Unknown upload. Choose the image again.")
        return self.uploads[text]

    # ---------- build (background) ----------

    def start_build(self, body: dict, run_async: bool = True) -> dict:
        floors_in = body.get("floors")
        if not isinstance(floors_in, list) or not floors_in:
            raise Level4Error("Add at least one floor plan image.")
        if len(floors_in) > MAX_FLOORS:
            raise Level4Error(f"At most {MAX_FLOORS} floors at once.")
        floors = []
        for item in floors_in:
            if not isinstance(item, dict):
                raise Level4Error("Each floor needs an image, a level and a scale.")
            upload = self._upload(item.get("upload_id"))
            level = _level(item.get("level", 0))
            along = str(item.get("along") or "building_width")
            if along not in ALONG:
                raise Level4Error(f"'along' must be one of {', '.join(ALONG)}.")
            scale_bar = bool(item.get("scale_bar"))
            known = item.get("known_length_m")
            if known in (None, "") and not scale_bar:
                raise Level4Error(
                    f"Floor {level}: give one length you know in metres (for example the building width), "
                    "or tick 'scale bar printed'."
                )
            known_m = None if known in (None, "") else _length(known)
            floors.append({"upload": upload, "level": level, "known_length_m": known_m, "along": along})
        levels = [floor["level"] for floor in floors]
        if len(set(levels)) != len(levels):
            raise Level4Error("Two images have the same floor (level).")
        name = _text(body.get("name"), NAME_MAX)
        with self.job_lock:
            if self.job is not None and self.job.state == "running":
                raise Level4Error("Still reading the last plans. Wait a moment.", 409)
            job = self.job = Job(floors)
        if body.get("fresh", True) and self.draft.building is not None:
            self.new_draft()
        if name:
            with self.lock:
                self.draft.name = name
        if run_async:
            threading.Thread(target=self._run, args=(job,), daemon=True).start()
        else:
            self._run(job)
        return self.status()

    def _run(self, job: Job) -> None:
        for index, floor in enumerate(job.floors):
            with self.job_lock:
                job.index = index
                job.message = f"Reading floor {floor['level']} ({index + 1} of {len(job.floors)})"
            try:
                with self.lock:
                    self.building_level = floor["level"]
                    self.begin_turn()
                    result = self.call(
                        "build_from_plan",
                        image_path=floor["upload"].path.name,
                        level=floor["level"],
                        known_length_m=floor["known_length_m"],
                        along=floor["along"],
                    )
                with self.job_lock:
                    job.results.append({"level": floor["level"], **result})
            except Level4Error as error:
                message = str(error)
                if message == level4_tools.ASK_SCALE:
                    message = "No scale bar was found on this plan. Give one length you know in metres."
                with self.job_lock:
                    job.errors.append({"level": floor["level"], "error": message})
            except Exception as error:  # noqa: BLE001 - a crash must end the job, not leave it "running"
                with self.job_lock:
                    job.errors.append({"level": floor["level"], "error": f"Reading failed ({type(error).__name__})."})
            finally:
                self.building_level = None
        with self.job_lock:
            job.finished = time.monotonic()
            job.state = "error" if len(job.errors) == len(job.floors) else "done"
            job.message = "Done." if job.state == "done" else "Nothing could be built."

    def status(self) -> dict:
        with self.job_lock:
            job = self.job
            if job is None:
                return {
                    "state": "idle",
                    "has_draft": self.draft.building is not None,
                    "version": self.draft.version,
                    "saved": self.saved_key,
                }
            end = job.finished or time.monotonic()
            return {
                "state": job.state,
                "message": job.message,
                "floor_index": job.index,
                "floors_total": len(job.floors),
                "seconds": round(end - job.started, 1),
                "expected": f"{SECONDS_PER_FLOOR} per floor",
                "errors": list(job.errors),
                "results": list(job.results),
                "has_draft": self.draft.building is not None,
                "version": self.draft.version,
                "saved": self.saved_key,
            }

    def busy(self) -> bool:
        with self.job_lock:
            return self.job is not None and self.job.state == "running"

    # ---------- preview ----------

    def preview(self) -> dict:
        if self.busy():
            raise Level4Error("Still reading the plans.", 409)
        with self.lock:
            draft = self.draft
            if draft.building is None:
                return {"draft": None, "status": self.status()}
            building = copy.deepcopy(draft.building)
            findings = draft.findings
            scales = {level: source.scale.note for level, source in draft.floors.items()}
            version, cost, notes = draft.version, draft.cost_usd, list(draft.notes)
        view = draft_view(building)
        spaces, openings = suspicious(building, findings)
        view["key"] = "draft"
        return {
            "draft": view,
            "version": version,
            "suspect_spaces": sorted(spaces),
            "suspect_openings": sorted(openings),
            "findings": [
                {"level": f.level, "code": f.code, "message": f.message, "items": f.items} for f in findings.items
            ],
            "summary": summary_line(building, findings),
            "problems": describe(findings),
            "can_save": findings.ok,
            "scales": [{"level": level, "note": note} for level, note in sorted(scales.items())],
            "cost_usd": round(cost, 4),
            "notes": notes,
            "status": self.status(),
        }

    # ---------- fix, card, save ----------

    def fix(self, body: dict) -> dict:
        if self.busy():
            raise Level4Error("Still reading the plans.", 409)
        action = str(body.get("action", ""))
        if action not in FIX_ACTIONS:
            raise Level4Error(f"action must be one of {', '.join(FIX_ACTIONS)}.")
        args: dict = {"action": action}
        for name in ("ref", "other_ref"):
            text = _text(body.get(name))
            if text:
                args[name] = text
        if body.get("room_type") not in (None, ""):
            args["room_type"] = _text(body.get("room_type"), 41)
        if body.get("level") not in (None, ""):
            args["level"] = _level(body["level"])
        if action == "set_scale":
            args["known_length_m"] = _length(body.get("known_length_m"))
            along = str(body.get("along") or "building_width")
            if along not in ALONG:
                raise Level4Error(f"'along' must be one of {', '.join(ALONG)}.")
            args["along"] = along
        with self.lock:
            self.begin_turn()
            done = self.call("fix_draft", **args)
        return {"done": done.get("done", ""), **self.preview()}

    def card(self) -> dict:
        """The understanding card (same tool as the chat). Saving needs the very next action to be a yes."""
        if self.busy():
            raise Level4Error("Still reading the plans.", 409)
        with self.lock:
            self.begin_turn()
            card = self.call("preview_draft")
            return {"card": card, "version": self.draft.version}

    def save(self, body: dict) -> dict:
        if self.busy():
            raise Level4Error("Still reading the plans.", 409)
        answer = str(body.get("answer", "")).strip().lower()
        accept = bool(body.get("accept_problems"))
        confirmed = answer == "yes"
        reply = ("yes, save it anyway" if accept else "yes, save it") if confirmed else "no, not yet"
        with self.lock:
            if self.draft.building is None:
                raise Level4Error("There is no draft to save.")
            self.begin_turn()
            result = self.call("save_building", confirmed=confirmed, user_reply=reply, accept_problems=accept)
        if result.get("saved"):
            result["key"] = self.saved_key
        return result

    # ---------- chat ----------

    def chat_context(self) -> str | None:
        """A short note for the chat agent naming the uploaded images, before any draft exists."""
        with self.lock:
            if self.draft.building is not None or not self.uploads:
                return None
            names = ", ".join(upload.path.name for upload in self.uploads.values())
        return f"[Floor plan images uploaded on the page: {names}]"

    def chat_info(self) -> dict:
        return {"version": self.draft.version, "has_draft": self.draft.building is not None, "saved": self.saved_key}


# ---------- views ----------


def draft_view(building: dict) -> dict:
    """The same JSON shape the page draws for a building (api.building_view)."""
    bm = BuildingMap(building)
    session = api.Session("draft", Path("."), bm)
    view = api.building_view(session)
    view["source"] = "draft"
    return view


def summary_line(building: dict, findings) -> str:
    totals = level4_tools.counts(building)
    entrances = totals["entrances"]
    line = f"{totals['rooms']} rooms, {totals['doors']} doors, {entrances} entrance{'s' if entrances != 1 else ''}."
    return f"{line} {describe(findings)}"


def suspicious(building: dict, findings) -> tuple[set[str], set[str]]:
    """Space and opening ids to draw red, from the findings' room labels."""
    by_label: dict[str, list[str]] = {}
    for space in building["spaces"]:
        by_label.setdefault(str(room_label(space)), []).append(space["id"])
    labels = {space["id"]: str(room_label(space)) for space in building["spaces"]}
    spaces: set[str] = set()
    openings: set[str] = set()
    for finding in findings.items:
        for item in finding.items:
            if finding.code in ROOM_CODES:
                spaces.update(by_label.get(item, []))
            elif finding.code in PAIR_CODES:
                pair = item.split("/")
                matched = [
                    opening["id"]
                    for opening in building["openings"]
                    if sorted(OUTSIDE if end == OUTSIDE else labels.get(end, end) for end in opening["space_ids"])
                    == sorted(pair)
                ]
                if matched and finding.code != "room_overlap":
                    openings.update(matched)
                else:
                    for label in pair:
                        spaces.update(by_label.get(label, []))
    return spaces, openings


def saved_buildings(root: Path) -> list[dict]:
    """Buildings saved from plans, for the building picker (key 'user/<id>')."""

    found = []
    if not root.is_dir():
        return found
    for building_file in sorted(root.glob("*/building.json")):
        try:
            data = json.loads(building_file.read_text(encoding="utf-8"))
            name, floors = data["building"]["name"], len(data["floors"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        found.append(
            {
                "key": USER_PREFIX + building_file.parent.name,
                "name": name,
                "split": "user",
                "source": "plan_upload",
                "floors": floors,
            }
        )
    return found


# ---------- offline extraction for demos and tests ----------


def synthetic_extraction(building: dict, level: int, width_px: int = 1200, drop_doors_of: int = 1) -> Extraction:
    """An Extraction made from a real building floor (no API): what a perfect vision call would return, with a
    printed scale bar, minus every door of `drop_doors_of` single-door rooms so the preview has a red finding."""
    floor = next(item for item in building["floors"] if item["level"] == level)
    spaces = [space for space in building["spaces"] if space["floor_id"] == floor["id"]]
    openings = [opening for opening in building["openings"] if opening["floor_id"] == floor["id"]]
    xs = [x for space in building["spaces"] for x, _ in space["polygon"]]
    ys = [y for space in building["spaces"] for _, y in space["polygon"]]
    min_x, min_y = min(xs), min(ys)
    px_per_m = width_px / max(max(xs) - min_x, max(ys) - min_y)
    margin = 20
    height_px = math.ceil((max(ys) - min_y) * px_per_m) + 2 * margin

    def to_px(x: float, y: float) -> list[float]:
        return [(x - min_x) * px_per_m + margin, height_px - ((y - min_y) * px_per_m + margin)]

    ids = {space["id"]: f"r{index}" for index, space in enumerate(spaces)}
    door_count: dict[str, int] = {}
    for opening in openings:
        for end in opening["space_ids"]:
            door_count[end] = door_count.get(end, 0) + 1
    dropped = {space["id"] for space in spaces if space["type"] == "room" and door_count.get(space["id"]) == 1}
    dropped = set(sorted(dropped)[:drop_doors_of])
    rooms = [
        ExtractedRoom(
            id=ids[space["id"]],
            polygon_px=[to_px(x, y) for x, y in space["polygon"]],
            ref=space.get("ref"),
            name=space.get("name"),
            type=space["type"],
            room_type=space["room_type"],
        )
        for space in spaces
    ]
    doors = [
        ExtractedDoor(
            rooms=tuple(OUTSIDE if end == OUTSIDE else ids[end] for end in opening["space_ids"]),  # type: ignore[arg-type]
            position_px=to_px(*opening["position"]),
            kind=opening["kind"],
            width_px=(opening.get("width_m") or 0.9) * px_per_m,
        )
        for opening in openings
        if not dropped.intersection(opening["space_ids"])
    ]
    return Extraction(
        width_px=width_px + 2 * margin,
        height_px=height_px,
        rooms=rooms,
        doors=doors,
        scale_bar_px=100.0,
        scale_bar_m=100.0 / px_per_m,
    )


def use_fake_extraction(
    studio: PlanStudio, building_dir: Path, drop_doors_of: int = 1, delay_seconds: float = 1.5
) -> None:
    """Offline demo: every uploaded image is 'read' as the floor of `building_dir` with the requested level.
    Replaces the vision call for this process only; never used unless `python -m web --fake-plans` asks for it."""

    building = json.loads((Path(building_dir) / "building.json").read_text(encoding="utf-8"))
    levels = sorted(floor["level"] for floor in building["floors"])

    def fake_extract(path, client=None, allowed_root=None, **kwargs) -> ExtractResult:
        level = studio.building_level if studio.building_level in levels else levels[0]
        time.sleep(delay_seconds)  # so the progress display can be seen
        extraction = synthetic_extraction(building, level, drop_doors_of=drop_doors_of)
        return ExtractResult(extraction, 0, 0, delay_seconds, 0.0)

    level4_tools.extract_floor = fake_extract
