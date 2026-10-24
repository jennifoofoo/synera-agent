// 3D view of the page: the second view next to the 2D plan, sharing app.js state (building, closures, new doors,
// route, Level 4 draft). This file holds the view state and the steering API (window.view3d); scene3d.js only draws.
// app.js is a classic script: its top-level `app` and functions (showFloor, onSpaceClick, ...) are globals here.
import { Scene3D, spaceColour } from "./scene3d.js";

const $ = (selector) => document.querySelector(selector);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const DEFAULT_HIGHLIGHT = "#f59e0b";
const MAX_FIND_HALOS = 150;
const FLOOR_MODES = ["stacked", "exploded", "single"];
const THINGS_MODES = ["auto", "on", "off"];
const THINGS_LABELS = { auto: "Things: near", on: "Things: all", off: "Things: off" };

// What the 3D view shows. The API only changes this; sync() hands it to the scene.
const view = {
  active: false,
  floorMode: "stacked",
  things: "auto",
  focusFloor: null,
  highlights: new Map(), // name -> {ids, colour}
  routeOverride: undefined, // undefined: follow the page's route; null: none; object: this route
  pending: [], // camera moves asked for before the scene exists
};

let scene = null;
const seen = { building: null, state: null, suspect: null, floorId: null, highlight: null, picked: null, routeKey: "" };

const routeKey = (route) =>
  route?.ok ? JSON.stringify([route.start, route.destination, route.via, route.length_m, route.segments.map((s) => s.points.length)]) : "";

function pageApp() {
  return typeof app !== "undefined" ? app : null;
}

// ---------- ids: spaces, things, doors, stairs/lifts, floors (ids or exact names) ----------

function resolveIds(ids) {
  const a = pageApp();
  const out = { spaceIds: [], assetIds: [], openingIds: [], connectorIds: [], floorIds: [], unknown: [] };
  if (!a?.building) return out;
  const list = (Array.isArray(ids) ? ids : [ids]).filter((id) => id !== undefined && id !== null && id !== "");
  for (const raw of list) {
    const id = String(raw);
    if (a.spaces.has(id)) out.spaceIds.push(id);
    else if (a.openings.has(id)) out.openingIds.push(id);
    else if (a.connectors.has(id)) out.connectorIds.push(id);
    else if (a.building.floors.some((f) => f.id === id)) out.floorIds.push(id);
    else if (assetIndex().has(id)) out.assetIds.push(id);
    else {
      const byName = (items) => items.filter((item) => item.name === id).map((item) => item.id);
      const spaces = byName(a.building.spaces), assets = byName(a.building.assets), connectors = byName(a.building.connectors);
      const floors = a.building.floors.filter((f) => f.name === id || String(f.level) === id).map((f) => f.id);
      if (spaces.length + assets.length + connectors.length + floors.length === 0) out.unknown.push(id);
      out.spaceIds.push(...spaces); out.assetIds.push(...assets); out.connectorIds.push(...connectors); out.floorIds.push(...floors);
    }
  }
  return out;
}

let assetIndexCache = { building: null, map: new Map() };
function assetIndex() {
  const a = pageApp();
  if (assetIndexCache.building !== a.building) assetIndexCache = { building: a.building, map: new Map(a.building.assets.map((x) => [x.id, x])) };
  return assetIndexCache.map;
}

function floorOfIds(resolved) {
  const a = pageApp();
  if (resolved.floorIds.length) return resolved.floorIds[0];
  for (const id of resolved.spaceIds) return a.spaces.get(id).floor_id;
  for (const id of resolved.assetIds) return assetIndex().get(id).floor_id;
  for (const id of resolved.openingIds) return a.openings.get(id).floor_id;
  for (const id of resolved.connectorIds) return a.connectors.get(id).floor_ids[0];
  return null;
}

// ---------- the steering API ----------

const api = {
  /** Switch the map pane to 3D (or back with hide()). */
  show() { setActive(true); return api; },
  hide() { setActive(false); return api; },
  toggle() { setActive(!view.active); return api; },
  isActive: () => view.active,

  /** "stacked" (x-ray: floors above the focus are see-through), "exploded" (floors spread apart) or "single". */
  setFloorMode(mode, floorId = undefined) {
    if (!FLOOR_MODES.includes(mode)) throw new Error(`floor mode must be one of ${FLOOR_MODES.join(", ")}`);
    view.floorMode = mode;
    if (floorId !== undefined) api.focusFloor(floorId, { fly: false });
    pushLayout();
    if (scene) scene.fit();
    renderTools();
    return api;
  },

  /** Focus one floor (id, name or level): it becomes the solid one, the 2D plan switches with it. */
  focusFloor(floor, { fly = true } = {}) {
    const a = pageApp();
    const f = a?.building?.floors.find((x) => x.id === floor || x.name === floor || x.level === Number(floor));
    if (!f) return api;
    setFocus(f.id, { syncPage: true });
    if (fly) whenScene(() => scene.flyToIds([f.id]));
    return api;
  },

  /** Highlight ids in a colour, focus their floor and fly the camera to them. */
  focus(ids, { colour = DEFAULT_HIGHLIGHT, name = "focus" } = {}) {
    const resolved = resolveIds(ids);
    api.highlight(ids, colour, { name });
    const floorId = floorOfIds(resolved);
    if (floorId) setFocus(floorId, { syncPage: true });
    whenScene(() => scene.flyToIds([...resolved.spaceIds, ...resolved.assetIds, ...resolved.openingIds, ...resolved.connectorIds, ...resolved.floorIds]));
    return { unknown: resolved.unknown };
  },

  /** Colour ids (rooms, things, doors, stairs/lifts) under a name; the same name replaces, other names add up. */
  highlight(ids, colour = DEFAULT_HIGHLIGHT, { name = "default" } = {}) {
    view.highlights.set(name, { ids: Array.isArray(ids) ? ids : [ids], colour });
    pushHighlights();
    return { unknown: resolveIds(ids).unknown };
  },

  /** Remove one named highlight, or all of them. */
  clearHighlights(name = undefined) {
    if (name === undefined) view.highlights.clear(); else view.highlights.delete(name);
    pushHighlights();
    return api;
  },

  /** Fly the camera to an id (room, thing, door, stair/lift, floor) or to {floor_id, point: [x, y]}. */
  flyTo(target) {
    if (target && typeof target === "object" && !Array.isArray(target)) {
      if (target.floor_id) setFocus(target.floor_id, { syncPage: true });
      whenScene(() => scene.flyToPoint(target.floor_id, target.point, target.radius || 12));
      return api;
    }
    const resolved = resolveIds(target);
    const floorId = floorOfIds(resolved);
    if (floorId && !resolved.connectorIds.length) setFocus(floorId, { syncPage: true });
    whenScene(() => scene.flyToIds([...resolved.spaceIds, ...resolved.assetIds, ...resolved.openingIds, ...resolved.connectorIds, ...resolved.floorIds]));
    return api;
  },

  /** Draw a route (the /api/route shape). null hides it; showRoute() again with undefined follows the page's route. */
  showRoute(route = undefined, { animate = true } = {}) {
    view.routeOverride = route;
    seen.routeKey = "";
    if (scene) { pushRoute(); if (animate) scene.playRoute(); }
    return api;
  },

  /** Replay the route animation (static with prefers-reduced-motion). */
  playRoute() { if (scene) scene.playRoute(); return api; },

  /** "auto" (things near the camera / on the focused floor), "on" or "off". */
  setThings(mode) {
    if (!THINGS_MODES.includes(mode)) throw new Error(`things must be one of ${THINGS_MODES.join(", ")}`);
    view.things = mode;
    pushLayout();
    renderTools();
    return api;
  },

  /** Back to the overview of the building. */
  resetView() { whenScene(() => scene.fit()); return api; },

  /**
   * One call for a chat reply's {"view": {...}}. Keys, all optional, applied in this order:
   * mode "2d"|"3d", floor_mode, floor, clear_highlights (true or a name), highlight ({ids, colour, name} or a list),
   * focus (ids), fly_to (id or {floor_id, point}), route (route object or null), reset (true).
   */
  apply(spec = {}) {
    if (!spec || typeof spec !== "object") return api;
    if (spec.mode === "3d") api.show(); else if (spec.mode === "2d") api.hide();
    if (spec.floor_mode) api.setFloorMode(spec.floor_mode);
    if (spec.floor !== undefined) api.focusFloor(spec.floor, { fly: !spec.focus && !spec.fly_to });
    if (spec.things) api.setThings(spec.things);
    if (spec.clear_highlights) api.clearHighlights(spec.clear_highlights === true ? undefined : spec.clear_highlights);
    for (const h of [].concat(spec.highlight || [])) api.highlight(h.ids, h.colour || h.color || DEFAULT_HIGHLIGHT, { name: h.name || "default" });
    if (spec.focus) api.focus(spec.focus, { colour: spec.focus_colour || DEFAULT_HIGHLIGHT });
    if (spec.fly_to) api.flyTo(spec.fly_to);
    if (spec.route !== undefined) api.showRoute(spec.route);
    if (spec.reset) api.resetView();
    return api;
  },

  /** Build time, draw calls, triangles and frames per second of the last second. */
  stats() { return scene ? scene.info() : null; },

  /** Spin the camera for ms milliseconds and measure frames per second. */
  benchmark(ms = 3000) { return scene ? scene.benchmark(ms) : Promise.resolve(null); },

  /** The renderer, for debugging in the console only (not part of the steering contract). */
  get _scene() { return scene; },

  /** Current view state (for the agent or a test to read back). */
  state() {
    return {
      active: view.active, floor_mode: view.floorMode, focus_floor: view.focusFloor, things: view.things,
      highlights: Object.fromEntries([...view.highlights].map(([k, v]) => [k, v])),
      route: view.routeOverride === undefined ? "page" : view.routeOverride ? "override" : "none",
    };
  },
};

window.view3d = api;

// ---------- view state -> scene ----------

function whenScene(action) {
  if (scene && seen.building) action();
  else view.pending.push(action);
}

function setFocus(floorId, { syncPage = false } = {}) {
  view.focusFloor = floorId;
  const a = pageApp();
  if (syncPage && a?.building && a.floorId !== floorId) {
    a.floorId = floorId;
    seen.floorId = floorId;
    renderFloorTabs();
  }
  pushLayout();
  drawMinimapBase();
}

function pushLayout() {
  if (!scene) return;
  scene.setLayout({ mode: view.floorMode, focus: view.focusFloor, things: view.things });
  pushLabelsDirty();
}

function pushHighlights() {
  if (!scene || !seen.building) return;
  const a = pageApp();
  const highlights = new Map();
  for (const [name, item] of view.highlights) {
    const r = resolveIds(item.ids);
    highlights.set(name, { ...r, points: item.points || [], colour: item.colour });
  }
  // The page's own selections: the room with an open popover, the Find tab's hits.
  const picked = a.pickedSpaceId || a.pendingDoorFrom;
  if (picked) highlights.set("page:picked", { spaceIds: [picked], assetIds: [], openingIds: [], connectorIds: [], points: [], colour: "#2563eb" });
  if (a.highlight) {
    const assetIds = a.highlight.assetIds ? [...a.highlight.assetIds].slice(0, MAX_FIND_HALOS) : [];
    highlights.set("page:find", { spaceIds: [], assetIds, openingIds: [], connectorIds: [], points: [{ floor_id: a.highlight.floor_id, point: a.highlight.point }], colour: DEFAULT_HIGHLIGHT });
  }
  scene.setHighlights(highlights);
}

function currentRoute() {
  const a = pageApp();
  return view.routeOverride === undefined ? a?.state?.route : view.routeOverride;
}

// In the x-ray (stacked) view the floors above the focus are see-through, so a new route is shown from its lowest
// floor: the whole line, including the climb through stairs or lifts, stays visible.
function focusLowestRouteFloor() {
  const a = pageApp();
  const route = currentRoute();
  if (!route?.ok || view.floorMode === "single") return;
  const levels = new Map(a.building.floors.map((f) => [f.id, f.level]));
  const lowest = [...route.floors].sort((x, y) => levels.get(x) - levels.get(y))[0];
  // app.js may have switched the 2D plan to the start floor in the same tick, so check both.
  if (lowest && (lowest !== view.focusFloor || a.floorId !== lowest)) setFocus(lowest, { syncPage: true });
}

function pushRoute() {
  const route = currentRoute();
  const key = routeKey(route);
  if (key === seen.routeKey) return false;
  seen.routeKey = key;
  scene.setRoute(route);
  drawMinimapBase();
  return true;
}

// Called every frame while 3D is shown: pick up what app.js changed (it replaces objects, so identity is enough).
function sync() {
  const a = pageApp();
  if (!scene || !a?.building) return;
  if (a.building !== seen.building) {
    seen.building = a.building;
    seen.state = seen.suspect = null;
    seen.routeKey = "";
    view.focusFloor = a.floorId;
    seen.floorId = a.floorId;
    scene.setBuilding(a.building, view.focusFloor);
    scene.setLayout({ mode: view.floorMode, focus: view.focusFloor, things: view.things });
    scene.fit(true);
    renderTools();
    pushHighlights();
    const pending = view.pending.splice(0);
    pending.forEach((action) => action());
  }
  if (a.state !== seen.state || a.suspect !== seen.suspect) {
    seen.state = a.state;
    seen.suspect = a.suspect;
    scene.setState({
      closed: a.state.closed,
      added: a.state.added_doors,
      suspectSpaces: [...(a.suspect?.spaces || [])],
      suspectOpenings: [...(a.suspect?.openings || [])],
    });
    if (pushRoute()) {
      focusLowestRouteFloor();
      scene.fitRoute();
    }
    drawMinimapBase();
  }
  // app.js started its 2D route animation (new route or the replay button): play it in 3D instead.
  if (a.anim) {
    stopRouteAnimation(false);
    pushRoute();
    scene.playRoute();
  }
  if (a.floorId !== seen.floorId) {
    seen.floorId = a.floorId;
    if (a.floorId !== view.focusFloor) {
      setFocus(a.floorId);
      scene.flyToIds([a.floorId]);
    }
  }
  const picked = a.pickedSpaceId || a.pendingDoorFrom;
  if (a.highlight !== seen.highlight || picked !== seen.picked) {
    const fly = a.highlight && a.highlight !== seen.highlight;
    seen.highlight = a.highlight;
    seen.picked = picked;
    pushHighlights();
    if (fly) scene.flyToPoint(a.highlight.floor_id, a.highlight.point, 14);
  }
}

// ---------- switching 2D / 3D ----------

function ensureScene() {
  if (scene) return true;
  try {
    scene = new Scene3D($("#view3d-stage"), {
      onSpaceClick: (event, id) => onSpaceClick(event, id),
      onOpeningClick: (event, id) => onOpeningClick(event, id),
      onEmptyClick: () => hidePopover(),
      onCaption: (text) => setAnimCaption(text),
    });
  } catch (error) {
    toast(`3D is not available here: ${error.message}`, true);
    return false;
  }
  scene.beforeFrame = sync;
  scene.afterRender = afterRender;
  return true;
}

function setActive(on) {
  if (on && !ensureScene()) on = false;
  view.active = on;
  const pane = $(".map-pane");
  pane.classList.toggle("is-3d", on);
  $("#view3d").hidden = !on;
  document.querySelectorAll(".view-switch button").forEach((b) => b.setAttribute("aria-pressed", String((b.dataset.view === "3d") === on)));
  try { localStorage.setItem("view", on ? "3d" : "2d"); } catch { /* private mode */ }
  const a = pageApp();
  if (on) {
    if (a?.anim) stopRouteAnimation(false);
    scene.start();
    sync();
    scene.requestRender();
  } else {
    scene?.stop();
    scene?.stopRouteAnimation();
    if (a?.building) showFloor(a.floorId, true);
  }
}

// ---------- overlay: room labels, route pins ----------

const labelPool = [];
let lastLabelsAt = 0;

function pushLabelsDirty() {
  if (scene) scene.labelsDirty = true;
}

function afterRender(now) {
  if (now - lastLabelsAt > 50) {
    const labels = scene.layoutLabels();
    if (labels) { lastLabelsAt = now; drawLabels(labels); }
  }
  drawPins();
  drawMinimapCamera();
  if (perfBox) perfBox.textContent = `${scene.stats.fps} fps · ${scene.renderer.info.render.calls} draws · ${Math.round(scene.renderer.info.render.triangles / 1000)}k tris · build ${Math.round(scene.stats.build_ms)} ms`;
}

function drawLabels(labels) {
  const layer = $("#view3d-labels");
  while (labelPool.length < labels.length) {
    const div = document.createElement("div");
    div.className = "label3d";
    layer.appendChild(div);
    labelPool.push(div);
  }
  const a = pageApp();
  labelPool.forEach((div, i) => {
    const item = labels[i];
    if (!item) { div.hidden = true; return; }
    div.hidden = false;
    div.textContent = item.text;
    div.classList.toggle("closed", a.state.closed.includes(item.s.id));
    div.style.transform = `translate(${Math.round(item.x)}px, ${Math.round(item.y)}px) translate(-50%, -50%)`;
  });
}

function drawPins() {
  const layer = $("#view3d-pins");
  const a = pageApp();
  const route = currentRoute();
  const pins = [];
  if (route?.ok) {
    const anchor = (id) => a.spaces.get(id);
    const stops = [[route.start, "start", "A"], ...route.via.map((id, i) => [id, "via", String(i + 1)]), [route.destination, "end", "B"]];
    for (const [id, kind, text] of stops) {
      const s = anchor(id);
      if (s) pins.push({ floor: s.floor_id, point: s.anchor, kind, text, title: s.name });
    }
    for (const c of route.floor_changes) {
      pins.push({ floor: c.from_floor, point: c.from_point, kind: "change", text: c.direction === "up" ? "↑" : "↓", title: `${c.name} to ${a.building.floors.find((f) => f.id === c.to_floor)?.name ?? ""}` });
    }
  }
  const key = JSON.stringify(pins.map((p) => [p.floor, p.point, p.text]));
  if (layer.dataset.key !== key) {
    layer.dataset.key = key;
    layer.innerHTML = pins.map((p) => `<div class="pin3d ${p.kind}" title="${escapeHtml(p.title)}"><span>${escapeHtml(p.text)}</span></div>`).join("");
  }
  [...layer.children].forEach((div, i) => {
    const p = pins[i];
    const at = scene.project(p.floor, p.point, p.kind === "change" ? 2.4 : 1.6);
    div.hidden = !at;
    if (at) div.style.transform = `translate(${Math.round(at[0])}px, ${Math.round(at[1])}px) translate(-50%, -100%)`;
  });
}

const escapeHtml = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- minimap: the focused floor in 2D, with the camera ----------

const minimap = { base: null, transform: null };

function drawMinimapBase() {
  const a = pageApp();
  const canvas = $("#minimap");
  if (!canvas || !a?.building || !view.active) return;
  const floorId = view.focusFloor || a.floorId;
  const box = a.floorBoxes.get(floorId);
  if (!box) return;
  const ratio = window.devicePixelRatio || 1;
  const size = canvas.clientWidth || 150;
  canvas.width = size * ratio;
  canvas.height = size * ratio;
  const base = document.createElement("canvas");
  base.width = canvas.width;
  base.height = canvas.height;
  const ctx = base.getContext("2d");
  // floorBoxes are in SVG units (x, -y)
  const w = box.maxX - box.minX, h = box.maxY - box.minY;
  const pad = 8 * ratio;
  const scale = Math.min((base.width - 2 * pad) / (w || 1), (base.height - 2 * pad) / (h || 1));
  const ox = pad + (base.width - 2 * pad - w * scale) / 2, oy = pad + (base.height - 2 * pad - h * scale) / 2;
  const toPx = ([x, y]) => [ox + (x - box.minX) * scale, oy + (-y - box.minY) * scale];
  minimap.transform = { toPx, toPlan: ([px, py]) => [(px - ox) / scale + box.minX, -((py - oy) / scale + box.minY)], ratio };
  ctx.lineWidth = Math.max(0.5, ratio * 0.6);
  ctx.strokeStyle = "#8b877e";
  for (const s of a.building.spaces) {
    if (s.floor_id !== floorId) continue;
    ctx.beginPath();
    s.polygon.forEach((p, i) => { const [x, y] = toPx(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
    ctx.closePath();
    const closed = a.state.closed.includes(s.id);
    ctx.fillStyle = closed ? "#f8b4b4" : `#${spaceColour(s).toString(16).padStart(6, "0")}`;
    ctx.fill();
    ctx.stroke();
  }
  const route = currentRoute();
  if (route?.ok) {
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 2.5 * ratio;
    ctx.lineJoin = ctx.lineCap = "round";
    for (const segment of route.segments) {
      if (segment.floor_id !== floorId || segment.points.length < 2) continue;
      ctx.beginPath();
      segment.points.forEach((p, i) => { const [x, y] = toPx(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
      ctx.stroke();
    }
  }
  minimap.base = base;
  const floor = a.building.floors.find((f) => f.id === floorId);
  $("#minimap-label").textContent = floor ? floor.name : "";
  minimap.lastCamera = "";
}

function drawMinimapCamera() {
  const canvas = $("#minimap");
  if (!minimap.base || !canvas || canvas.offsetParent === null) return;
  const cam = scene.cameraOnPlan();
  const key = `${cam.target[0].toFixed(1)},${cam.target[1].toFixed(1)},${cam.heading.toFixed(2)},${cam.distance.toFixed(0)}`;
  if (key === minimap.lastCamera) return;
  minimap.lastCamera = key;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(minimap.base, 0, 0);
  const { toPx, ratio } = minimap.transform;
  const [x, y] = toPx(cam.target);
  // view wedge: the camera looks along heading (plan angle), drawn as a soft cone from behind the target
  const reach = 26 * ratio;
  const half = 0.45;
  const back = [x - Math.cos(cam.heading) * reach * 0.6, y + Math.sin(cam.heading) * reach * 0.6];
  ctx.fillStyle = "rgba(37, 99, 235, 0.18)";
  ctx.beginPath();
  ctx.moveTo(back[0], back[1]);
  ctx.lineTo(back[0] + Math.cos(cam.heading - half) * reach * 1.4, back[1] - Math.sin(cam.heading - half) * reach * 1.4);
  ctx.lineTo(back[0] + Math.cos(cam.heading + half) * reach * 1.4, back[1] - Math.sin(cam.heading + half) * reach * 1.4);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = "#1f2328";
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2 * ratio;
  ctx.beginPath();
  ctx.arc(x, y, 4 * ratio, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
}

// ---------- tools ----------

let perfBox = null;

function renderTools() {
  const a = pageApp();
  const multi = (a?.building?.floors.length || 0) > 1;
  $("#view3d-floor-modes").hidden = !multi;
  document.querySelectorAll("[data-floor-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.floorMode === view.floorMode)));
  const things = $("#view3d-things");
  things.textContent = THINGS_LABELS[view.things];
  things.setAttribute("aria-pressed", String(view.things !== "off"));
}

function wire() {
  document.querySelectorAll(".view-switch button").forEach((b) => (b.onclick = () => setActive(b.dataset.view === "3d")));
  document.querySelectorAll("[data-floor-mode]").forEach((b) => (b.onclick = () => api.setFloorMode(b.dataset.floorMode)));
  $("#view3d-things").onclick = () => api.setThings(THINGS_MODES[(THINGS_MODES.indexOf(view.things) + 1) % THINGS_MODES.length]);
  $("#view3d-reset").onclick = () => api.resetView();
  $("#view3d-zoom-in").onclick = () => scene?.zoom(0.7);
  $("#view3d-zoom-out").onclick = () => scene?.zoom(1.4);
  $("#minimap").addEventListener("click", (e) => {
    if (!minimap.transform || !scene) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const r = minimap.transform.ratio;
    scene.panTo(minimap.transform.toPlan([(e.clientX - rect.left) * r, (e.clientY - rect.top) * r]));
  });
  reducedMotion.addEventListener?.("change", () => scene?.requestRender());
  const params = new URLSearchParams(location.search);
  if (params.has("perf")) {
    perfBox = document.createElement("div");
    perfBox.className = "perf3d";
    $("#view3d").appendChild(perfBox);
  }
  renderTools();
  let wanted = params.get("view");
  if (!wanted) { try { wanted = localStorage.getItem("view"); } catch { wanted = null; } }
  if (wanted === "3d") setActive(true);
}

wire();
