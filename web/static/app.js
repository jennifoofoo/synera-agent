// 2D page: floor plan (SVG), route, closures, new doors and chat. Every fact comes from the server (BuildingMap).
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const $ = (selector) => document.querySelector(selector);

const app = {
  building: null,      // building_view from the server
  key: null,
  floorId: null,
  state: { closed: [], added_doors: [], route: null },
  spaces: new Map(),
  openings: new Map(),
  connectors: new Map(),
  connectorBySpace: new Map(),
  floorBoxes: new Map(),
  view: null,          // {x, y, w, h} in SVG units (x, -y)
  highlight: null,     // {floor_id, point, assetIds}
  pendingDoorFrom: null,
  pickedSpaceId: null,
  status: { chat_available: false },
};

// ---------- server ----------

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ building: app.key, ...body }),
  };
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

// ---------- helpers ----------

const esc = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const svgPoint = ([x, y]) => [x, -y];
const floorName = (floorId) => app.building.floors.find((f) => f.id === floorId)?.name ?? floorId;
const spaceName = (spaceId) => app.spaces.get(spaceId)?.name ?? spaceId;
const isClosed = (id) => app.state.closed.includes(id);
// Server texts carry ids in [brackets] for the agent; people only need the names.
const clean = (text) =>
  String(text ?? "")
    .replace(/ \[[^\]]+\]/g, "")
    .replace(/ with the current closures \[\]/, "")
    .replace("Try search_building with fewer words.", "Try fewer words or the Find tab.")
    .replace(/Use one of these ids: (.*)$/, (_, list) => "Did you mean: " + [...list.matchAll(/\(([^)]+)\)/g)].map((m) => m[1]).join(", ") + "?");

function el(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(name, value);
  }
  if (parent) parent.appendChild(node);
  return node;
}

function toast(text, bad = false) {
  const box = $("#toast");
  box.textContent = clean(text);
  box.className = "toast" + (bad ? " bad" : "");
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (box.hidden = true), 5000);
}

function pixelSize() {
  const svg = $("#map");
  return app.view ? app.view.w / Math.max(svg.clientWidth, 1) : 0.05;
}

// ---------- loading ----------

async function init() {
  wireUi();
  app.status = await api("/api/status").catch(() => ({ chat_available: false }));
  const { buildings } = await api("/api/buildings");
  const select = $("#building-select");
  const groups = new Map();
  for (const b of buildings) {
    if (!groups.has(b.split)) groups.set(b.split, []);
    groups.get(b.split).push(b);
  }
  for (const [split, items] of groups) {
    const group = document.createElement("optgroup");
    group.label = split || "buildings";
    for (const b of items) {
      const option = document.createElement("option");
      option.value = b.key;
      const floors = b.floors ? ` · ${b.floors} floor${b.floors > 1 ? "s" : ""}` : "";
      option.textContent = `${b.name} (${b.key.split("/").pop()})${floors}`;
      group.appendChild(option);
    }
    select.appendChild(group);
  }
  const fromHash = decodeURIComponent((location.hash.match(/b=([^&]+)/) || [])[1] || "");
  const initial = buildings.find((b) => b.key === fromHash) || buildings.find((b) => b.key.includes("campus")) || buildings[0];
  if (initial) {
    select.value = initial.key;
    await loadBuilding(initial.key);
  }
  updateChatNote();
}

async function loadBuilding(key, reset = false) {
  app.key = key;
  history.replaceState(null, "", `#b=${encodeURIComponent(key)}`);
  $("#building-meta").textContent = "loading…";
  $("#map").innerHTML = `<text x="0" y="0" font-size="1" text-anchor="middle" fill="#6b6f76">Loading building…</text>`;
  $("#map").setAttribute("viewBox", "-10 -6 20 12");
  const data = reset ? await api("/api/reset", {}) : await api(`/api/building?key=${encodeURIComponent(key)}`);
  app.building = data;
  app.spaces = new Map(data.spaces.map((s) => [s.id, s]));
  app.openings = new Map(data.openings.map((o) => [o.id, o]));
  app.connectors = new Map(data.connectors.map((c) => [c.id, c]));
  app.connectorBySpace = new Map();
  for (const c of data.connectors) for (const sid of c.space_ids) app.connectorBySpace.set(sid, c);
  app.floorBoxes = new Map();
  for (const s of data.spaces) {
    const box = app.floorBoxes.get(s.floor_id) || { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    for (const [x, y] of s.polygon) {
      box.minX = Math.min(box.minX, x); box.maxX = Math.max(box.maxX, x);
      box.minY = Math.min(box.minY, -y); box.maxY = Math.max(box.maxY, -y);
    }
    app.floorBoxes.set(s.floor_id, box);
  }
  app.highlight = null;
  app.pendingDoorFrom = null;
  app.pickedSpaceId = null;
  hidePopover();
  setBanner(null);
  const nRooms = data.spaces.filter((s) => s.type === "room" || s.type === "hall").length;
  $("#building-meta").textContent = `${data.floors.length} floor${data.floors.length > 1 ? "s" : ""} · ${nRooms} rooms · ${data.assets.length} things · ${data.source}`;
  const ground = data.floors.find((f) => f.level === 0) || data.floors[0];
  app.floorId = ground.id;
  applyState(data.state, { silent: true });
  showFloor(app.floorId, true);
  $("#chat-log").innerHTML = "";
  addMessage("system", `Building: ${data.name}. Ask where things are, how to get somewhere, or tell me what is closed.`);
}

// What the person typed -> what the server resolves: exact unique name -> id, otherwise the raw text.
function placeRef(text) {
  const value = text.trim();
  const matches = app.building.spaces.filter((s) => s.name === value);
  return matches.length === 1 ? matches[0].id : value;
}

// ---------- drawing ----------

function showFloor(floorId, fit = false) {
  app.floorId = floorId;
  renderFloorTabs();
  if (fit || !app.view) fitView();
  render();
}

function renderFloorTabs() {
  const tabs = $("#floor-tabs");
  tabs.innerHTML = "";
  const routeFloors = new Set(app.state.route?.ok ? app.state.route.floors : []);
  const floors = [...app.building.floors].sort((a, b) => b.level - a.level);
  if (floors.length === 1) return;
  for (const floor of floors) {
    const button = document.createElement("button");
    button.role = "tab";
    button.innerHTML = `${floor.level}<span class="name">${esc(floor.name)}</span>`;
    button.title = floor.name;
    if (floor.id === app.floorId) button.classList.add("active");
    if (routeFloors.has(floor.id)) button.classList.add("on-route");
    button.onclick = () => showFloor(floor.id, true);
    tabs.appendChild(button);
  }
}

function fitView(box = app.floorBoxes.get(app.floorId)) {
  if (!box) return;
  const svg = $("#map");
  const pad = Math.max(box.maxX - box.minX, box.maxY - box.minY) * 0.06 + 1;
  let w = box.maxX - box.minX + 2 * pad;
  let h = box.maxY - box.minY + 2 * pad;
  const aspect = svg.clientWidth / Math.max(svg.clientHeight, 1) || 1;
  if (w / h < aspect) w = h * aspect; else h = w / aspect;
  const cx = (box.minX + box.maxX) / 2, cy = (box.minY + box.maxY) / 2;
  app.view = { x: cx - w / 2, y: cy - h / 2, w, h };
  // Keep the top strip free for the route bar.
  const reserve = $("#route-bar").hidden ? 0 : 56 * (h / Math.max(svg.clientHeight, 1));
  app.view.y -= reserve;
  app.view.h += reserve;
  app.view.w = app.view.h * aspect;
  app.view.x = cx - app.view.w / 2;
  applyView();
}

function applyView() {
  const v = app.view;
  $("#map").setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
}

function render() {
  const svg = $("#map");
  svg.innerHTML = "";
  const defs = el("defs", {}, svg);
  const hatch = el("pattern", { id: "hatch-closed", width: 0.8, height: 0.8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
  el("rect", { width: 0.8, height: 0.8, fill: "#fde2e2" }, hatch);
  el("rect", { width: 0.25, height: 0.8, fill: "#ef4444" }, hatch);

  const route = app.state.route?.ok ? app.state.route : null;
  const onRoute = new Set(route ? route.space_path : []);
  const floorId = app.floorId;
  const spacesLayer = el("g", {}, svg);
  const labelLayer = el("g", {}, svg);
  const assetLayer = el("g", {}, svg);
  const openingLayer = el("g", {}, svg);
  const routeLayer = el("g", {}, svg);
  const markerLayer = el("g", { id: "markers" }, svg);

  for (const s of app.building.spaces) {
    if (s.floor_id !== floorId) continue;
    const connector = app.connectorBySpace.get(s.id);
    const closed = isClosed(s.id) || (connector && isClosed(connector.id));
    const classes = ["space", s.type];
    if (onRoute.has(s.id)) classes.push("on-route");
    if (route && s.id === route.start) classes.push("start");
    if (route && s.id === route.destination) classes.push("end");
    if (closed) classes.push("closed");
    if (s.id === app.pickedSpaceId || s.id === app.pendingDoorFrom) classes.push("picked");
    const points = s.polygon.map((p) => svgPoint(p).join(",")).join(" ");
    const shape = el("polygon", { points, class: classes.join(" "), "data-space": s.id }, spacesLayer);
    const title = el("title", {}, shape);
    title.textContent = `${s.name} · ${floorName(s.floor_id)}${closed ? " · CLOSED" : ""}`;
    drawLabel(labelLayer, s, closed);
  }

  for (const a of app.building.assets) {
    if (a.floor_id !== floorId) continue;
    const [x, y] = svgPoint(a.position);
    const hit = app.highlight?.assetIds?.has(a.id);
    el("circle", { cx: x, cy: y, r: hit ? 0.45 : 0.22, class: `asset ${a.category || ""}${hit ? " hit" : ""}` }, assetLayer);
  }

  for (const o of app.building.openings) {
    if (o.floor_id !== floorId) continue;
    drawOpening(openingLayer, o);
  }

  if (route) drawRoute(routeLayer, route);
  drawMarkers(markerLayer);
}

function drawLabel(layer, s, closed) {
  if (s.type === "corridor" && !s.ref) return;
  const xs = s.polygon.map((p) => p[0]), ys = s.polygon.map((p) => p[1]);
  const width = Math.max(...xs) - Math.min(...xs), height = Math.max(...ys) - Math.min(...ys);
  const maxSize = Math.max(0.35, Math.min(1.6, Math.min(width, height) / 5));
  const fits = (text) => Math.min(maxSize, (width * 0.9) / (text.length * 0.58));
  // Full name when it fits at a readable size, otherwise the room number.
  const generic = /^(Corridor|Generic room|Room)\b/.test(s.name);
  let text = s.name, size = fits(s.name);
  if (generic || size < 0.45) {
    text = s.ref || s.name;
    size = fits(text);
    if (size < 0.25) return;
  }
  const [x, y] = svgPoint(s.anchor);
  const label = el("text", { x, y, "font-size": size, class: "label" + (closed ? " closed" : "") }, layer);
  label.textContent = closed ? `✕ ${text}` : text;
}

function drawOpening(layer, o) {
  const [x, y] = svgPoint(o.position);
  const r = Math.max(0.3, Math.min(0.6, (o.width_m || 0.9) / 2));
  const g = el("g", { class: "opening", "data-opening": o.id }, layer);
  el("circle", { cx: x, cy: y, r: r * 2.2, class: "hit" }, g);
  const kindClass = o.kind === "entrance" ? "entrance" : o.kind === "opening" ? "opening-kind" : "";
  const classes = ["door", kindClass, o.step_free ? "" : "step", o.added ? "added" : ""].join(" ");
  if (o.kind === "entrance") {
    el("rect", { x: x - r, y: y - r, width: 2 * r, height: 2 * r, rx: 0.12, class: classes }, g);
  } else {
    el("circle", { cx: x, cy: y, r: o.added ? r * 1.1 : r * 0.6, class: classes }, g);
  }
  if (o.added) el("circle", { cx: x, cy: y, r: r * 1.4, class: "ring" }, g);
  if (isClosed(o.id)) {
    const d = r * 1.3;
    el("path", { d: `M${x - d},${y - d}L${x + d},${y + d}M${x - d},${y + d}L${x + d},${y - d}`, class: "x" }, g);
  }
  const title = el("title", {}, g);
  const sides = o.space_ids.map((id) => (id === "outside" ? "outside" : spaceName(id))).join(" ↔ ");
  title.textContent = `${o.added ? "New door" : o.kind}: ${sides}${o.step_free ? "" : " (step)"}${isClosed(o.id) ? " · CLOSED" : ""}`;
}

function drawRoute(layer, route) {
  for (const segment of route.segments) {
    if (segment.floor_id !== app.floorId || segment.points.length < 2) continue;
    const points = segment.points.map((p) => svgPoint(p).join(",")).join(" ");
    el("polyline", { points, class: "route-casing" }, layer);
    el("polyline", { points, class: "route-line" + (segment.kind === "outside" ? " outside" : "") }, layer);
    if (segment.kind !== "outside") el("polyline", { points, class: "route-flow" }, layer);
  }
}

// Markers keep a fixed screen size, so they are redrawn on zoom.
function drawMarkers(layer = $("#markers")) {
  if (!layer) return;
  layer.innerHTML = "";
  const px = pixelSize();
  const route = app.state.route?.ok ? app.state.route : null;

  for (const c of app.building.connectors) {
    const index = c.floor_ids.indexOf(app.floorId);
    if (index < 0) continue;
    const s = app.spaces.get(c.space_ids[index]);
    if (!s) continue;
    const [x, y] = svgPoint(s.anchor);
    const g = el("g", { class: `conn-badge ${c.kind}${isClosed(c.id) ? " closed" : ""}` }, layer);
    el("circle", { cx: x, cy: y - 14 * px, r: 8 * px }, g);
    const t = el("text", { x, y: y - 14 * px, "font-size": 10 * px }, g);
    t.textContent = c.kind === "lift" ? "L" : "S";
  }

  if (route) {
    for (const change of route.floor_changes) {
      const here = change.from_floor === app.floorId ? "from" : change.to_floor === app.floorId ? "to" : null;
      if (!here) continue;
      const target = here === "from" ? change.to_floor : change.from_floor;
      const [x, y] = svgPoint(here === "from" ? change.from_point : change.to_point);
      const g = el("g", { class: "marker change", "data-floor": target }, layer);
      el("circle", { cx: x, cy: y, r: 11 * px }, g);
      const arrowUp = change.direction === "up";
      const t = el("text", { x, y, "font-size": 13 * px }, g);
      t.textContent = arrowUp ? "↑" : "↓";
      const tag = el("text", { x: x + 15 * px, y, "font-size": 12 * px, class: "tag" }, g);
      tag.textContent = here === "from" ? `${change.name} to ${floorName(target)}` : `from ${floorName(target)} (${change.name})`;
    }
    const stopMarkers = [
      [route.start, "start", "A"],
      ...route.via.map((id, i) => [id, "via", String(i + 1)]),
      [route.destination, "end", "B"],
    ];
    for (const [id, kind, text] of stopMarkers) {
      const s = app.spaces.get(id);
      if (!s || s.floor_id !== app.floorId) continue;
      const [x, y] = svgPoint(s.anchor);
      const g = el("g", { class: `marker ${kind}` }, layer);
      el("circle", { cx: x, cy: y, r: 12 * px }, g);
      const t = el("text", { x, y, "font-size": 13 * px }, g);
      t.textContent = text;
    }
  }

  if (app.highlight && app.highlight.floor_id === app.floorId && app.highlight.point) {
    const [x, y] = svgPoint(app.highlight.point);
    el("circle", { cx: x, cy: y, r: 14 * px, class: "pulse" }, layer);
  }
}

// ---------- state from server ----------

function applyState(state, { silent = false, cause = "" } = {}) {
  const before = app.state.route;
  app.state = state;
  // Mirror closures/new doors into the building copy used for drawing.
  for (const door of state.added_doors) {
    if (!app.openings.has(door.id)) {
      const opening = { ...door, kind: "door", width_m: 0.9, added: true };
      app.building.openings.push(opening);
      app.openings.set(door.id, opening);
    }
  }
  const route = state.route;
  if (route?.ok && (!before || !before.ok || before.start !== route.start || before.destination !== route.destination || silent)) {
    if (!route.floors.includes(app.floorId)) app.floorId = route.floors[0];
  }
  if (!silent && before && route) explainRouteChange(before, route, cause);
  renderFloorTabs();
  render();
  renderRouteBar();
  renderRoutePanel();
  renderChanges();
}

function explainRouteChange(before, after, cause) {
  if (!cause) return;
  if (before.ok && !after.ok) return toast(`${cause}. There is no route any more: ${after.error}`, true);
  if (!before.ok && after.ok) return toast(`${cause}. A route exists again: ${after.length_m} m.`);
  if (!before.ok || !after.ok) return;
  const diff = Math.round((after.length_m - before.length_m) * 10) / 10;
  const viaBefore = before.floor_changes.map((c) => c.name).join(", ");
  const viaAfter = after.floor_changes.map((c) => c.name).join(", ");
  if (diff === 0 && viaBefore === viaAfter) return toast(`${cause}. Your route is not affected.`);
  const via = viaAfter && viaAfter !== viaBefore ? `, now via ${viaAfter}` : "";
  const delta = diff > 0 ? `${diff} m longer` : diff < 0 ? `${-diff} m shorter` : "same length";
  toast(`${cause}. Route recomputed: ${after.length_m} m (${delta})${via}.`);
}

function stateSignature(state) {
  const r = state.route;
  return JSON.stringify([state.closed, state.added_doors.map((d) => d.id), r && [r.ok, r.start, r.destination, r.length_m]]);
}

function renderRouteBar() {
  const bar = $("#route-bar");
  const route = app.state.route;
  if (!route) { bar.hidden = true; return; }
  bar.hidden = false;
  if (!route.ok) {
    bar.className = "route-bar error";
    bar.textContent = clean(route.error);
    return;
  }
  bar.className = "route-bar";
  const via = route.floor_changes.length ? ` · via ${[...new Set(route.floor_changes.map((c) => c.name))].join(", ")}` : "";
  bar.innerHTML = `<span class="dot start"></span><b>${esc(spaceName(route.start))}</b> → <span class="dot end"></span><b>${esc(spaceName(route.destination))}</b> · ${route.length_m} m${route.step_free ? " · step-free" : ""}${esc(via)}`;
}

function renderRoutePanel() {
  const box = $("#route-result");
  const route = app.state.route;
  if (!route) { box.innerHTML = ""; return; }
  if (!route.ok) { box.innerHTML = `<div class="summary error">${esc(clean(route.error))}</div>`; return; }
  const steps = route.steps.map((step) => {
    const change = /^(Take|Use) /.test(step);
    return `<li class="${change ? "floor-change" : ""}">${esc(clean(step))}</li>`;
  }).join("");
  box.innerHTML = `<div class="summary"><div class="big">${route.length_m} m</div>
    ${esc(spaceName(route.start))} → ${esc(spaceName(route.destination))}${route.step_free ? " · step-free" : ""}
    <ol class="steps">${steps}</ol></div>`;
  $("#route-from").value ||= spaceName(route.start);
  $("#route-to").value ||= spaceName(route.destination);
}

function renderChanges() {
  const connectors = $("#connector-list");
  connectors.innerHTML = app.building.connectors.length ? "" : '<div class="empty">This building has no stairs or lifts.</div>';
  for (const c of app.building.connectors) {
    const closed = isClosed(c.id);
    const row = document.createElement("div");
    row.className = "item" + (closed ? " closed" : "");
    const floors = c.floor_ids.map((id) => app.building.floors.find((f) => f.id === id)?.level).join(", ");
    row.innerHTML = `<div>${esc(c.name)} <div class="kind">${c.kind}${c.step_free ? " · step-free" : ""} · floors ${floors}</div></div>`;
    const button = document.createElement("button");
    button.className = "small " + (closed ? "ok" : "danger");
    button.textContent = closed ? "Reopen" : "Close";
    button.onclick = () => setClosed(c.id, !closed);
    row.appendChild(button);
    connectors.appendChild(row);
  }
  const closedList = $("#closed-list");
  closedList.innerHTML = app.state.closed.length ? "" : '<div class="empty">Nothing closed.</div>';
  for (const id of app.state.closed) {
    const row = document.createElement("div");
    row.className = "item closed";
    row.innerHTML = `<div>${esc(describeElement(id))}</div>`;
    const button = document.createElement("button");
    button.className = "small ok";
    button.textContent = "Reopen";
    button.onclick = () => setClosed(id, false);
    row.appendChild(button);
    closedList.appendChild(row);
  }
  const doorList = $("#door-list");
  doorList.innerHTML = app.state.added_doors.length ? "" : '<div class="empty">No new doors.</div>';
  for (const door of app.state.added_doors) {
    const row = document.createElement("div");
    row.className = "item";
    row.innerHTML = `<div>${esc(door.space_ids.map(spaceName).join(" ↔ "))}<div class="kind">${esc(floorName(door.floor_id))}</div></div>`;
    row.onclick = () => focusPoint(door.floor_id, door.position);
    doorList.appendChild(row);
  }
  const count = app.state.closed.length + app.state.added_doors.length;
  $("#changes-count").hidden = count === 0;
  $("#changes-count").textContent = count;
}

function describeElement(id) {
  if (app.connectors.has(id)) return `${app.connectors.get(id).name} (${app.connectors.get(id).kind})`;
  if (app.spaces.has(id)) return `${spaceName(id)} · ${floorName(app.spaces.get(id).floor_id)}`;
  if (app.openings.has(id)) {
    const o = app.openings.get(id);
    return `Door ${o.space_ids.map((s) => (s === "outside" ? "outside" : spaceName(s))).join(" ↔ ")}`;
  }
  return id;
}

// ---------- actions ----------

async function requestRoute(start, destination, { stepFree = $("#route-stepfree").checked, via = [] } = {}) {
  try {
    const result = await api("/api/route", { start, destination, step_free: stepFree, via });
    app.state.route = null;
    applyState(result.state, { silent: true });
    if (result.route.ok) {
      app.floorId = result.route.floors[0];
      showFloor(app.floorId, true);
    } else {
      toast(result.route.error, true);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

async function setClosed(element, closed) {
  try {
    const result = await api("/api/close", { element, closed });
    applyState(result.state, { cause: `${describeElement(result.element)} ${closed ? "closed" : "reopened"}` });
    if (!app.state.route) toast(`${describeElement(result.element)} ${closed ? "closed" : "reopened"}.`);
  } catch (error) {
    toast(error.message, true);
  }
}

async function addDoor(first, second) {
  try {
    const result = await api("/api/door", { first, second, step_free: true });
    applyState(result.state, { cause: `New door between ${spaceName(first)} and ${spaceName(second)}` });
    if (!app.state.route) toast(`New door between ${spaceName(first)} and ${spaceName(second)}.`);
  } catch (error) {
    toast(error.message, true);
  }
}

function focusPoint(floorId, point, assetIds = null) {
  app.highlight = { floor_id: floorId, point, assetIds };
  app.floorId = floorId;
  renderFloorTabs();
  const [x, y] = svgPoint(point);
  const box = app.floorBoxes.get(floorId);
  const span = Math.max(25, Math.min(60, (box.maxX - box.minX) / 2.5));
  const svg = $("#map");
  const aspect = svg.clientWidth / Math.max(svg.clientHeight, 1) || 1;
  app.view = { x: x - span / 2, y: y - span / aspect / 2, w: span, h: span / aspect };
  applyView();
  render();
}

// ---------- popover on the plan ----------

function hidePopover() {
  $("#popover").hidden = true;
  if (app.pickedSpaceId) {
    app.pickedSpaceId = null;
    render();
  }
}

function showPopover(event, html, actions) {
  const pop = $("#popover");
  pop.innerHTML = `<button class="close-x" aria-label="Close">×</button>${html}<div class="actions"></div>`;
  const row = pop.querySelector(".actions");
  for (const [label, cls, handler] of actions) {
    const b = document.createElement("button");
    b.className = "small " + cls;
    b.textContent = label;
    b.onclick = (e) => { e.stopPropagation(); pop.hidden = true; app.pickedSpaceId = null; handler(); render(); };
    row.appendChild(b);
  }
  pop.querySelector(".close-x").onclick = hidePopover;
  pop.hidden = false;
  const pane = $(".map-pane").getBoundingClientRect();
  const left = Math.min(event.clientX - pane.left + 10, pane.width - pop.offsetWidth - 10);
  const top = Math.min(event.clientY - pane.top + 10, pane.height - pop.offsetHeight - 10);
  pop.style.left = Math.max(10, left) + "px";
  pop.style.top = Math.max(10, top) + "px";
}

function onSpaceClick(event, spaceId) {
  const s = app.spaces.get(spaceId);
  if (app.pendingDoorFrom) {
    const first = app.pendingDoorFrom;
    app.pendingDoorFrom = null;
    setBanner(null);
    if (first !== spaceId) addDoor(first, spaceId); else render();
    return;
  }
  app.pickedSpaceId = spaceId;
  render();
  const connector = app.connectorBySpace.get(spaceId);
  const things = app.building.assets.filter((a) => a.space_id === spaceId);
  const thingText = things.length ? ` · ${things.length} thing${things.length > 1 ? "s" : ""}` : "";
  const closed = isClosed(spaceId);
  const actions = [
    ["Start here", "", () => setEndpoint("from", spaceId)],
    ["Go here", "", () => setEndpoint("to", spaceId)],
  ];
  if (app.state.route?.ok) actions.push(["Add as stop", "secondary", () => addVia(spaceId)]);
  if (connector) {
    const cClosed = isClosed(connector.id);
    actions.push([`${cClosed ? "Reopen" : "Close"} ${connector.name}`, cClosed ? "ok" : "danger", () => setClosed(connector.id, !cClosed)]);
  } else {
    actions.push([closed ? "Reopen room" : "Close room", closed ? "ok" : "danger", () => setClosed(spaceId, !closed)]);
  }
  actions.push(["Add door to…", "secondary", () => {
    app.pendingDoorFrom = spaceId;
    render();
    setBanner(`New door from ${s.name}: tap the neighbouring room.`);
  }]);
  const sample = things.slice(0, 4).map((a) => esc(a.name)).join(", ");
  showPopover(event, `<h4>${esc(s.name)}</h4><div class="sub">${esc(s.room_type.replaceAll("_", " "))} · ${esc(floorName(s.floor_id))} · ${s.area_m2} m²${thingText}${closed ? " · <b style='color:var(--closed)'>closed</b>" : ""}${sample ? `<br>${sample}${things.length > 4 ? ", …" : ""}` : ""}</div>`, actions);
}

function onOpeningClick(event, openingId) {
  const o = app.openings.get(openingId);
  const closed = isClosed(openingId);
  const sides = o.space_ids.map((id) => (id === "outside" ? "outside" : esc(spaceName(id)))).join(" ↔ ");
  const kind = o.added ? "New door" : o.kind[0].toUpperCase() + o.kind.slice(1);
  showPopover(event, `<h4>${kind}</h4><div class="sub">${sides}<br>${o.width_m ? o.width_m + " m wide · " : ""}${o.step_free ? "step-free" : "has a step"}${closed ? " · <b style='color:var(--closed)'>closed</b>" : ""}</div>`, [
    [closed ? "Reopen" : "Close", closed ? "ok" : "danger", () => setClosed(openingId, !closed)],
  ]);
}

function setBanner(text) {
  const banner = $("#mode-banner");
  if (!text) { banner.hidden = true; return; }
  banner.innerHTML = `${esc(text)} <button class="small secondary">Cancel</button>`;
  banner.querySelector("button").onclick = () => { app.pendingDoorFrom = null; setBanner(null); render(); };
  banner.hidden = false;
}

function setEndpoint(which, spaceId) {
  const input = which === "from" ? $("#route-from") : $("#route-to");
  input.value = spaceName(spaceId);
  input.dataset.id = spaceId;
  const from = $("#route-from"), to = $("#route-to");
  if (from.value && to.value) submitRoute();
  else {
    switchTab("route");
    toast(which === "from" ? "Start set. Now tap the destination." : "Destination set. Now tap where you start.");
  }
}

function inputRef(input) {
  const id = input.dataset.id;
  if (id && app.spaces.get(id)?.name === input.value) return id;
  return placeRef(input.value);
}

function addVia(spaceId) {
  const row = addViaRow();
  row.querySelector("input").value = spaceName(spaceId);
  row.querySelector("input").dataset.id = spaceId;
  submitRoute();
}

function addViaRow() {
  const row = document.createElement("div");
  row.className = "via-row";
  row.innerHTML = `<label>Stop <input class="place" autocomplete="off" placeholder="Room on the way"></label><button type="button" class="link">✕</button>`;
  row.querySelector("button").onclick = () => { row.remove(); };
  $("#via-list").appendChild(row);
  attachSuggest(row.querySelector("input"));
  return row;
}

function submitRoute() {
  const from = $("#route-from"), to = $("#route-to");
  if (!from.value.trim() || !to.value.trim()) return toast("Set a start and a destination.", true);
  const via = [...document.querySelectorAll("#via-list input")].filter((i) => i.value.trim()).map(inputRef);
  requestRoute(inputRef(from), inputRef(to), { via });
}

// ---------- place suggestions (own list: the native <datalist> popup is misplaced in embedded browsers) ----------

const suggest = { input: null, items: [], index: -1 };

function placeMatches(text) {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const hits = app.building.spaces.filter((s) => {
    const hay = `${s.name} ${s.ref || ""} ${s.room_type.replaceAll("_", " ")}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
  const first = words[0];
  hits.sort((a, b) => (b.name.toLowerCase().startsWith(first) - a.name.toLowerCase().startsWith(first)) || a.name.localeCompare(b.name));
  return hits.slice(0, 8);
}

function showSuggest(input) {
  const box = $("#suggest");
  suggest.input = input;
  suggest.items = placeMatches(input.value);
  suggest.index = -1;
  if (!suggest.items.length || (suggest.items.length === 1 && suggest.items[0].name === input.value)) {
    box.hidden = true;
    return;
  }
  box.innerHTML = suggest.items
    .map((s, i) => `<div class="suggest-item" data-i="${i}"><span>${esc(s.name)}</span><span class="kind">${esc(floorName(s.floor_id))}</span></div>`)
    .join("");
  const panel = input.closest(".panel").getBoundingClientRect();
  const rect = input.getBoundingClientRect();
  box.style.left = rect.left - panel.left + "px";
  box.style.top = rect.bottom - panel.top + input.closest(".panel").scrollTop + 2 + "px";
  box.style.width = rect.width + "px";
  box.hidden = false;
}

function pickSuggest(i) {
  const space = suggest.items[i];
  if (!space || !suggest.input) return;
  suggest.input.value = space.name;
  suggest.input.dataset.id = space.id;
  $("#suggest").hidden = true;
}

function attachSuggest(input) {
  input.addEventListener("input", () => { delete input.dataset.id; showSuggest(input); });
  input.addEventListener("focus", () => input.value && showSuggest(input));
  input.addEventListener("blur", () => setTimeout(() => ($("#suggest").hidden = true), 150));
  input.addEventListener("keydown", (e) => {
    const box = $("#suggest");
    if (box.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = suggest.items.length;
      suggest.index = (suggest.index + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      box.querySelectorAll(".suggest-item").forEach((el, i) => el.classList.toggle("active", i === suggest.index));
    } else if (e.key === "Enter" && suggest.index >= 0) {
      e.preventDefault();
      pickSuggest(suggest.index);
    } else if (e.key === "Escape") {
      box.hidden = true;
    }
  });
}

// ---------- find ----------

function runFind() {
  const words = $("#find-input").value.toLowerCase().replaceAll("_", " ").split(/\s+/).filter(Boolean);
  const box = $("#find-results");
  box.innerHTML = "";
  if (!words.length) return;
  const matchText = (text) => words.every((w) => text.toLowerCase().replaceAll("_", " ").includes(w));
  const spaces = app.building.spaces.filter((s) => matchText(`${s.name} ${s.ref || ""} ${s.room_type}`));
  const assets = app.building.assets.filter((a) => matchText(`${a.name} ${a.type}`));
  if (!spaces.length && !assets.length) { box.innerHTML = '<div class="empty">Nothing matches. Try fewer or shorter words.</div>'; return; }
  const assetIds = new Set(assets.map((a) => a.id));
  for (const s of spaces.slice(0, 30)) {
    box.appendChild(resultRow(s.name, `room · ${floorName(s.floor_id)}`, () => { app.pickedSpaceId = s.id; focusPoint(s.floor_id, s.anchor, assetIds); }, s.id));
  }
  for (const a of assets.slice(0, 60)) {
    box.appendChild(resultRow(a.name, `${a.type.replaceAll("_", " ")} · in ${spaceName(a.space_id)} · ${floorName(a.floor_id)}`, () => focusPoint(a.floor_id, a.position, assetIds), a.space_id));
  }
  const more = spaces.length - 30 + assets.length - 60;
  if (more > 0) box.insertAdjacentHTML("beforeend", `<div class="empty">${more} more, add a word to narrow down.</div>`);
}

function resultRow(title, kind, onClick, spaceId) {
  const row = document.createElement("div");
  row.className = "result";
  row.innerHTML = `<div>${esc(title)}<div class="kind">${esc(kind)}</div></div>`;
  const go = document.createElement("button");
  go.className = "small secondary";
  go.textContent = "Go here";
  go.onclick = (e) => { e.stopPropagation(); setEndpoint("to", spaceId); };
  row.appendChild(go);
  row.onclick = onClick;
  return row;
}

// ---------- chat ----------

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  $("#chat-log").appendChild(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
  return div;
}

function updateChatNote() {
  const note = $("#chat-note");
  if (!app.status.chat_available) {
    note.textContent = "Chat is off: no ANTHROPIC_API_KEY on the server. The map, routes and closures still work.";
  } else {
    note.textContent = `Agent: ${app.status.chat_backend}. Changes the agent makes show up on the plan.`;
  }
}

async function sendChat(text) {
  addMessage("user", text);
  const pending = addMessage("agent pending", "thinking…");
  try {
    const result = await api("/api/chat", { message: text });
    pending.remove();
    addMessage(result.error ? "system" : "agent", result.reply);
    if (result.state) {
      const changed = stateSignature(result.state) !== stateSignature(app.state);
      applyState(result.state, changed ? { cause: "Updated from the chat" } : { silent: true });
    }
    const route = app.state.route;
    if (route?.ok && !route.floors.includes(app.floorId)) showFloor(route.floors[0], true);
  } catch (error) {
    pending.remove();
    addMessage("system", `Chat failed: ${error.message}`);
  }
}

// ---------- pan / zoom / click ----------

function wireMap() {
  const svg = $("#map");
  const pointers = new Map();
  let drag = null;

  const toSvg = (clientX, clientY) => {
    const rect = svg.getBoundingClientRect();
    return [app.view.x + ((clientX - rect.left) / rect.width) * app.view.w, app.view.y + ((clientY - rect.top) / rect.height) * app.view.h];
  };
  const zoomAt = (factor, clientX, clientY) => {
    const [px, py] = toSvg(clientX, clientY);
    const v = app.view;
    const w = Math.max(3, Math.min(5000, v.w * factor));
    const k = w / v.w;
    app.view = { x: px - (px - v.x) * k, y: py - (py - v.y) * k, w, h: v.h * k };
    applyView();
    drawMarkers();
  };

  svg.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(Math.exp(e.deltaY * 0.0015), e.clientX, e.clientY); }, { passive: false });
  svg.addEventListener("pointerdown", (e) => {
    pointers.set(e.pointerId, [e.clientX, e.clientY]);
    svg.setPointerCapture(e.pointerId);
    drag = { x: e.clientX, y: e.clientY, view: { ...app.view }, moved: false, target: e.target, pinch: null };
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      drag.pinch = Math.hypot(a[0] - b[0], a[1] - b[1]);
    }
  });
  svg.addEventListener("pointermove", (e) => {
    if (!drag || !pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (pointers.size === 2 && drag.pinch) {
      const [a, b] = [...pointers.values()];
      const distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
      zoomAt(drag.pinch / distance, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      drag.pinch = distance;
      drag.moved = true;
      return;
    }
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    drag.moved = true;
    svg.classList.add("dragging");
    const rect = svg.getBoundingClientRect();
    app.view = { ...app.view, x: drag.view.x - (dx / rect.width) * drag.view.w, y: drag.view.y - (dy / rect.height) * drag.view.h };
    applyView();
  });
  const end = (e) => {
    pointers.delete(e.pointerId);
    svg.classList.remove("dragging");
    if (!drag) return;
    const wasClick = !drag.moved && pointers.size === 0;
    const target = drag.target;
    if (pointers.size === 0) drag = null;
    if (!wasClick) return;
    const floorJump = target.closest?.("[data-floor]");
    const opening = target.closest?.("[data-opening]");
    const space = target.closest?.("[data-space]");
    if (floorJump) showFloor(floorJump.dataset.floor, true);
    else if (opening) onOpeningClick(e, opening.dataset.opening);
    else if (space) onSpaceClick(e, space.dataset.space);
    else hidePopover();
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);

  $("#zoom-in").onclick = () => { const r = svg.getBoundingClientRect(); zoomAt(0.7, r.left + r.width / 2, r.top + r.height / 2); };
  $("#zoom-out").onclick = () => { const r = svg.getBoundingClientRect(); zoomAt(1.4, r.left + r.width / 2, r.top + r.height / 2); };
  $("#zoom-fit").onclick = () => { fitView(); drawMarkers(); };
  window.addEventListener("resize", () => { fitView(); drawMarkers(); });
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
}

function wireUi() {
  wireMap();
  document.querySelectorAll(".tab").forEach((tab) => (tab.onclick = () => switchTab(tab.dataset.tab)));
  $("#building-select").onchange = (e) => loadBuilding(e.target.value);
  $("#route-form").onsubmit = (e) => { e.preventDefault(); submitRoute(); };
  $("#route-stepfree").onchange = () => { if (app.state.route) submitRoute(); };
  $("#add-via").onclick = () => addViaRow().querySelector("input").focus();
  $("#swap").onclick = () => {
    const from = $("#route-from"), to = $("#route-to");
    [from.value, to.value] = [to.value, from.value];
    [from.dataset.id, to.dataset.id] = [to.dataset.id || "", from.dataset.id || ""];
    if (from.value && to.value) submitRoute();
  };
  $("#route-clear").onclick = async () => {
    $("#route-from").value = ""; $("#route-to").value = ""; $("#via-list").innerHTML = "";
    const result = await api("/api/route/clear", {});
    applyState(result.state, { silent: true });
  };
  $("#find-input").oninput = runFind;
  attachSuggest($("#route-from"));
  attachSuggest($("#route-to"));
  $("#suggest").addEventListener("mousedown", (e) => {
    const item = e.target.closest(".suggest-item");
    if (item) { e.preventDefault(); pickSuggest(Number(item.dataset.i)); }
  });
  $("#reset").onclick = async () => {
    $("#route-from").value = ""; $("#route-to").value = ""; $("#via-list").innerHTML = "";
    app.state = { closed: [], added_doors: [], route: null };
    await loadBuilding(app.key, true);
    toast("Building reset: all closures, new doors and the route are gone.");
  };
  $("#chat-form").onsubmit = (e) => {
    e.preventDefault();
    const text = $("#chat-input").value.trim();
    if (!text) return;
    $("#chat-input").value = "";
    sendChat(text);
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { hidePopover(); app.pendingDoorFrom = null; setBanner(null); }
  });
}

init().catch((error) => toast(`Could not start: ${error.message}`, true));
