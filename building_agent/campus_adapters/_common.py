"""Shared parsing helpers for the campus adapters. Everything here is tolerant: bad input becomes None or a finding."""

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from building_agent.campus import Campus, CampusBuilding, Link, resolve_building_dir
from building_agent.level4.schema import Finding

MAX_BYTES = 20_000_000
KIND_SYNONYMS = {
    "walkway": "walkway",
    "path": "walkway",
    "weg": "walkway",
    "bridge": "bridge",
    "bruecke": "bridge",
    "tunnel": "tunnel",
}
TRUE_WORDS = {"true", "yes", "y", "ja", "j", "1", "x", "wahr", "stufenfrei"}
FALSE_WORDS = {"false", "no", "n", "nein", "0", "falsch"}


def read_text(path: Path) -> str | None:
    """Text of a file (UTF-8 with or without BOM, UTF-16 or Windows-1252 as Excel writes it), None if binary."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in data:
        return None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def read_json(path: Path) -> Any:
    """Parsed JSON of a .json file, or None."""
    if path.suffix.lower() != ".json":
        return None
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return None


def parse_number(value: Any) -> float | None:
    """A finite float from a number or text such as '85,5', '1.234,5', '85 m'. None if unreadable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    text = re.sub(r"[\s  ']", "", str(value)).lower()
    text = re.sub(r"(meters|metres|meter|m)$", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    else:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    return default


def norm_key(text: Any) -> str:
    """'Length (m)' -> 'length_m', 'Von-Gebaeude' -> 'von_gebaeude'."""
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def parse_kind(value: Any) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if not text:
        return "walkway"
    return KIND_SYNONYMS.get(text, text)


def parse_origin(value: Any) -> tuple[float, float] | None:
    if isinstance(value, list | tuple) and len(value) == 2:
        x, y = parse_number(value[0]), parse_number(value[1])
        if x is not None and y is not None:
            return (x, y)
    return None


def text_of(value: Any) -> str:
    return "" if value is None else str(value).strip()


def search_roots(path: Path, root: Path | None) -> list[Path]:
    roots = [Path(root)] if root else []
    return roots + [path.parent, Path("data")]


def build_link(raw: dict, index: int, findings: list[Finding]) -> Link:
    """The one place where a raw link description becomes a `Link`, so every adapter yields the same structure."""
    link_id = text_of(raw.get("id")) or f"L{index}"
    length = parse_number(raw.get("length_m"))
    if length is None and text_of(raw.get("length_m")):
        findings.append(
            Finding("warning", "length_unreadable", f"The length of link {link_id} could not be read.", [link_id])
        )
    delta = parse_number(raw.get("level_delta"))
    return Link(
        id=link_id,
        kind=parse_kind(raw.get("kind")),
        name=text_of(raw.get("name")),
        from_building=text_of(raw.get("from_building")),
        from_entrance=text_of(raw.get("from_entrance")),
        to_building=text_of(raw.get("to_building")),
        to_entrance=text_of(raw.get("to_entrance")),
        length_m=length,
        length_estimated=parse_bool(raw.get("length_estimated"), False) and length is not None,
        width_m=parse_number(raw.get("width_m")),
        step_free=parse_bool(raw.get("step_free"), True),
        closed=parse_bool(raw.get("closed"), False),
        level_delta=int(delta) if delta is not None and abs(delta) < 1000 else 0,
    )


def add_building(campus: Campus, building_id: str, roots: list[Path], path: Any = None, **extra: Any) -> bool:
    """Add a building once; its folder is `path` if given, else looked up by id under `roots`. False if not found."""
    if campus.building(building_id) is not None:
        return True
    folder: Path | None
    if text_of(path):
        folder = Path(text_of(path))
        if not folder.exists():
            folder = next((Path(root) / folder for root in roots if (Path(root) / folder).exists()), folder)
    else:
        folder = resolve_building_dir(building_id, roots)
    if folder is None:
        return False
    campus.buildings.append(CampusBuilding(building_id, folder, **extra))
    return True


def note(campus: Campus, code: str, message: str, items: list[str] | None = None) -> None:
    campus.load_findings.append(Finding("warning", code, message, items or []))


def read_rows(path: Path) -> list[list[str]] | None:
    """Rows of a delimited text file (comma, semicolon, tab or pipe, as Excel exports), blank rows dropped."""
    if path.suffix.lower() == ".json":
        return None
    text = read_text(path)
    if text is None:
        return None
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lower().startswith("sep=")):
        lines.pop(0)
    if not lines:
        return None
    delimiter = max(";,\t|", key=lambda char: lines[0].count(char))
    try:
        rows = [[cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)]
    except csv.Error:
        return None
    return [row for row in rows if any(row)]


def find_header(rows: list[list[str]], synonyms: dict[str, tuple[str, ...]], required: tuple[str, ...]):
    """(header row index, {canonical column: cell index}) for the first row that has all required columns."""
    lookup = {norm_key(name): canonical for canonical, names in synonyms.items() for name in (canonical, *names)}
    for row_index, row in enumerate(rows[:5]):
        columns: dict[str, int] = {}
        for cell_index, cell in enumerate(row):
            canonical = lookup.get(norm_key(cell))
            if canonical and canonical not in columns:
                columns[canonical] = cell_index
        if all(name in columns for name in required):
            return row_index, columns
    return None


def cell(row: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    return row[index].strip() if index is not None and index < len(row) else ""
