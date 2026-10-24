"""Furniture glyphs of the plan svg: feature extraction, the room type model, thresholds, the build hook. Offline."""

from building_agent.level4 import furniture as fm
from building_agent.level4.schema import ExtractedRoom, Extraction, Scale

PT = 72 / 100  # svg points per png pixel


def _patch(x: float, y: float, w: float, d: float, fill: str, opacity: str = "0.75") -> str:
    """A rectangle patch the way matplotlib writes it, given in png pixels."""
    corners = [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]
    path = "\nL ".join(f"{cx * PT} {cy * PT}" for cx, cy in corners)
    return f'<g id="patch_9">\n <path d="M {path}\nz\n" clip-path="url(#p)" style="fill: {fill}; opacity: {opacity}"/>\n</g>\n'


BROWN, GREEN, BLUE = "#7f6a4f", "#2e7d32", "#4f81bd"
SVG = (
    _patch(10, 10, 14, 7, BROWN)  # desk 1.4 x 0.7 m at 10 px per metre
    + _patch(30, 10, 5, 5, BROWN)  # chair 0.5 x 0.5
    + _patch(40, 10, 4, 4, GREEN)  # coffee machine 0.4 x 0.4
    + _patch(50, 10, 7, 4, BLUE)
    + _patch(60, 10, 3, 3, "#123456")  # unknown colour: ignored
    + _patch(70, 10, 3, 3, BROWN, opacity="1")  # not a glyph (opacity)
)
PX_PER_M = 10.0


def test_read_glyphs_colour_size_and_order():
    glyphs = fm.read_glyphs(SVG)
    assert [g.colour for g in glyphs] == ["brown", "brown", "green", "blue"]
    assert [fm.glyph_key(g, PX_PER_M) for g in glyphs] == [
        "brown:1.40x0.70",
        "brown:0.50x0.50",
        "green:0.40x0.40",
        "blue:0.70x0.40",
    ]
    assert fm.key_footprint("brown:1.40x0.70") == (1.4, 0.7)


def test_rotated_glyph_keeps_its_size():
    import math

    side_a, side_b = 14.0, 7.0
    angle = math.radians(30)
    ux, uy = math.cos(angle), math.sin(angle)
    corners = [
        (0, 0),
        (side_a * ux, side_a * uy),
        (side_a * ux - side_b * uy, side_a * uy + side_b * ux),
        (-side_b * uy, side_b * ux),
    ]
    path = "\nL ".join(f"{(100 + x) * PT} {(100 + y) * PT}" for x, y in corners)
    text = f'<g id="patch_3"><path d="M {path}\nz\n" style="fill: {BROWN}; opacity: 0.75"/></g>'
    (glyph,) = fm.read_glyphs(text)
    assert fm.glyph_key(glyph, PX_PER_M) == "brown:1.40x0.70"
    assert abs(glyph.angle - 30) < 0.5


def test_glyphs_go_to_the_smallest_room_and_ranks_count_per_key():
    big = [[0, 0], [100, 0], [100, 100], [0, 100]]
    small = [[0, 0], [30, 0], [30, 30], [0, 30]]
    glyphs = fm.read_glyphs(SVG)
    held = fm.glyphs_by_room([big, small], glyphs)
    assert len(held[1]) == 1  # the small room (0..30) holds the desk centre at 17, not the chair at 32
    assert len(held[0]) == 3
    twice = fm.read_glyphs(_patch(10, 10, 6, 6, GREEN) + _patch(30, 10, 6, 6, GREEN))
    assert [rank for _, rank in fm.glyph_ranks(twice, PX_PER_M)] == [0, 1]


def test_ref_shape_formats():
    assert fm.ref_shape("1.30") == "d.dd"
    assert fm.ref_shape("H-A2") == "L-Ld"
    assert fm.ref_shape(None) == "none"


def _room(glyph_text: str, ref="1.01", fill="beige") -> fm.RoomInput:
    glyphs = fm.read_glyphs(glyph_text)
    return fm.RoomInput([[0, 0], [100, 0], [100, 100], [0, 100]], ref, fill, glyphs)


def _model() -> fm.Model:
    """Offices have desks and chairs, kitchens have a fridge and a stove; 30 rooms each."""
    office = _room(_patch(10, 10, 14, 7, BROWN) + _patch(30, 10, 5, 5, BROWN))
    kitchen = _room(_patch(10, 10, 6.5, 6, GREEN) + _patch(30, 10, 6, 6, GREEN))
    model = fm.Model(fm.RoomTypeModel(), fm.AssetTypeTable())
    for label, room in (("office", office), ("kitchen", kitchen)):
        for _ in range(30):
            model.rooms.add(label, fm.room_tokens(room, PX_PER_M, 0, 10))
            for (key, rank), name in zip(fm.glyph_ranks(room.glyphs, PX_PER_M), _types(label), strict=True):
                model.assets.add(key, label, name, rank)
    return model


def _types(label: str) -> list[str]:
    return ["desk", "chair"] if label == "office" else ["fridge", "stove"]


def test_model_is_deterministic_and_sure_on_typical_rooms():
    model = _model()
    room = _room(_patch(10, 10, 14, 7, BROWN) + _patch(30, 10, 5, 5, BROWN))
    first = model.rooms.predict(fm.room_tokens(room, PX_PER_M, 0, 10))
    second = model.rooms.predict(fm.room_tokens(room, PX_PER_M, 0, 10))
    assert first == second
    assert first[0] == "office" and first[1] >= fm.ROOM_CONFIDENCE


def test_unknown_room_stays_generic_below_threshold():
    model = _model()
    odd = _room(_patch(10, 10, 30, 2, GREEN) + _patch(50, 10, 1, 1, BLUE))  # sizes the model never saw
    guesses, assets = fm.infer_floor([odd], PX_PER_M, 0, model)
    assert guesses[0].room_type == fm.GENERIC and not guesses[0].guessed
    assert assets == []  # unknown keys are never listed


def test_non_plain_rooms_are_not_typed_and_balcony_gives_context():
    model = _model()
    corridor = _room(_patch(10, 10, 14, 7, BROWN), fill="grey")
    guesses, _ = fm.infer_floor([corridor], PX_PER_M, 0, model)
    assert not guesses[0].guessed
    assert fm.asset_context("green") == "balcony" and fm.asset_context("beige") is None


def test_asset_table_prefers_rank_and_needs_support():
    table = fm.AssetTypeTable()
    for _ in range(5):
        table.add("green:0.60x0.60", "kitchen", "stove", 0)
        table.add("green:0.60x0.60", "kitchen", "dishwasher", 1)
    assert table.predict("green:0.60x0.60", "kitchen", 0) == ("stove", 1.0)
    assert table.predict("green:0.60x0.60", "kitchen", 1) == ("dishwasher", 1.0)
    assert table.predict("green:0.60x0.60", None, 0)[1] == 0.5  # without the room type only half sure
    assert table.predict("brown:9.00x9.00", "kitchen", 0) is None
    two = fm.AssetTypeTable.from_json(table.to_json())
    assert two.predict("green:0.60x0.60", "kitchen", 1) == ("dishwasher", 1.0)


def test_model_json_roundtrip(tmp_path):
    model = _model()
    model.meta = {"room_precision": 0.99}
    path = tmp_path / "m.json"
    model.save(path)
    loaded = fm.Model.load(path)
    room = _room(_patch(10, 10, 14, 7, BROWN))
    tokens = fm.room_tokens(room, PX_PER_M, 0, 10)
    assert loaded.rooms.predict(tokens)[0] == model.rooms.predict(tokens)[0]
    assert loaded.meta == {"room_precision": 0.99}
    assert fm.Model.load(tmp_path / "missing.json") is None


def _floor_extraction(glyph_svg: str) -> Extraction:
    room = ExtractedRoom("r0", [[0, 0], [100, 0], [100, 100], [0, 100]], ref="1.01", fill="beige")
    return Extraction(100, 100, [room], [])


def test_hook_types_the_room_names_it_and_lists_assets(tmp_path):
    svg = tmp_path / "floor_1.svg"
    svg.write_text(
        '<svg width="72pt" height="72pt">' + _patch(10, 10, 14, 7, BROWN) + _patch(30, 10, 5, 5, BROWN) + "</svg>"
    )
    png = tmp_path / "floor_1.png"
    png.write_bytes(b"")
    scale = Scale(0.1, "known_length")
    extraction, note = fm.plan_furniture(_floor_extraction(""), png, tmp_path, scale, 1, model=_model())
    room = extraction.rooms[0]
    assert room.room_type == "office" and room.name == "Office 1.01"
    assert [a.asset_type for a in extraction.plan_assets] == ["desk", "chair"]
    assert "1 of 1 plain rooms" in note

    building = {
        "building": {"id": "b"},
        "floors": [{"id": "b-F1", "level": 1}],
        "spaces": [
            {
                "id": "s1",
                "floor_id": "b-F1",
                "name": "Office 1.01",
                "ref": "1.01",
                "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
            }
        ],
        "assets": [],
    }

    class Item:
        level = 1
        scale = Scale(0.1, "known_length")

    Item.extraction = extraction
    assert fm.attach_plan_assets(building, [Item]) == 2
    first = building["assets"][0]
    assert first["type"] == "desk" and first["source"] == "plan" and first["space_id"] == "s1"
    assert first["name"] == "Desk 1.01" and first["footprint"]["width_m"] == 1.4


def test_hook_without_glyphs_or_model_changes_nothing(tmp_path):
    svg = tmp_path / "floor_1.svg"
    svg.write_text('<svg width="72pt" height="72pt"></svg>')
    png = tmp_path / "floor_1.png"
    png.write_bytes(b"")
    original = _floor_extraction("")
    same, note = fm.plan_furniture(original, png, tmp_path, Scale(0.1, "known_length"), 1, model=_model())
    assert same is original and note == ""


def test_shipped_model_loads_and_knows_the_kit_types():
    model = fm.Model.load()
    assert model is not None and model.meta["room_precision"] >= 0.9
    assert model.assets.predict("brown:1.40x0.70", "office", 0) == ("desk", 1.0)
    assert model.assets.predict("brown:0.50x0.50", "balcony", 0)[0] == "outdoor_chair"
