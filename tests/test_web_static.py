"""The 2D page's static files fit together: every element the scripts look up exists in index.html."""

import re
from pathlib import Path

STATIC = Path("web/static")


def test_every_id_the_scripts_use_is_in_the_page():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    for script in ("app.js", "voice.js", "plan.js"):
        assert f'<script src="{script}"></script>' in html
        source = (STATIC / script).read_text(encoding="utf-8")
        used = set(re.findall(r'\$\("#([\w-]+)"\)', source))
        created = set(re.findall(r'\bid: "([\w-]+)"', source))  # SVG elements the script draws itself
        assert used, script
        assert used - ids - created == set(), f"{script} looks up ids missing from index.html"


def test_voice_script_loads_after_app_script():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.index('src="app.js"') < html.index('src="voice.js"')


def test_chat_reply_finds_are_focused_on_the_plan():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert re.search(r"window\.app\s*=\s*Object\.assign\(window\.app \|\| \{\}, \{[^}]*focusFound", source)
    assert re.search(r"function focusFound\(entries\)", source)
    send_chat = source[source.index("async function sendChat") : source.index("// ---------- pan / zoom / click")]
    assert "window.app.focusFound(result.located)" in send_chat
    assert "window.plan.openSaved(result.opened" in send_chat  # the agent saved a building: the page switches to it
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="found-list"' in html


def _function_source(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    return source[start : source.index("\n}\n", start) + 3]


def test_click_selection_is_wired_into_the_page():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    for element in ("selection-chip", "selection-text", "selection-clear"):
        assert f'id="{element}"' in html
    assert html.index('id="selection-chip"') < html.index('id="chat-form"')  # the chip sits above the chat input
    send_chat = source[source.index("async function sendChat") : source.index("// ---------- pan / zoom / click")]
    assert "selectionContext()" in send_chat and "{ message: text, context }" in send_chat
    assert "selection_ignored" in send_chat and "I couldn't use the selection" in send_chat
    assert send_chat.index("selection_ignored") < send_chat.index("clearSelection()")  # kept for retry when ignored
    assert "app.selection" in _function_source(source, "render")  # highlighted on the plan
    assert "hit" in _function_source(source, "onSpaceClick") and "setSelection" in _function_source(
        source, "onSpaceClick"
    )
    assert "page:selection" in (STATIC / "view3d.js").read_text(encoding="utf-8")  # highlighted in 3D
    assert "onSpaceClick: (event, id, hit) => onSpaceClick(event, id, hit)" in (STATIC / "view3d.js").read_text(
        encoding="utf-8"
    )


def test_selection_context_has_exactly_the_fields_that_apply():
    import json
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    script = (
        _function_source(source, "selectionContext")
        + """
const out = [
  selectionContext({ space_id: "s1", floor_id: "f1", label: "Office 1.04" }),
  selectionContext({ asset_id: "a1", space_id: "s1", floor_id: "f1", label: "CMM" }),
  selectionContext({ space_id: "s1", point: [1.5, -2], floor_id: "f1", label: "Point in Hall 1" }),
  selectionContext(null),
];
console.log(JSON.stringify(out));
"""
    )
    result = subprocess.run([node, "-e", script], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {"floor_id": "f1", "space_id": "s1"},
        {"floor_id": "f1", "space_id": "s1", "asset_id": "a1"},
        {"floor_id": "f1", "space_id": "s1", "point": [1.5, -2]},
        None,
    ]
