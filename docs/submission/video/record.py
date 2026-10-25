"""Screen recordings for the video (storyboard §B), made with Playwright at 1920x1080, no audio.

Needs the twin running locally with the Urban Colab (floors -1..4), e.g. the preview on http://127.0.0.1:5186.

    uv run --group e2e python docs/submission/video/record.py p1          # laptop: plan the floor-3 round
    uv run --group e2e python docs/submission/video/record.py p3          # architecture.html (diagram + 145 card)
    uv run --group e2e python docs/submission/video/record.py p4          # floor 3: 2D plan, then 3D
    uv run --group e2e python docs/submission/video/record.py all
Options: --url http://127.0.0.1:5186  --out docs/submission/video/rec  --headed

Each scene writes one WebM into --out (git-ignored), named after the scene. CapCut imports WebM directly.
"""

import argparse
import shutil
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).parent
BUILDING = "user/plan-89323a15"
MAIN_STAIRS_F3 = "plan-89323a15-F3-S014"
FLOOR_3 = "plan-89323a15-F3"
SIZE = {"width": 1920, "height": 1080}


def glide(page: Page, x: float, y: float, steps: int = 30) -> None:
    """Moves the (drawn) cursor slowly, so clicks read on video."""
    page.mouse.move(x, y, steps=steps)
    time.sleep(0.25)


def click_slow(page: Page, locator) -> None:
    box = locator.bounding_box()
    if box is None:
        locator.click()
        return
    glide(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    locator.click()
    time.sleep(0.6)


CURSOR_JS = """
(() => {
  if (document.getElementById('rec-cursor')) return;
  const c = document.createElement('div');
  c.id = 'rec-cursor';
  Object.assign(c.style, {position: 'fixed', left: '0px', top: '0px', width: '22px', height: '22px', marginLeft: '-11px',
    marginTop: '-11px', borderRadius: '50%', background: 'rgba(0,79,171,0.35)', border: '2px solid #004fab',
    pointerEvents: 'none', zIndex: 99999, transition: 'transform 0.12s'});
  document.body.appendChild(c);
  addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { c.style.transform = 'scale(0.7)'; }, true);
  addEventListener('mouseup', () => { c.style.transform = 'none'; }, true);
})();
"""


def open_twin(page: Page, url: str) -> None:
    page.goto(f"{url}/?building={BUILDING}")
    page.wait_for_function("() => window.__twinAudit?.store?.getState()?.model", timeout=60_000)
    page.evaluate(CURSOR_JS)
    time.sleep(1.5)
    # The welcome card hides the map until the first interaction: close it before the take starts.
    page.mouse.click(SIZE["width"] / 2, SIZE["height"] - 200)
    time.sleep(1.0)


def scene_p1(page: Page, url: str) -> None:
    """Laptop planning: floor 3, Round, fire extinguishers, Floor 3, start at the Main Stairs, the planned route."""
    open_twin(page, url)
    # Start = "where I am" (the round's default start); set to the Main Stairs on floor 3 before the take.
    page.evaluate(
        "([space, floor]) => window.__twinAudit.store.getState().setHere({space_id: space, floor_id: floor})",
        [MAIN_STAIRS_F3, FLOOR_3],
    )
    page.evaluate("(floor) => window.__twinAudit.store.getState().focusFloor(floor)", FLOOR_3)
    time.sleep(2.5)
    click_slow(page, page.get_by_role("button", name="Round"))
    time.sleep(1.0)
    click_slow(page, page.get_by_role("button", name="Fire extinguishers"))
    click_slow(page, page.get_by_role("radio", name="Floor 3", exact=True))
    page.get_by_text("Start round").wait_for(timeout=30_000)
    time.sleep(1.0)
    glide(page, SIZE["width"] * 0.5, SIZE["height"] * 0.4, steps=60)
    time.sleep(5.0)


def scene_p3(page: Page, url: str) -> None:
    """The architecture beat: Space plays the 15-s animation."""
    page.goto((HERE / "architecture.html").resolve().as_uri())
    time.sleep(1.0)
    page.keyboard.press("Space")
    time.sleep(16.0)


def scene_p4(page: Page, url: str) -> None:
    """Floor 3 as a 2D plan, then the 3D twin (for the evacuation-plan crossfade)."""
    open_twin(page, url)
    page.evaluate("(floor) => window.__twinAudit.store.getState().focusFloor(floor)", FLOOR_3)
    page.evaluate("() => window.__twinAudit.store.getState().setViewMode('2d')")
    time.sleep(4.0)
    page.evaluate("() => window.__twinAudit.store.getState().setViewMode('3d')")
    time.sleep(5.0)


SCENES = {"p1": scene_p1, "p3": scene_p3, "p4": scene_p4}


def record(name: str, url: str, out: Path, headed: bool) -> Path:
    tmp = out / f".tmp-{name}"
    shutil.rmtree(tmp, ignore_errors=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport=SIZE, device_scale_factor=1, record_video_dir=str(tmp), record_video_size=SIZE)
        page = context.new_page()
        SCENES[name](page, url)
        video = page.video
        context.close()
        browser.close()
        src = Path(video.path()) if video else None
    target = out / f"{name}.webm"
    if src and src.exists():
        shutil.move(str(src), target)
    shutil.rmtree(tmp, ignore_errors=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scene", choices=[*SCENES, "all"])
    parser.add_argument("--url", default="http://127.0.0.1:5186")
    parser.add_argument("--out", type=Path, default=HERE / "rec")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in SCENES if args.scene == "all" else [args.scene]:
        print(name, "->", record(name, args.url, args.out, args.headed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
