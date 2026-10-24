from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from PIL import Image

from building_agent.level4.extract import (
    EXTRACTION_TOOL,
    ExtractError,
    compute_cost,
    extract_floor,
)

ROOMS = [
    {
        "id": "r1",
        "ref": "0.01",
        "type": "room",
        "room_type": "office",
        "polygon_px": [[10, 10], [110, 10], [110, 90], [10, 90]],
    },
    {"id": "r2", "ref": "0.02", "type": "corridor", "polygon_px": [[110, 10], [210, 10], [210, 90], [110, 90]]},
]
DOORS = [
    {"rooms": ["r1", "r2"], "position_px": [110, 50], "kind": "door", "width_px": 8},
    {"rooms": ["r2", "outside"], "position_px": [210, 50], "kind": "entrance"},
]


def good_input(**changes):
    data = {
        "scale_bar_px": None,
        "scale_bar_m": None,
        "rooms": [dict(r) for r in ROOMS],
        "doors": [dict(d) for d in DOORS],
    }
    data.update(changes)
    return data


def tool_response(tool_input, input_tokens=1000, output_tokens=2000, stop_reason="tool_use"):
    block = SimpleNamespace(type="tool_use", name=EXTRACTION_TOOL["name"], input=tool_input)
    return SimpleNamespace(
        content=[block],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class FakeClient:
    """Mimics client.messages.create; each item of `script` is a response or an exception to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def api_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()
    return folder


def make_png(root, name="plan.png", size=(300, 200)):
    path = root / name
    Image.new("RGB", size, "white").save(path)
    return path


def run(root, client, **kwargs):
    return extract_floor(make_png(root), client=client, allowed_root=root, **kwargs)


def test_valid_answer(root):
    client = FakeClient(tool_response(good_input()))
    result = run(root, client)
    extraction = result.extraction
    assert (extraction.width_px, extraction.height_px) == (300, 200)
    assert [r.id for r in extraction.rooms] == ["r1", "r2"]
    assert extraction.rooms[0].ref == "0.01"
    assert extraction.rooms[1].room_type == "generic_room"
    assert [d.rooms for d in extraction.doors] == [("r1", "r2"), ("r2", "outside")]
    assert extraction.doors[0].width_px == 8
    assert result.warnings == []
    assert (result.input_tokens, result.output_tokens) == (1000, 2000)
    call = client.calls[0]
    assert call["tools"] == [EXTRACTION_TOOL]
    assert call["messages"][0]["content"][0]["type"] == "image"


def test_cost_computation(root):
    assert compute_cost(1_000_000, 1_000_000) == pytest.approx(12.0)
    result = run(root, FakeClient(tool_response(good_input(), 1000, 2000)))
    assert result.cost_usd == pytest.approx(0.022)


def test_missing_fields_become_warnings(root):
    rooms = [{"id": "r1", "polygon_px": [[0, 0], [10, 0], [10, 10]]}, {"polygon_px": [[0, 0], [1, 1], [2, 0]]}]
    result = run(root, FakeClient(tool_response({"rooms": rooms})))
    assert len(result.extraction.rooms) == 1
    assert result.extraction.rooms[0].type == "room"
    assert result.extraction.doors == []
    assert any("no id" in w for w in result.warnings)


def test_wrong_types_are_coerced_or_dropped(root):
    rooms = [
        {"id": 1, "type": "room", "polygon_px": [["0", "0"], ["10", 0], [10, "10"], ["x", 3]]},
        {"id": "bad", "type": "room", "polygon_px": [[0, 0], [1, 1]]},
        "not a room",
        {"id": "r3", "type": "room", "polygon_px": "nonsense"},
    ]
    doors = [
        {"rooms": ["1", "outside"], "position_px": ["5", "6"], "width_px": "x"},
        {"rooms": "1,2", "position_px": [1, 1]},
    ]
    result = run(
        root, FakeClient(tool_response({"rooms": rooms, "doors": doors, "scale_bar_px": "abc", "scale_bar_m": 5}))
    )
    extraction = result.extraction
    assert [r.id for r in extraction.rooms] == ["1"]
    assert extraction.rooms[0].polygon_px == [[0, 0], [10, 0], [10, 10]]
    assert extraction.doors[0].position_px == [5, 6] and extraction.doors[0].width_px is None
    assert len(extraction.doors) == 1
    assert extraction.scale_bar_px is None and extraction.scale_bar_m is None
    assert len(result.warnings) >= 4


def test_duplicate_ids_keep_first(root):
    rooms = [ROOMS[0], {**ROOMS[1], "id": "r1"}, ROOMS[1]]
    result = run(root, FakeClient(tool_response(good_input(rooms=rooms))))
    assert [r.ref for r in result.extraction.rooms] == ["0.01", "0.02"] or len(result.extraction.rooms) == 2
    assert result.extraction.rooms[0].ref == "0.01"
    assert any("duplicate" in w for w in result.warnings)


def test_unknown_and_identical_door_rooms_dropped(root):
    doors = [
        {"rooms": ["r1", "r9"], "position_px": [1, 1]},
        {"rooms": ["r1", "r1"], "position_px": [1, 1]},
        {"rooms": ["r1", "r2"], "position_px": [1, 1], "kind": "portal"},
    ]
    result = run(root, FakeClient(tool_response(good_input(doors=doors))))
    assert len(result.extraction.doors) == 1
    assert result.extraction.doors[0].kind == "door"
    assert any("unknown room" in w for w in result.warnings)
    assert any("itself" in w for w in result.warnings)


def test_unknown_room_type_mapped_to_room(root):
    rooms = [{**ROOMS[0], "type": "spaceship"}]
    result = run(root, FakeClient(tool_response({"rooms": rooms, "doors": []})))
    assert result.extraction.rooms[0].type == "room"
    assert any("spaceship" in w for w in result.warnings)


def test_invalid_twice_raises(root):
    bad = tool_response({"rooms": [{"id": "r1", "polygon_px": [[0, 0]]}], "doors": []})
    client = FakeClient(bad, bad)
    with pytest.raises(ExtractError, match="usable"):
        run(root, client)
    assert len(client.calls) == 2


def test_no_tool_call_then_valid_retries(root):
    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")], stop_reason="end_turn", usage=None)
    client = FakeClient(text_only, tool_response(good_input()))
    result = run(root, client)
    assert len(client.calls) == 2 and len(result.extraction.rooms) == 2
    assert any("Retried" in w for w in result.warnings)


def test_transient_error_then_success(root):
    client = FakeClient(api_error(anthropic.InternalServerError, 500), tool_response(good_input()))
    result = run(root, client)
    assert len(client.calls) == 2 and len(result.extraction.rooms) == 2


def test_transient_error_twice_raises(root):
    client = FakeClient(api_error(anthropic.InternalServerError, 500), api_error(anthropic.InternalServerError, 529))
    with pytest.raises(ExtractError, match="temporary"):
        run(root, client)


@pytest.mark.parametrize(
    "error",
    [
        api_error(anthropic.RateLimitError, 429),
        api_error(anthropic.AuthenticationError, 401),
        api_error(anthropic.BadRequestError, 400),
    ],
)
def test_usage_limit_and_auth_not_retried(root, error):
    client = FakeClient(error, tool_response(good_input()))
    with pytest.raises(ExtractError, match="usage limits"):
        run(root, client)
    assert len(client.calls) == 1


def test_oversized_file_rejected_before_api(root):
    path = root / "big.png"
    make_png(root, "big.png")
    with path.open("ab") as handle:
        handle.write(b"\0" * (10 * 1024 * 1024))
    client = FakeClient()
    with pytest.raises(ExtractError, match="10 MB"):
        extract_floor(path, client=client, allowed_root=root)
    assert client.calls == []


def test_wrong_magic_bytes_and_suffix(root):
    fake = root / "fake.png"
    fake.write_bytes(b"GIF89a" + b"\0" * 100)
    client = FakeClient()
    with pytest.raises(ExtractError, match="not a PNG or JPG"):
        extract_floor(fake, client=client, allowed_root=root)
    gif = root / "plan.gif"
    Image.new("RGB", (300, 300)).save(gif)
    with pytest.raises(ExtractError, match="Only PNG and JPG"):
        extract_floor(gif, client=client, allowed_root=root)
    jpeg_as_png = root / "x.png"
    Image.new("RGB", (300, 300)).save(jpeg_as_png, format="JPEG")
    with pytest.raises(ExtractError, match="match"):
        extract_floor(jpeg_as_png, client=client, allowed_root=root)
    assert client.calls == []


def test_jpeg_accepted(root):
    path = root / "plan.jpg"
    Image.new("RGB", (300, 300), "white").save(path)
    client = FakeClient(tool_response(good_input()))
    extract_floor(path, client=client, allowed_root=root)
    assert client.calls[0]["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


def test_damaged_and_tiny_and_huge_images(root):
    damaged = root / "d.png"
    damaged.write_bytes(b"\x89PNG\r\n\x1a\n" + b"junk" * 20)
    tiny = make_png(root, "tiny.png", (100, 100))
    huge = make_png(root, "huge.png", (8001, 250))
    client = FakeClient()
    for path, text in [(damaged, "could not be read"), (tiny, "between 200 and 8000"), (huge, "between 200 and 8000")]:
        with pytest.raises(ExtractError, match=text):
            extract_floor(path, client=client, allowed_root=root)
    assert client.calls == []


def test_path_outside_root_and_dotdot(root, tmp_path):
    outside = make_png(tmp_path, "outside.png")
    client = FakeClient()
    with pytest.raises(ExtractError, match="not inside"):
        extract_floor(outside, client=client, allowed_root=root)
    with pytest.raises(ExtractError, match=r"\.\."):
        extract_floor(root / ".." / "outside.png", client=client, allowed_root=root)
    with pytest.raises(ExtractError, match="regular file"):
        extract_floor(root / "missing.png", client=client, allowed_root=root)
    with pytest.raises(ExtractError, match="regular file"):
        extract_floor(root, client=client, allowed_root=root)
    assert client.calls == []


def test_symlink_escape_rejected(root, tmp_path):
    outside = make_png(tmp_path, "secret.png")
    link = root / "link.png"
    link.symlink_to(outside)
    client = FakeClient()
    with pytest.raises(ExtractError, match="not inside"):
        extract_floor(link, client=client, allowed_root=root)
    assert client.calls == []


def test_large_image_downscaled_and_coordinates_scaled_back(root):
    path = make_png(root, "wide.png", (6000, 1000))
    sent = {}

    class Capturing(FakeClient):
        def create(self, **kwargs):
            sent["source"] = kwargs["messages"][0]["content"][0]["source"]
            return super().create(**kwargs)

    answer = good_input(
        rooms=[{"id": "r1", "type": "room", "polygon_px": [[0, 0], [1500, 0], [1500, 250]]}],
        doors=[{"rooms": ["r1", "outside"], "position_px": [750, 125], "width_px": 10}],
        scale_bar_px=100,
        scale_bar_m=5,
    )
    result = extract_floor(path, client=Capturing(tool_response(answer)), allowed_root=root)
    import base64
    import io

    with Image.open(io.BytesIO(base64.b64decode(sent["source"]["data"]))) as image:
        assert image.size == (3000, 500)
    extraction = result.extraction
    assert (extraction.width_px, extraction.height_px) == (6000, 1000)
    assert extraction.rooms[0].polygon_px == [[0, 0], [3000, 0], [3000, 500]]
    assert extraction.doors[0].position_px == [1500, 250]
    assert extraction.doors[0].width_px == 20
    assert extraction.scale_bar_px == 200 and extraction.scale_bar_m == 5
    assert any("downscaled" in w for w in result.warnings)
