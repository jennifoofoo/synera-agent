"""Contracts between the Level 4 steps: extraction (vision) -> convert -> validate -> save.

Everything is plain data so each step can be built and tested alone. Pixel coordinates have the origin at the top
left with y down (as in the image); `convert` turns them into metres with y up (as in building.json)."""

from dataclasses import dataclass, field

ROOM_TYPES = {"room", "corridor", "stair", "lift", "hall", "outdoor"}
DOOR_KINDS = {"door", "opening", "entrance"}
OUTSIDE = "outside"


@dataclass
class ExtractedRoom:
    id: str  # the extractor's own running id, unique per floor
    polygon_px: list[list[float]]  # corners in order, not closed
    ref: str | None = None  # room number printed in the plan
    name: str | None = None
    type: str = "room"  # one of ROOM_TYPES
    room_type: str = "generic_room"  # office, kitchen, toilet, ... (see README section 3)


@dataclass
class ExtractedDoor:
    rooms: tuple[str, str]  # two extracted room ids, or (room id, "outside") for an entrance
    position_px: list[float]
    kind: str = "door"  # one of DOOR_KINDS
    width_px: float | None = None


@dataclass
class Extraction:
    """What the vision step returns for ONE floor image."""

    width_px: int
    height_px: int
    rooms: list[ExtractedRoom]
    doors: list[ExtractedDoor]
    scale_bar_px: float | None = None  # printed bar length in px, if any
    scale_bar_m: float | None = None


@dataclass
class Scale:
    """Metres per pixel, with where it came from, so the agent can say it."""

    metres_per_px: float
    source: str  # "known_length" | "scale_bar"
    note: str = ""


@dataclass
class Finding:
    level: str  # "error" blocks saving, "warning" is shown
    code: str  # stable id, e.g. "room_unreachable", "door_not_on_wall"
    message: str  # one plain sentence for the person
    items: list[str] = field(default_factory=list)  # room ids or refs concerned


@dataclass
class Findings:
    items: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.items if finding.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        """One line for the person, e.g. '24 rooms ok, 2 problems: 15 rooms without a way out.'"""
        if not self.items:
            return "No problems found."
        return " ".join(finding.message for finding in self.items)


# Tool schema for the vision call (Claude tool use, so the answer is structured and never half a JSON string).
EXTRACTION_TOOL = {
    "name": "report_floor_plan",
    "description": "Report every room and every door of the floor plan image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scale_bar_px": {
                "type": ["number", "null"],
                "description": "length of a printed scale bar in px, else null",
            },
            "scale_bar_m": {"type": ["number", "null"], "description": "its length in metres, else null"},
            "rooms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "ref": {"type": ["string", "null"]},
                        "name": {"type": ["string", "null"]},
                        "type": {"type": "string", "enum": sorted(ROOM_TYPES)},
                        "room_type": {"type": "string"},
                        "polygon_px": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                            "minItems": 3,
                        },
                    },
                    "required": ["id", "type", "polygon_px"],
                },
            },
            "doors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rooms": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
                        "kind": {"type": "string", "enum": sorted(DOOR_KINDS)},
                        "position_px": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                        "width_px": {"type": ["number", "null"]},
                    },
                    "required": ["rooms", "position_px"],
                },
            },
        },
        "required": ["rooms", "doors"],
    },
}
