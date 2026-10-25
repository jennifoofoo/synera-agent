"""The narrator VO tool for the video (docs/submission/video/make_vo.py): no network, only its file and math."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("make_vo", ROOT / "docs/submission/video/make_vo.py")
make_vo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(make_vo)


def test_every_line_fits_its_storyboard_slot():
    lines = make_vo.load_lines()
    assert [line["id"] for line in lines] == [f"S{n:02d}" for n in range(1, len(lines) + 1)]
    for line in lines:
        assert make_vo.slot_seconds(line["slot"]) == line["target_s"], line["id"]


def test_lines_are_the_storyboard_voiceover_word_for_word():
    storyboard = (ROOT / "docs/submission/VIDEO_STORYBOARD.md").read_text()
    for line in make_vo.load_lines():
        assert f'VO: "{line["text"]}"' in storyboard, line["id"]


def test_duration_from_constant_bitrate_and_overrun_flag():
    assert make_vo.mp3_seconds(16_000) == 1.0
    lines = make_vo.report([("S01", 3.1, 3.0), ("S02", 4.0, 3.0)])
    assert "OVER" not in lines[1]
    assert "OVER by 1.0 s" in lines[2]
    assert "7.1s" in lines[-1]
