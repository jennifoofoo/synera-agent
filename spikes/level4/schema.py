"""Extraction schema (what Claude fills from ONE plain plan image) and the prompt.

All coordinates are pixels of the image, origin top-left, y down.
Stairs and lifts are rooms with type "stair" or "lift" (grey, unlabelled shapes are common),
so doors can refer to them like to any other room."""

EXTRACTION_SCHEMA = {
    "scale": {"bar_px": "length of a printed scale bar in px, or null", "bar_m": "its length in metres, or null"},
    "rooms": [
        {
            "id": "r1 (your own running id, unique)",
            "ref": "room number printed in the room, or null",
            "name": "printed name if any, else null",
            "type": "room | corridor | stair | lift | hall | outdoor",
            "room_type": "bedroom, kitchen, bathroom, office, ... best guess from colour and label",
            "polygon_px": "[[x, y], ...] outline corners in order, not closed",
        }
    ],
    "doors": [
        {
            "rooms": "[id_a, id_b] the two rooms it joins, or [id_a, 'outside'] for an entrance (red triangle)",
            "kind": "door | opening | entrance",
            "position_px": "[x, y] centre of the marker",
            "width_px": "width of the door in px (guess from the wall gap)",
        }
    ],
}

PROMPT = """You get ONE floor plan image of a building floor ({width} x {height} px, origin top-left, y down).
Extract it as JSON for a building model. Conventions of this drawing style:
- Each room is a filled polygon; its number is printed inside it (the ref). Colours hint at the type.
- Brown dots on walls are doors, grey dots are openings without a door leaf, red triangles are
  entrances from outside. Grey shapes without a number next to entrances are stairs or lifts.
- There is usually no scale bar. Say null if you see none.
Rules: list EVERY room incl. corridors and stairs; polygon corners in pixel coordinates as exact as you
can (all real corners, also notches); every door joins exactly two rooms (or a room and 'outside').
Answer with ONLY one JSON object of this shape, no prose, no code fence:
{schema}
"""

# Variant v2: first enumerate every printed number and every marker, then draw the polygons.
PROMPT_V2_EXTRA = """
Work in two passes. Pass 1 (a key "inventory" inside the SAME single JSON object, next to scale, rooms and doors): list every printed room number you can read,
count the brown dots, grey dots and red triangles, and list the grey unlabelled shapes. Include very small
rooms (narrow corridors, small bathrooms) and every stair shape. Pass 2: the rooms and doors, so that the
numbers of rooms and doors match your inventory exactly (one door entry per marker).
"""
