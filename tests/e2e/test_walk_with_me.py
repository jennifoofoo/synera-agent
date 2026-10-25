"""Walk with me in the step guide (twin/src/walkWithMe.ts): synthetic steps move an estimated dot along the route.

Flow on a phone-sized page: route across two floors on a dev building, open the guide, switch "Walk with me" on
(motion permission stubbed), window.__walkSim(3). The dot moves along the route line, the step advances at a leg
end, it waits at the stairs until Next, End route stops it, and nothing is sent to the server as a position.
The chat turn is faked (tests/e2e/fake_chat_server.py): no API key, no cost. Skips without Playwright, a browser,
data/dev or twin/dist.

Run: scripts/build_twin.sh && uv run pytest -m e2e tests/e2e/test_walk_with_me.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed (uv sync --group e2e)")

from tests.e2e.conftest import DATA, REPO, _free_port

pytestmark = pytest.mark.e2e

# Stub the iOS-style permission prompt and record every request body the page sends.
INIT = """
window.DeviceMotionEvent = window.DeviceMotionEvent || function () {};
window.DeviceMotionEvent.requestPermission = async () => "granted";
window.__sent = [];
const realFetch = window.fetch.bind(window);
window.fetch = (input, init) => {
  try { window.__sent.push({ url: String(input && input.url || input), body: init && init.body ? String(init.body) : "" }); } catch (e) {}
  return realFetch(input, init);
};
"""

# A route that crosses floors and walks a few metres before the stairs: tries room pairs on the first two floors.
FIND_ROUTE = """async () => {
  const s = window.__twinStore.getState();
  const floors = [...s.model.floors].sort((a, b) => a.level - b.level);
  const rooms = (f) => f.spaces.filter((x) => !/stair|lift|elevator|shaft/i.test(x.type + " " + (x.name || "")));
  const a = rooms(floors[0]), b = rooms(floors[floors.length - 1]);
  for (let i = 0; i < Math.min(a.length, 12); i++) {
    for (let j = 0; j < Math.min(b.length, 4); j++) {
      await window.__twinStore.getState().route(a[i].id, b[j].id);
      const r = window.__twinStore.getState().state.route;
      if (!r || !r.ok || !(r.floor_changes || []).length || !r.steps) continue;
      const seg = r.segments[0].points;
      let len = 0;
      for (let k = 1; k < seg.length; k++) len += Math.hypot(seg[k][0] - seg[k - 1][0], seg[k][1] - seg[k - 1][1]);
      if (len > 6) return { start: a[i].id, destination: b[j].id, steps: r.steps };
    }
  }
  return null;
}"""

RECORD = """() => {
  window.__stepLog = [];
  window.__estLog = [];
  window.__twinStore.subscribe((s) => window.__stepLog.push(s.walkStep));
  window.__walkMotion.subscribe((m) => m.estimate && window.__estLog.push({ point: m.estimate.point, floor: m.estimate.floorId,
    along: m.estimate.alongRouteM, leg: m.estimate.legIndex, atConnector: m.estimate.atConnector, left: m.estimate.distanceLeftM }));
}"""

NEAR_ROUTE = """() => {
  const r = window.__twinStore.getState().state.route;
  const dist = (p, pts) => {
    if (pts.length === 1) return Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]);
    let best = Infinity;
    for (let i = 1; i < pts.length; i++) {
      const [a, b] = [pts[i - 1], pts[i]], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
      const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
      best = Math.min(best, Math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]));
    }
    return best;
  };
  return window.__estLog.map((e) => Math.min(...r.segments.filter((s) => s.floor_id === e.floor).map((s) => dist(e.point, s.points))));
}"""


def _multi_floor_building(target) -> str:
    """Copy the smallest dev building with two or more floors and a stair or lift; return its key."""
    dev = DATA / "dev"
    if not dev.exists():
        pytest.skip("data/dev is missing (symlink data into the worktree)")
    found = []
    for folder in dev.iterdir():
        path = folder / "building.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        if len(data.get("floors", [])) >= 2 and data.get("vertical_connectors"):
            found.append((sum(f.stat().st_size for f in folder.iterdir() if f.is_file()), folder.name, folder))
    if not found:
        pytest.skip("no multi-floor dev building")
    _, name, folder = min(found)
    shutil.copytree(folder, target / "dev" / name)
    return f"dev/{name}"


@pytest.fixture()
def server(tmp_path_factory):
    if not (REPO / "twin" / "dist" / "index.html").exists():
        pytest.skip("twin/dist is missing (scripts/build_twin.sh)")
    data = tmp_path_factory.mktemp("walk_data")
    key = _multi_floor_building(data)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith("ANTHROPIC")}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.e2e.fake_chat_server",
            "--data",
            str(data),
            "--port",
            str(port),
            "--env-file",
            str(data / "no.env"),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail("fake chat server exited early")
            try:
                urllib.request.urlopen(url + "/", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("fake chat server did not start")
        yield url, key
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def page(server, playwright_instance):
    url, key = server
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, device_scale_factor=2
    )
    context.add_init_script(INIT)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{url}/?building={key}")
    page.wait_for_function(
        "() => !!(window.__twinStore && window.__twinStore.getState().model && window.__walkMotion)", timeout=20000
    )
    page.wait_for_timeout(1000)
    yield page
    context.close()
    browser.close()


def test_walk_with_me_moves_the_estimate_and_never_sends_it(page):
    found = page.evaluate(FIND_ROUTE)
    if not found:
        pytest.skip("no route across floors with a walk before the stairs in the picked building")
    steps = found["steps"]
    if len(steps) > 1 and steps[0].startswith(("Start in ", "Start at ")):
        steps = steps[1:]  # the guide leaves out the opening "Start in X" line (store.ts walkLines)
    ride = next(i for i, line in enumerate(steps) if line.startswith(("Take ", "Use ")))
    # This test drives the switch itself; the first-time hint (which stands in for the switch) is answered already.
    page.evaluate("() => window.__walkMotion.setState({ answered: true })")
    page.evaluate("() => window.__twinStore.getState().startWalk()")
    page.wait_for_function("() => window.__twinStore.getState().walkStep === 0", timeout=5000)
    switch = page.get_by_role("switch", name="Walk with me")
    assert not switch.is_checked(), "Walk with me is off by default"
    page.evaluate(RECORD)
    sent_before = page.evaluate("() => window.__sent.length")

    switch.click()
    page.wait_for_function(
        "() => window.__walkMotion.getState().on && !!window.__walkMotion.getState().estimate", timeout=5000
    )
    assert page.get_by_text("on", exact=True).is_visible()
    assert page.evaluate("() => localStorage.getItem('twin.walkWithMe')") == "1"

    page.evaluate("() => window.__walkSim(3)")
    # waits at the stairs: the dot stops, the guide shows the ride step
    page.wait_for_function("() => window.__walkMotion.getState().estimate?.atConnector", timeout=30000)
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__twinStore.getState().walkStep") == ride
    assert page.get_by_text("Waiting here").is_visible()
    est = page.evaluate("() => window.__estLog")
    assert len({tuple(e["point"]) for e in est}) > 3, "the dot moved"
    assert max(page.evaluate(NEAR_ROUTE)) < 0.05, "every estimate lies on the route line"
    lefts = [e["left"] for e in est]
    assert lefts[-1] < lefts[0]
    assert page.locator(".walk-left").inner_text() == str(
        round(page.evaluate("() => window.__walkMotion.getState().estimate.distanceLeftM"))
    )
    assert page.locator(".walk-estimated").is_visible(), "the dot is labelled estimated"
    walked = [s for s in page.evaluate("() => window.__stepLog") if s is not None]
    assert walked == sorted(walked) and walked[-1] == ride, "the step moved forward with the estimate"
    if ride >= 2:
        assert len(set(walked)) >= 3, "steps before the stairs advanced on their own"

    held = page.evaluate("() => window.__walkMotion.getState().estimate.alongRouteM")
    page.wait_for_timeout(1500)
    assert page.evaluate("() => window.__walkMotion.getState().estimate.alongRouteM") == held, "it waits at the stairs"
    assert page.evaluate("() => window.__twinStore.getState().walkStep") == ride

    page.get_by_role("button", name="Next", exact=True).click()
    page.wait_for_function(
        "(held) => { const e = window.__walkMotion.getState().estimate; return e && !e.atConnector && e.legIndex > 0 && e.alongRouteM > held + 0.5; }",
        arg=held,
        timeout=15000,
    )
    assert page.evaluate("() => window.__twinStore.getState().walkStep") > ride

    # arrival is a guess too: "You should be about there.", never "you have arrived"
    page.wait_for_function("() => window.__walkMotion.getState().arrived", timeout=30000)
    assert page.evaluate("() => window.__twinStore.getState().walkStep") == len(steps) - 1
    assert page.get_by_text("You should be about there.").is_visible()
    assert "arrived" not in page.locator(".walk-now").inner_text().lower()

    # "I'm here" (the person's own correction) moves the estimate and the step back to where she says she is
    page.evaluate("() => window.__walkSim(0)")
    here = page.evaluate("""() => { const s = window.__twinStore.getState(), seg = s.state.route.segments[0], p = seg.points;
      const point = [(p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2];
      const space = s.model.floorById.get(seg.floor_id).spaces.find((x) => x.id === s.state.route.start) || s.model.floorById.get(seg.floor_id).spaces[0];
      s.setHere({ space_id: space.id, floor_id: seg.floor_id, point }); return point; }""")
    page.wait_for_function("() => window.__walkMotion.getState().estimate?.legIndex === 0", timeout=5000)
    assert page.evaluate("() => window.__twinStore.getState().walkStep") < ride

    page.get_by_role("button", name="End route").click()
    page.wait_for_function("() => window.__twinStore.getState().walkStep === null", timeout=5000)
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.__walkMotion.getState().estimate") is None, "End route stops the module"
    count = page.evaluate("() => window.__estLog.length")
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.__estLog.length") == count, "no more estimates after End route"

    # nothing the module estimated reached the server as a position
    position = page.evaluate("() => window.__twinStore.getState().state.position")
    assert position is None or position["point"] == here, "only the person's own 'I'm here' is a position"
    sent = page.evaluate("() => window.__sent")[sent_before:]
    for request in sent:
        assert '"here"' not in request["body"] and "start_point" not in request["body"], request
        assert "/api/chat" not in request["url"], request
    assert not page.errors, page.errors


def _start_guide(page) -> None:
    if not page.evaluate(FIND_ROUTE):
        pytest.skip("no route across floors in the picked building")
    page.evaluate("() => window.__twinStore.getState().startWalk()")
    # generous: the laptop page renders 3D every frame, which is slow headless on a loaded machine
    page.wait_for_function("() => window.__twinStore.getState().walkStep === 0", timeout=20000)


def _restart_guide(page) -> None:
    page.evaluate("() => window.__twinStore.getState().stopWalk()")
    page.wait_for_timeout(200)
    page.evaluate("() => window.__twinStore.getState().startWalk()")
    page.wait_for_function("() => window.__twinStore.getState().walkStep === 0", timeout=5000)


def test_walk_hint_turns_it_on_once_and_is_not_asked_again(page):
    """Phone, first guide: the hint asks once; "Turn on" uses the switch path and is remembered."""
    _start_guide(page)
    hint = page.get_by_role("group", name="Walk with me hint")
    assert hint.is_visible()
    assert page.get_by_role("switch", name="Walk with me").count() == 0, "one Walk with me control at a time"
    assert "Walk with me?" in hint.inner_text()
    assert len(hint.inner_text().split()) <= 6, "one short line, no explanation text on the phone"
    hint.get_by_role("button", name="Turn on").click()
    page.wait_for_function("() => window.__walkMotion.getState().on", timeout=5000)
    assert page.get_by_role("switch", name="Walk with me").is_checked()
    assert page.evaluate("() => localStorage.getItem('twin.walkWithMe')") == "1"
    assert not hint.is_visible()
    assert page.get_by_role("switch", name="Walk with me").is_visible(), "the switch is back once answered"
    # switched off again later: still answered, the hint stays away
    page.get_by_role("switch", name="Walk with me").click()
    _restart_guide(page)
    assert page.get_by_role("group", name="Walk with me hint").count() == 0
    assert not page.errors, page.errors


def test_walk_hint_not_now_is_remembered(page):
    _start_guide(page)
    page.get_by_role("group", name="Walk with me hint").get_by_role("button", name="Not now").click()
    assert page.get_by_role("group", name="Walk with me hint").count() == 0
    assert page.evaluate("() => localStorage.getItem('twin.walkWithMe')") == "0"
    assert not page.evaluate("() => window.__walkMotion.getState().on")
    page.reload()
    page.wait_for_function(
        "() => !!(window.__twinStore && window.__twinStore.getState().model && window.__walkMotion)", timeout=20000
    )
    _start_guide(page)
    assert page.get_by_role("group", name="Walk with me hint").count() == 0, "not asked again after a reload"


def test_walk_hint_only_after_the_first_step(page):
    """The hint belongs to the start of the guide: after Next it is gone, the switch is still there."""
    _start_guide(page)
    assert page.get_by_role("group", name="Walk with me hint").is_visible()
    page.get_by_role("button", name="Next", exact=True).click()
    assert page.get_by_role("group", name="Walk with me hint").count() == 0
    assert page.get_by_role("switch", name="Walk with me").is_visible()


def test_walk_hint_never_on_a_laptop(server, playwright_instance):
    """A laptop (mouse, no touch) gets no hint, even though Chrome defines DeviceMotionEvent."""
    url, key = server
    try:
        browser = playwright_instance.chromium.launch()
    except Exception as error:  # noqa: BLE001 - missing browser binary
        pytest.skip(f"chromium not installed: {str(error)[:80]}")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    context.add_init_script(INIT)
    page = context.new_page()
    try:
        page.goto(f"{url}/?building={key}")
        page.wait_for_function(
            "() => !!(window.__twinStore && window.__twinStore.getState().model && window.__walkMotion)", timeout=20000
        )
        _start_guide(page)
        page.wait_for_timeout(300)
        assert page.get_by_role("group", name="Walk with me hint").count() == 0
    finally:
        context.close()
        browser.close()
