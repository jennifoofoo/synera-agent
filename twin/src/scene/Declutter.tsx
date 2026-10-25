// Last line of defence against overlapping map labels and icons, measured on screen.
//
// Labels.tsx lays text and symbols out in advance from the plan (top-down, screen px at the zoom bucket's scale).
// That is exact for the unrotated 2D plan, but not for the tilted perspective of 3D (rows of rooms squeeze together
// towards the horizon, labels float at the marker's height), for a rotated plan, nor for the chips that Markers.tsx
// floats above closed lifts and floor changes in 3D, which no layout sees. So after every frame that moved the
// camera (at most every THROTTLE_MS) this pass measures every drei <Html> element on the map and hides the lower
// ranked one of any pair that touches, and any label on a marker drawn in three.js (here dot, route ends, tap pin).
// The tap pin itself yields to the here dot and the route ends.
// Hiding is only `visibility` on drei's wrapper; nothing about the look changes. Ties keep what is already shown,
// so labels do not flicker while the camera moves.

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { frameSize, HERE_RIM_PX, PIN_HEAD_PX, PIN_HEIGHT_PX, START_DOT_PX, TAP_CROSS_PX, TAP_RING_PX, TAP_STALK_M } from "./markerLayout";

interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

const THROTTLE_MS = 90;
const TOUCH_PX = 0.5; // boxes may touch by this much (rounding), any more and the lower ranked one goes
const HIDDEN = "declutter-hidden";

/** Priority of a map element (lower wins), in the order Labels.tsx lays them out: chips and badges, found names,
 * the marked rooms (destination, tapped, other markers), closed glyphs and their tag, symbols, landmarks, room and
 * area names, machine names, fire extinguishers, second lines, door widths. */
export function rankOf(content: Element): number {
  const c = content.classList;
  if (c.contains("chip") || c.contains("floor-badge") || c.contains("found-dot") || c.contains("walk-estimated")) return 0;
  if (c.contains("found-name")) return 1;
  if (c.contains("label-dest")) return 2;
  if (c.contains("label-selected")) return 3;
  if (c.contains("label-marked")) return 4;
  const kind = (content as HTMLElement).dataset?.zoomKind ?? "";
  if (kind.startsWith("poi-")) return content.querySelector(".poi-closed") ? 5 : kind === "poi-extinguisher" ? 10 : 7;
  if (kind === "closed-tag") return 6;
  if (kind === "thing") return c.contains("label-landmark") ? 8 : 9;
  if (kind === "room" || kind === "area") return 8.5;
  if (kind === "sub") return 11;
  if (kind === "door") return 12;
  return 8.5;
}

function touches(a: Box, b: Box): boolean {
  return Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0) > TOUCH_PX && Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0) > TOUCH_PX;
}

const v = new THREE.Vector3();

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
  // the tap pin may be hidden by an earlier pass (below): it still counts, so it can come back once there is room
  const shown = (obj: THREE.Object3D) => {
    if (!obj.visible && !(obj.userData.declutterHidden && obj.name === "tap-pin")) return false;
    for (let p = obj.parent; p; p = p.parent) if (!p.visible) return false;
    return true;
  };
  scene.traverse((obj) => {
    if (!obj.name) return;
    const name = obj.name;
    if (name !== "here-dot" && name !== "walk-estimate" && name !== "route-start" && name !== "route-end" && name !== "tap-pin") return;
    if (!shown(obj)) return;
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

/** Mounted once inside the Canvas. */
export function Declutter() {
  const gl = useThree((s) => s.gl);
  const events = useThree((s) => s.events);
  const invalidate = useThree((s) => s.invalidate);
  const last = useRef(0);
  const pending = useRef<number | null>(null);
  const state = useThree((s) => s.get);

  useEffect(
    () => () => {
      if (pending.current !== null) window.clearTimeout(pending.current);
    },
    [],
  );

  const pass = () => {
    pending.current = null;
    last.current = performance.now();
    const { scene, camera } = state();
    // drei <Html> appends its wrappers here (Html.js: events.connected || gl.domElement.parentNode)
    const target = (events.connected as HTMLElement | undefined) ?? (gl.domElement.parentNode as HTMLElement | null);
    if (!target) return;
    const rect = gl.domElement.getBoundingClientRect();
    const items: { wrapper: HTMLElement; rank: number; shown: boolean; order: number; box: Box }[] = [];
    let order = 0;
    for (const child of Array.from(target.children)) {
      const wrapper = child as HTMLElement;
      if (wrapper === gl.domElement || !wrapper.style.transform.includes("translate3d")) continue;
      const content = wrapper.firstElementChild?.firstElementChild as HTMLElement | null | undefined;
      if (!content) continue;
      order++;
      if (wrapper.style.display === "none" || content.style.visibility === "hidden") continue; // behind the camera, culled
      const kind = content.dataset.zoomKind ?? "";
      const measured = (kind.startsWith("poi-") && content.firstElementChild) || content;
      const r = measured.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      items.push({ wrapper, rank: rankOf(content), shown: !wrapper.classList.contains(HIDDEN), order, box: { x0: r.left, y0: r.top, x1: r.right, y1: r.bottom } });
    }
    items.sort((a, b) => a.rank - b.rank || Number(b.shown) - Number(a.shown) || a.order - b.order);
    const { fixed, taps } = markerBoxes(scene, camera, rect);
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
    for (const item of items) {
      const hide = kept.some((other) => touches(item.box, other));
      if (!hide) kept.push(item.box);
      if (hide !== item.wrapper.classList.contains(HIDDEN)) {
        item.wrapper.classList.toggle(HIDDEN, hide);
        item.wrapper.style.visibility = hide ? "hidden" : "";
      }
    }
  };

  useFrame(() => {
    if (pending.current !== null) return;
    const wait = Math.max(0, THROTTLE_MS - (performance.now() - last.current));
    // after this frame's <Html> transforms are written; a trailing pass catches the last frame of a movement
    pending.current = window.setTimeout(pass, wait);
  });
  return null;
}
