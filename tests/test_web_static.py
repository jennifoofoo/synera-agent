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
