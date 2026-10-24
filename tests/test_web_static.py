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
