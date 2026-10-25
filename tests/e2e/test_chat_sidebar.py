"""Laptop chat column (docs/specs/chat-sidebar.md, twin/src/ui/Sidebar.tsx): on the planner profile from 1024 px the
chat is a fixed column on the left, the map uses the rest.

Desktop 1440x900 (column 420 px) and 1024x768 (planner forced, column 380 px). /api/chat is stubbed by Playwright
with long replies, so no API key and no cost. Skips without Playwright, chromium, data/dev or twin/dist.

Run: scripts/build_twin.sh && uv run --group e2e pytest -m e2e tests/e2e/test_chat_sidebar.py
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

pytestmark = pytest.mark.e2e

SIZES = {"1440": ({"width": 1440, "height": 900}, 420), "1024": ({"width": 1024, "height": 768}, 380)}
# Long enough that three of them overflow the column at 768 px, and that a 4-line clamp would cut them.
REPLIES = [
    "Reply one. "
    + "The nearest toilet is on this floor, past the kitchen on the left, about 25 m from the entrance. " * 4
    + "End of one.",
    "Reply two. "
    + "The kitchen next to the open office has a coffee machine, second door on the right. " * 4
    + "End of two.",
    "Reply three. "
    + "The nearest way out is the main entrance, straight ahead and then left at the reception. " * 4
    + "End of three.",
]

BOX = "(sel) => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; }"

# Every visible map label (drei <Html> wrappers move with an inline translate3d), as screen boxes.
MAP_LABELS = """() => {
  const inMap = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) if (e.style && e.style.transform.includes('translate3d')) return true; return false; };
  const visible = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.05) return false; } return true; };
  return [...document.querySelectorAll('.label')].filter((el) => inMap(el) && visible(el)).map((el) => {
    const r = el.getBoundingClientRect(); return { text: el.textContent.trim().slice(0, 30), left: r.left, right: r.right, top: r.top, bottom: r.bottom };
  }).filter((b) => b.right > b.left);
}"""


@pytest.fixture(scope="module")
def chromium(playwright_instance):
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed (playwright install chromium): {str(error)[:80]}")
    yield browser
    browser.close()


def _open(chromium, base_url, viewport, planner=False):
    context = chromium.new_context(viewport=viewport, device_scale_factor=1)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    calls = {"n": 0}

    def on_chat(route):
        reply = REPLIES[calls["n"] % len(REPLIES)]
        calls["n"] += 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"reply": reply, "backend": "fake"}))

    page.route("**/api/chat", on_chat)
    page.route("**/api/speak", lambda route: route.fulfill(status=503, body="no voice"))
    page.goto(base_url)
    page.wait_for_function("() => !!(window.__twinStore && window.__twinStore.getState().model)", timeout=30000)
    if planner:
        page.evaluate("() => window.__twinStore.getState().setProfile('planner')")
    page.evaluate("() => window.__twinStore.getState().reset && window.__twinStore.getState().reset()")
    page.wait_for_timeout(800)
    return context, page


@pytest.fixture(params=list(SIZES), ids=[f"desktop{k}" for k in SIZES])
def laptop(request, chromium, base_url):
    viewport, width = SIZES[request.param]
    context, page = _open(chromium, base_url, viewport, planner=viewport["width"] < 1100)
    page.evaluate("() => { try { localStorage.removeItem('twin.sidebarCollapsed'); } catch (e) {} }")
    page.wait_for_selector(".sidebar", timeout=20000)
    yield page, width
    assert page.errors == [], page.errors
    context.close()


def _ask(page, text: str) -> None:
    field = page.locator(".sidebar input[aria-label='Ask or search']")
    field.fill(text)
    field.press("Enter")
    page.wait_for_function("() => !window.__twinStore.getState().chatBusy", timeout=20000)


def test_column_width_and_order(laptop):
    page, width = laptop
    side = page.evaluate(BOX, ".sidebar")
    assert side["left"] == 0 and abs(side["width"] - width) <= 1, side
    assert page.locator(".sidebar .building-title").is_visible()
    assert page.locator(".sidebar .sb-floor").inner_text().strip()
    assert page.locator(".sidebar .wanda-orb").is_visible(), "the Wanda orb sits in the column"
    field = page.evaluate(BOX, ".sidebar input[aria-label='Ask or search']")
    log = page.evaluate(BOX, ".sidebar .sb-log")
    orb = page.evaluate(BOX, ".sidebar .wanda-orb")
    assert field["top"] >= log["bottom"], "the composer is at the bottom, under the conversation"
    assert (
        orb["right"] <= field["left"]
        and abs((orb["top"] + orb["bottom"]) / 2 - (field["top"] + field["bottom"]) / 2) < 6
    ), "one composer row: the orb left of the text field"
    assert page.locator(".sidebar input[aria-label='Ask or search']").count() == 1, "one text field"
    assert page.locator(".sidebar .wb-caption:visible").count() == 0, "no separate Wanda bar above the field"
    # the tools moved from the map into the column
    for name in ("Inspection round", "Notes", "Notes and photos on the map"):
        assert page.locator(".sidebar .sb-tools").get_by_role("button", name=name, exact=True).is_visible(), name
    assert page.locator(".notes-fab-row:not(.sidebar .notes-fab-row)").count() == 0
    # empty: Wanda's welcome and the chips sit in the conversation, the floating welcome card is gone
    assert page.locator(".sidebar .sb-welcome .welcome-title").is_visible()
    assert page.locator(".sidebar .sb-welcome .welcome-chip").count() >= 1
    assert page.locator(".welcome").count() == 0, "no welcome card over the map"
    canvas = page.evaluate(BOX, "canvas")
    assert abs(canvas["left"] - side["right"]) <= 1, "the canvas starts at the column's edge (never under it)"
    assert abs(canvas["right"] - page.viewport_size["width"]) <= 1
    assert page.locator(".dock").count() == 0, "no floating dock while the column is open"


def test_three_answers_complete_and_scrolled(laptop):
    page, _ = laptop
    for question in ("Where is the nearest toilet?", "Where can I get a coffee?", "What is the nearest way out?"):
        _ask(page, question)
    page.wait_for_timeout(300)
    texts = page.locator(".sidebar .sb-agent .sb-text").all_inner_texts()
    assert len(texts) == 3, texts
    for text, reply in zip(texts, REPLIES, strict=True):
        assert text.strip() == reply.strip(), "the whole answer, not a clamp"
    clipped = page.evaluate(
        "() => [...document.querySelectorAll('.sidebar .sb-agent .sb-text')].filter((el) => el.scrollHeight > el.clientHeight + 1).length"
    )
    assert clipped == 0
    assert page.locator(".sidebar .sb-user").count() == 3
    scroll = page.evaluate(
        "() => { const l = document.querySelector('.sidebar .sb-log'); return { top: l.scrollTop, height: l.scrollHeight, client: l.clientHeight }; }"
    )
    assert scroll["height"] > scroll["client"], f"three long answers overflow the column: {scroll}"
    assert scroll["top"] + scroll["client"] >= scroll["height"] - 2, f"scrolled to the newest answer: {scroll}"


def test_spoken_reply_in_log(laptop):
    page, _ = laptop
    # a spoken question goes through the same ask (voice = true), its answer lands in the conversation
    page.evaluate("() => window.__twinStore.getState().ask('Where is the nearest toilet?', true)")
    page.wait_for_function("() => document.querySelectorAll('.sidebar .sb-agent').length === 1", timeout=20000)
    assert "End of one." in page.locator(".sidebar .sb-agent").inner_text()


def _plan(page):
    return page.evaluate(
        "() => { const s = window.__twinStore.getState(); const m = s.model; const f = m.floorById.get(s.focusedFloorId) || m.floors[0];"
        " const rooms = f.spaces.filter((x) => x.type === 'room' && x.name && !m.connectorBySpace.has(x.id)).sort((a, b) => b.area_m2 - a.area_m2 || a.id.localeCompare(b.id));"
        " return { a: rooms[0].id, b: rooms[Math.min(3, rooms.length - 1)].id, c: rooms[1].id, floor: f.id, point: rooms[1].anchor }; }"
    )


def test_route_card_and_walk_in_column(laptop):
    page, _ = laptop
    plan = _plan(page)
    page.evaluate("([a, b]) => window.__twinStore.getState().route(a, b)", [plan["a"], plan["b"]])
    page.wait_for_function("() => window.__twinStore.getState().state?.route?.ok", timeout=15000)
    page.wait_for_selector(".sidebar .card", timeout=20000)
    assert page.locator(".card").count() == page.locator(".sidebar .card").count(), "every card sits in the column"
    page.evaluate("() => window.__twinStore.getState().requestCamera({ kind: 'home' })")
    page.wait_for_timeout(2500)
    edge = page.evaluate(BOX, ".sidebar")["right"]
    labels = page.evaluate(MAP_LABELS)
    assert labels, "the map shows labels"
    left_of_edge = [b for b in labels if b["left"] < edge - 1]
    assert not left_of_edge, f"labels under the column: {left_of_edge[:5]}"
    page.evaluate("() => window.__twinStore.getState().startWalk()")
    page.wait_for_selector(".sidebar .card-walk", timeout=20000)
    assert page.locator(".card-walk").count() == page.locator(".sidebar .card-walk").count()
    page.get_by_role("button", name="End route").first.click()


def test_collapse_and_reload(laptop):
    page, width = laptop
    page.locator(".sidebar .sb-toggle").click()
    page.wait_for_selector(".sidebar", state="detached", timeout=20000)
    page.wait_for_timeout(500)
    canvas = page.evaluate(BOX, "canvas")
    assert canvas["left"] == 0 and abs(canvas["width"] - page.viewport_size["width"]) <= 1, canvas
    assert page.locator(".sb-expand").is_visible()
    assert page.locator(".wanda-orb").is_visible(), "the orb stays when the column is hidden"
    page.reload()
    page.wait_for_function("() => !!(window.__twinStore && window.__twinStore.getState().model)", timeout=30000)
    if page.viewport_size["width"] < 1100:
        page.evaluate("() => window.__twinStore.getState().setProfile('planner')")
    page.wait_for_selector(".sb-expand", timeout=20000)
    assert page.locator(".sidebar").count() == 0, "still collapsed after a reload"
    page.locator(".sb-expand").click()
    page.wait_for_selector(".sidebar", timeout=20000)
    assert abs(page.evaluate(BOX, ".sidebar")["width"] - width) <= 1


@pytest.mark.parametrize("case", ["worker-1440", "narrow-800"])
def test_no_column_on_phone_profile_or_narrow(case, chromium, base_url):
    viewport = {"width": 1440, "height": 900} if case == "worker-1440" else {"width": 800, "height": 700}
    context, page = _open(chromium, base_url, viewport)
    try:
        if case == "worker-1440":
            page.evaluate("() => window.__twinStore.getState().setProfile('worker')")
        else:
            page.evaluate("() => window.__twinStore.getState().setProfile('planner')")  # planner, but under 1024 px
        page.wait_for_timeout(500)
        assert page.locator(".sidebar").count() == 0
        assert page.locator(".sb-expand").count() == 0
        assert page.locator(".dock .omnibox").count() == 1, "the floating dock as before"
        assert page.errors == [], page.errors
    finally:
        context.close()


MARKDOWN = "Two places:\n\n1. **Café (Gastraum)**, 20 m\n2. *Kitchen*, 35 m\n\n- <b>not html</b>\nAnswer: Café"


def test_reply_markdown_rendered(laptop):
    page, _ = laptop
    page.unroute("**/api/chat")
    page.route(
        "**/api/chat",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"reply": MARKDOWN, "backend": "fake"})
        ),
    )
    _ask(page, "Where can I eat?")
    bubble = page.locator(".sidebar .sb-agent .sb-text").last
    assert bubble.locator("ol > li").count() == 2
    assert bubble.locator("ol strong").inner_text() == "Café (Gastraum)"
    assert bubble.locator("ol em").inner_text() == "Kitchen"
    assert bubble.locator("ul > li").inner_text() == "<b>not html</b>", "markup stays text"
    assert bubble.locator("b").count() == 0
    assert "**" not in bubble.inner_text() and "Answer:" not in bubble.inner_text()


def test_place_card_note_opens_form_for_that_room(laptop):
    page, _ = laptop
    plan = _plan(page)
    name = page.evaluate("(id) => window.__twinStore.getState().model.spaceById.get(id).name", plan["c"])
    page.evaluate(
        "([id, p, f]) => window.__twinStore.getState().select({ kind: 'space', id, floor_id: f, point: p })",
        [plan["c"], plan["point"], plan["floor"]],
    )
    card = page.locator(".sidebar .card-selection")
    card.wait_for(timeout=20000)
    actions = card.locator(".card-actions button")
    assert [t.strip() for t in actions.all_inner_texts()][:3] == ["Route", "I'm here", "Note"]
    card.get_by_role("button", name="Add a note here").click()
    form = page.get_by_role("region", name="New note").or_(page.locator("section[aria-label='New note']"))
    form.first.wait_for(timeout=20000)
    assert name in form.first.inner_text(), "the form is about exactly that room"
    assert "Wanda, note:" in form.first.inner_text(), "the voice tip"
    assert page.evaluate("() => window.__twinStore.getState().selection") is None
