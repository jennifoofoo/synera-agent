// Last line of defence against overlapping map labels and icons, measured on screen.
//
// Labels.tsx lays text and symbols out in advance from the plan (top-down, screen px at the zoom bucket's scale).
// That is exact for the unrotated 2D plan, but not for the tilted perspective of 3D (rows of rooms squeeze together
// towards the horizon, labels float at the marker's height), for a rotated plan, nor for the chips that Markers.tsx
// floats above closed lifts and floor changes in 3D, which no layout sees. So after every frame that moved the
// camera this pass measures every drei <Html> element on the map and hides the lower ranked one of any pair that
// touches, and any label on a marker drawn in three.js (here dot, route ends, tap pin). The tap pin itself yields to
// the here dot and the route ends.
// When (docs/specs/label-rules.md, rule 5): only at decision points, never while the map only pans or rotates (the
// labels still follow the camera, the visible set stays): a zoom step (more than 15 %, labelRules.ts), a change of
// the labels on the map (floor, zoom bucket, route, selection, round: Labels.tsx re-lays them out), of the "you are
// here" spot, the selection, the round, the view or the building, and a resize.
// Who wins: the shared priority list (labelRules.ts, `data-label-class` on every label). Hysteresis: a shown label
// stays until it really touches another, a hidden one only comes back with REVEAL_PX of free space around it.
// At rest: if a rotation brought two shown labels together, the lower ranked one fades to 0 once the camera has been
// still for REST_MS (and fades back when they part), so nothing flickers during the motion.
// Hiding is only `visibility` (fading only `opacity`) on drei's wrapper; nothing about the look changes.

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { useTwin } from "../store";
import { useRound } from "../round/round";
import { blocked, rankOfClass, ZOOM_MARGIN, zoomStepChanged, type Box, type LabelClass } from "./labelRules";
import { metresPerPixelOf } from "./mapZoom";
import { controlsRef } from "./FloorMesh";
import { frameSize, HERE_RIM_PX, PIN_HEAD_PX, PIN_HEIGHT_PX, START_DOT_PX, TAP_CROSS_PX, TAP_RING_PX, TAP_STALK_M } from "./markerLayout";

const THROTTLE_MS = 90; // decisions at most this often (a fast zoom crosses several steps)
const TOUCH_PX = 0.5; // boxes may touch by this much (rounding), any more and the lower ranked one goes
const REVEAL_PX = 3; // a hidden label only comes back with this much free space around it
const HYSTERESIS = { hold: TOUCH_PX, reveal: REVEAL_PX };
const HIDDEN = "declutter-hidden";
const FADED = "declutter-faded";
/** After a rotation two shown labels may touch (the visible set stays while the view only moves): once the camera has
 * been still this long, the lower ranked one of such a pair fades out; it stays in the set and comes back at rest or
 * at the next decision. Nothing changes while the camera moves. */
const REST_MS = 300;
const FADE_MS = 200;

/** Bumped at every decision. Per-frame label rules elsewhere (the far-label cull of 3D room names in Labels.tsx)
 * re-decide only when it changes, so they keep still while the map pans or rotates, too. */
export const labelDecision = { epoch: 0 };

/** The class of a map element in the shared priority list: `data-label-class` (Labels.tsx), else by its look (the
 * chips and badges of Markers.tsx and poiIcons.tsx are markers). */
export function classOf(content: Element): LabelClass | string {
  const own = (content as HTMLElement).dataset?.labelClass;
  if (own) return own;
  const c = content.classList;
  if (c.contains("chip") || c.contains("floor-badge") || c.contains("found-dot") || c.contains("walk-estimated")) return "marker";
  if (c.contains("found-name")) return "found";
  if (c.contains("label-dest")) return "destination";
  if (c.contains("label-selected")) return "selected";
  if (c.contains("label-marked")) return "here";
  const kind = (content as HTMLElement).dataset?.zoomKind ?? "";
  if (kind.startsWith("poi-")) return content.querySelector(".poi-closed") ? "closure" : kind === "poi-extinguisher" ? "furniture" : "poi";
  if (kind === "closed-tag") return "closure";
  if (kind === "thing") return c.contains("label-landmark") ? "landmark" : "machine";
  if (kind === "area") return "zone";
  if (kind === "sub" || kind === "door") return "detail";
  return "room";
}

/** Priority of a map element (lower wins). */
export function rankOf(content: Element): number {
  return rankOfClass(classOf(content));
}

function touches(a: Box, b: Box): boolean {
  return blocked(a, b, true, HYSTERESIS);
}

/** A box grown about its centre by ZOOM_MARGIN. Between two decisions the map may zoom out by up to that factor,
 * which brings every pair of centres closer by it while the labels keep their size on screen; testing the grown
 * boxes keeps them apart anywhere inside the zoom step. */
function grown(box: Box): Box {
  const dx = ((box.x1 - box.x0) * (ZOOM_MARGIN - 1)) / 2;
  const dy = ((box.y1 - box.y0) * (ZOOM_MARGIN - 1)) / 2;
  return { x0: box.x0 - dx, y0: box.y0 - dy, x1: box.x1 + dx, y1: box.y1 + dy };
}

const v = new THREE.Vector3();
const target = new THREE.Vector3();

const MARKERS = new Set(["here-dot", "walk-estimate", "route-start", "route-end", "tap-pin"]);

/** Is a marker drawn? The tap pin hidden by an earlier pass still counts, so it can come back once there is room. */
function markerShown(obj: THREE.Object3D): boolean {
  if (!obj.visible && !(obj.userData.declutterHidden && obj.name === "tap-pin")) return false;
  for (let p = obj.parent; p; p = p.parent) if (!p.visible) return false;
  return true;
}

const markerAt = new THREE.Vector3();

/** Which markers are drawn and where (to 10 cm): a marker that appears, goes or moves is a decision point (a route
 * end drawn anew, the tap pin, the "you are here" dot walking). Camera moves do not change it. */
function markerSignature(scene: THREE.Scene): string {
  const parts: string[] = [];
  scene.traverse((obj) => {
    if (!obj.name || !MARKERS.has(obj.name) || !markerShown(obj)) return;
    obj.getWorldPosition(markerAt);
    parts.push(`${obj.uuid}@${Math.round(markerAt.x * 10)},${Math.round(markerAt.y * 10)},${Math.round(markerAt.z * 10)}`);
  });
  return parts.join("|");
}

/** Screen boxes (client px) of the markers drawn in three.js at a constant size on screen (markerLayout.tsx). */
function markerBoxes(scene: THREE.Scene, camera: THREE.Camera, rect: DOMRect): { fixed: Box[]; taps: { obj: THREE.Object3D; boxes: Box[] }[] } {
  const ortho = (camera as THREE.OrthographicCamera).isOrthographicCamera;
  const project = (x: number, y: number, z: number): [number, number] => {
    v.set(x, y, z).project(camera);
    return [rect.left + ((v.x + 1) / 2) * rect.width, rect.top + ((1 - v.y) / 2) * rect.height];
  };
  const frameH = frameSize(camera, rect.width, rect.height)[1];
  const metresPerPixel = (x: number, y: number, z: number) => {
    if (ortho) {
      const o = camera as THREE.OrthographicCamera;
      return (o.top - o.bottom) / o.zoom / Math.max(1, frameH);
    }
    const p = camera as THREE.PerspectiveCamera;
    return (2 * camera.position.distanceTo(v.set(x, y, z)) * Math.tan(THREE.MathUtils.degToRad(p.fov / 2))) / Math.max(1, frameH);
  };
  // a disc of `px` screen pixels lying on the floor (foreshortened in 3D)
  const disc = (x: number, y: number, z: number, px: number): Box => {
    const r = px * metresPerPixel(x, y, z);
    const pts = [project(x + r, y, z), project(x - r, y, z), project(x, y, z + r), project(x, y, z - r)];
    return { x0: Math.min(...pts.map((p) => p[0])), x1: Math.max(...pts.map((p) => p[0])), y0: Math.min(...pts.map((p) => p[1])), y1: Math.max(...pts.map((p) => p[1])) };
  };
  const fixed: Box[] = [];
  const taps: { obj: THREE.Object3D; boxes: Box[] }[] = [];
  const at = new THREE.Vector3();
  scene.traverse((obj) => {
    if (!obj.name) return;
    const name = obj.name;
    if (!MARKERS.has(name) || !markerShown(obj)) return;
    const boxes = name === "tap-pin" ? [] : fixed;
    if (name === "tap-pin") taps.push({ obj, boxes });
    obj.getWorldPosition(at);
    const { x, y, z } = at;
    if (name === "here-dot" || name === "walk-estimate") boxes.push(disc(x, y, z, HERE_RIM_PX));
    else if (name === "route-start") {
      if (obj.children.length) boxes.push(disc(x, y, z, START_DOT_PX));
    } else if (name === "route-end") {
      const [px, py] = project(x, y, z); // the pin stands upright on its tip
      boxes.push({ x0: px - PIN_HEAD_PX - 1.5, x1: px + PIN_HEAD_PX + 1.5, y0: py - PIN_HEIGHT_PX, y1: py });
    } else {
      boxes.push(disc(x, y, z, ortho ? TAP_CROSS_PX : TAP_RING_PX));
      if (!ortho) {
        const head = TAP_STALK_M - 0.2; // the 0.2 m head of the 3D pin's stalk
        const [hx, hy] = project(x, y + head, z);
        const r = 0.2 / metresPerPixel(x, y + head, z);
        boxes.push({ x0: hx - r, x1: hx + r, y0: hy - r, y1: hy + r });
      }
    }
  });
  return { fixed, taps };
}

function union(rects: DOMRect[]): Box | null {
  let box: Box | null = null;
  for (const r of rects) {
    if (r.width < 1 || r.height < 1) continue;
    box = box ? { x0: Math.min(box.x0, r.left), y0: Math.min(box.y0, r.top), x1: Math.max(box.x1, r.right), y1: Math.max(box.y1, r.bottom) } : { x0: r.left, y0: r.top, x1: r.right, y1: r.bottom };
  }
  return box;
}

/** Screen box of a map element. A symbol counts with the name beside it ("Lift 0.18"), which sits outside the
 * badge's own box, so two named symbols side by side are seen as overlapping. */
function contentBox(content: HTMLElement): Box | null {
  const kind = content.dataset.zoomKind ?? "";
  if (!kind.startsWith("poi-")) return union([content.getBoundingClientRect()]);
  const badge = content.firstElementChild;
  const name = content.querySelector(".poi-pin-name");
  return union([badge, name].filter((el): el is Element => !!el).map((el) => el.getBoundingClientRect()));
}

/** Floating UI over the map; a label under it is hidden. */
const CHROME = ".dock, .floorrail, .topbar, .round-toggle, .round-panel, .notes-fab-row, .recenter, .pill, .phone-search";

function chromeBoxes(): Box[] {
  const boxes: Box[] = [];
  for (const el of Array.from(document.querySelectorAll(CHROME))) {
    if (getComputedStyle(el).visibility === "hidden") continue;
    // The dock is one box from its first to its last panel (card, the gap, the Wanda bar), not its padding.
    const box = union(el.classList.contains("dock") ? Array.from(el.children).map((c) => c.getBoundingClientRect()) : [el.getBoundingClientRect()]);
    if (box) boxes.push(box);
  }
  return boxes;
}

/** Mounted once inside the Canvas. */
export function Declutter() {
  const gl = useThree((s) => s.gl);
  const events = useThree((s) => s.events);
  const invalidate = useThree((s) => s.invalidate);
  const last = useRef(0);
  const pending = useRef<number | null>(null);
  const state = useThree((s) => s.get);
  // Decision points: `dirty` is set by a change of the labels, the store or the canvas; the zoom and the camera
  // (2D / 3D) are checked every frame. `settle` counts the frames left before the pass (labels and transforms update).
  const dirty = useRef(true);
  const settle = useRef(0);
  const decided = useRef<{ mpp: number | null; camera: string; size: string; markers: string }>({ mpp: null, camera: "", size: "", markers: "" });
  const checked = useRef(0);
  const pose = useRef("");
  const rest = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pending.current !== null) window.clearTimeout(pending.current);
      if (rest.current !== null) window.clearTimeout(rest.current);
    },
    [],
  );

  // Labels added, removed or restyled (a new zoom bucket, floor, route, selection): drei mounts and unmounts its
  // wrappers here, Labels.tsx changes their classes. Our own hiding (classes on the wrappers) does not count.
  useEffect(() => {
    const target = (events.connected as HTMLElement | undefined) ?? (gl.domElement.parentNode as HTMLElement | null);
    if (!target) return;
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes" && record.target.parentNode === target) continue; // a wrapper: ours
        dirty.current = true;
        invalidate();
        return;
      }
    });
    observer.observe(target, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "data-label-class"] });
    return () => observer.disconnect();
  }, [events.connected, gl, invalidate]);

  // The "you are here" spot, the route, the selection, the floor, the view, the building and the round.
  useEffect(() => {
    const mark = () => {
      dirty.current = true;
      invalidate();
    };
    const twin = useTwin.subscribe((now, before) => {
      if (
        now.state?.position !== before.state?.position ||
        now.state?.route !== before.state?.route ||
        now.selection !== before.selection ||
        now.focusedFloorId !== before.focusedFloorId ||
        now.viewMode !== before.viewMode ||
        now.buildingKey !== before.buildingKey
      )
        mark();
    });
    const round = useRound.subscribe((now, before) => {
      if (now.index !== before.index || now.guiding !== before.guiding || now.plan !== before.plan || now.returning !== before.returning) mark();
    });
    return () => {
      twin();
      round();
    };
  }, [invalidate]);

  /** The map's drei <Html> labels with their rank and screen box, highest rank first (shown ones first on ties). */
  const measure = () => {
    // drei <Html> appends its wrappers here (Html.js: events.connected || gl.domElement.parentNode)
    const target = (events.connected as HTMLElement | undefined) ?? (gl.domElement.parentNode as HTMLElement | null);
    const items: { wrapper: HTMLElement; rank: number; shown: boolean; order: number; box: Box }[] = [];
    if (!target) return items;
    let order = 0;
    for (const child of Array.from(target.children)) {
      const wrapper = child as HTMLElement;
      if (wrapper === gl.domElement || !wrapper.style.transform.includes("translate3d")) continue;
      const content = wrapper.firstElementChild?.firstElementChild as HTMLElement | null | undefined;
      if (!content) continue;
      order++;
      if (wrapper.style.display === "none" || content.style.visibility === "hidden") continue; // behind the camera, culled
      const box = contentBox(content);
      if (!box) continue;
      items.push({ wrapper, rank: rankOf(content), shown: !wrapper.classList.contains(HIDDEN), order, box });
    }
    items.sort((a, b) => a.rank - b.rank || Number(b.shown) - Number(a.shown) || a.order - b.order);
    return items;
  };

  const fade = (wrapper: HTMLElement, out: boolean) => {
    if (out === wrapper.classList.contains(FADED)) return;
    wrapper.classList.toggle(FADED, out);
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    wrapper.style.transition = still ? "" : `opacity ${FADE_MS}ms`;
    wrapper.style.opacity = out ? "0" : "";
  };

  const pass = () => {
    pending.current = null;
    last.current = performance.now();
    const { scene, camera } = state();
    const rect = gl.domElement.getBoundingClientRect();
    const items = measure().map((item) => ({ ...item, box: grown(item.box) }));
    const shownBefore = new Map(items.map((item) => [item, item.shown]));
    const markers = markerBoxes(scene, camera, rect);
    const fixed = markers.fixed.map(grown);
    const taps = markers.taps.map(({ obj, boxes }) => ({ obj, boxes: boxes.map(grown) }));
    const kept = fixed;
    // The tap pin yields to the "You are here" dot and the route ends (zoomed out they can fall on one spot); the
    // tapped room stays named in its card. Hidden through three.js visibility, nothing about its look changes.
    for (const { obj, boxes } of taps) {
      const hide = boxes.some((box) => fixed.some((other) => touches(box, other)));
      if (!hide) kept.push(...boxes);
      if (hide !== Boolean(obj.userData.declutterHidden)) {
        obj.userData.declutterHidden = hide;
        obj.visible = !hide;
        invalidate(); // phones render on demand
      }
    }
    // Labels under the floating chrome (card, Wanda bar and the gap between them, rail, buttons) are hidden too:
    // nothing peeks out between two panels.
    kept.push(...chromeBoxes());
    for (const item of items) {
      const hide = kept.some((other) => blocked(item.box, other, shownBefore.get(item)!, HYSTERESIS));
      if (!hide) kept.push(item.box);
      fade(item.wrapper, false); // a decision starts from a clear map: no pair touches
      if (hide !== item.wrapper.classList.contains(HIDDEN)) {
        item.wrapper.classList.toggle(HIDDEN, hide);
        item.wrapper.style.visibility = hide ? "hidden" : "";
      }
    }
    invalidate(); // one more frame: a zoom step taken while this pass waited is seen at once (phones render on demand)
  };

  /** At rest after a move: the lower ranked of two shown labels that touch fades out, a faded one that is free again
   * fades back. The visible set (hidden or not) stays as decided. */
  const restPass = () => {
    rest.current = null;
    const { scene, camera } = state();
    const items = measure().filter((item) => item.shown);
    const kept = markerBoxes(scene, camera, gl.domElement.getBoundingClientRect()).fixed;
    for (const item of items) {
      const out = kept.some((other) => touches(item.box, other));
      if (!out) kept.push(item.box);
      fade(item.wrapper, out);
    }
  };

  // Checked after the frame (like the pass): inside useFrame the controls may not have moved the camera yet, and a
  // phone renders on demand, so a frame that came too early would leave the last zoom step unseen.
  const tick = () => {
    pending.current = null;
    if (settle.current > 0) {
      // a decision is under way: one more frame so labels re-rendered for it (and their transforms) are on screen
      settle.current--;
      if (settle.current === 0) pass();
      else invalidate();
      return;
    }
    const { camera, size, scene } = state();
    // the camera moved: look for touching labels once it has been still for REST_MS
    const e = camera.matrixWorld.elements;
    const poseKey = `${camera.uuid}:${e.map((x) => x.toFixed(3)).join(",")}:${size.width}x${size.height}`;
    if (poseKey !== pose.current) {
      pose.current = poseKey;
      if (rest.current !== null) window.clearTimeout(rest.current);
      rest.current = window.setTimeout(restPass, REST_MS);
    }
    const c = controlsRef.current;
    const focus = c ? c.getTarget(target) : target.set(0, 0, 0);
    const mpp = metresPerPixelOf(camera, size.width, size.height, focus);
    const sizeKey = `${size.width}x${size.height}`;
    const before = decided.current;
    // the markers are looked at as often as the old per-frame pass ran (a scene walk)
    const now = performance.now();
    const look = dirty.current || now - checked.current >= THROTTLE_MS;
    if (look) checked.current = now;
    const markers = look ? markerSignature(scene) : before.markers;
    if (!dirty.current && before.camera === camera.uuid && before.size === sizeKey && before.markers === markers && !zoomStepChanged(mpp, before.mpp)) return; // pan, rotate: keep
    dirty.current = false;
    decided.current = { mpp, camera: camera.uuid, size: sizeKey, markers };
    labelDecision.epoch++;
    settle.current = 2;
    invalidate(); // phones render on demand
  };

  // A card opening or closing changes which labels it covers without moving the camera (phones render on demand).
  useEffect(() => {
    const dock = document.querySelector(".dock");
    if (!dock || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => invalidate());
    observer.observe(dock);
    return () => observer.disconnect();
  }, [invalidate]);

  useFrame(() => {
    if (pending.current !== null) return;
    const wait = settle.current > 0 ? 0 : Math.max(0, THROTTLE_MS - (performance.now() - last.current));
    pending.current = window.setTimeout(tick, wait); // after this frame's <Html> transforms are written
  });
  return null;
}
