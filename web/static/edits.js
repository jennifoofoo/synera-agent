// Edits the agent made to things and doors (state.added_assets, moved_assets, removed_assets, removed_openings,
// widened_openings): the page's picture of assets and doors is always base picture + state, so undo and reset need no
// special case. app.js calls edits.apply(state) from applyState; 2D hooks: assetClass, drawEffects, decorateOpening.
"use strict";

const edits = (() => {
  const FX_MS = 3200;     // how long the ghost / fade / "new" marks stay after a change
  const FIELDS = ["added_assets", "moved_assets", "removed_assets", "removed_openings", "widened_openings"];
  let base = null;        // {building, assets: [], openings: []} as loaded from the server
  let list = [];          // change rows: {kind, text, floor_id, position, id}
  let fx = null;          // {until, ghosts: [{id, floor_id, position, category, kind}], fades: [...], news: Set, moved: Map}
  let signature = "";
  let marks = { ghosts: [], news: [] };  // persistent picture for 3D
  const state = { version: 0 };
  const names = { floor: (id) => (typeof floorName === "function" ? floorName(id) : id), space: (id) => (typeof spaceName === "function" ? spaceName(id) : id) };
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sides = (o) => o.space_ids.map((s) => (s === "outside" ? "outside" : names.space(s))).join(" ↔ ");

  function snapshot(building) {
    base = { building, assets: building.assets.slice(), openings: building.openings.filter((o) => !o.added) };
    signature = "";
    list = [];
    fx = null;
    marks = { ghosts: [], news: [] };
  }

  function sameFootprint(type) {
    return base.assets.find((a) => a.type === type && a.footprint)?.footprint || null;
  }

  const turned = (x, y) => Math.abs(((((x ?? 0) - (y ?? 0)) % 360) + 540) % 360 - 180) > 0.6;

  // The effective picture: removed gone, moved at the new place, added present, doors without removed, widths updated.
  function compose(edit) {
    const removed = new Set(edit.removed_assets || []);
    const moved = edit.moved_assets || {}, added = edit.added_assets || {};
    const assets = [], rows = [], ghosts = [], news = [];
    for (const a of base.assets) {
      if (removed.has(a.id)) {
        rows.push({ kind: "removed", id: a.id, text: `Removed ${a.name} from ${names.space(a.space_id)}`, floor_id: a.floor_id, position: a.position });
        ghosts.push({ id: a.id, floor_id: a.floor_id, position: a.position, category: a.category, footprint: a.footprint, kind: "removed" });
        continue;
      }
      if (added[a.id]) {  // page loaded after the agent added it: the server's picture already has it
        assets.push(a); news.push(a.id);
        rows.push({ kind: "added", id: a.id, text: `Added ${a.name} in ${names.space(a.space_id)}`, floor_id: a.floor_id, position: a.position });
        continue;
      }
      const m = moved[a.id];
      if (!m) { assets.push(a); continue; }
      const changed = m.space_id !== a.space_id || m.floor_id !== a.floor_id || m.position[0] !== a.position[0] || m.position[1] !== a.position[1] || turned(m.rotation_deg, a.footprint?.rotation_deg);
      const next = { ...a, ...m, footprint: a.footprint ? { ...a.footprint, rotation_deg: m.rotation_deg ?? a.footprint.rotation_deg } : a.footprint };
      assets.push(next);
      if (!changed) continue;
      const where = m.space_id === a.space_id ? `in ${names.space(m.space_id)}` : `from ${names.space(a.space_id)} to ${names.space(m.space_id)}`;
      rows.push({ kind: "moved", id: a.id, text: `Moved ${a.name} ${where}`, floor_id: m.floor_id, position: m.position });
      ghosts.push({ id: a.id, floor_id: a.floor_id, position: a.position, category: a.category, footprint: a.footprint, kind: "moved" });
    }
    for (const [id, m] of Object.entries(added)) {
      if (removed.has(id) || base.assets.some((a) => a.id === id)) continue;
      const asset = { id, name: m.name, type: m.type, category: m.category, space_id: m.space_id, floor_id: m.floor_id, position: m.position, footprint: sameFootprint(m.type) };
      if (asset.footprint && m.rotation_deg != null) asset.footprint = { ...asset.footprint, rotation_deg: m.rotation_deg };
      assets.push(asset);
      news.push(id);
      rows.push({ kind: "added", id, text: `Added ${m.name} in ${names.space(m.space_id)}`, floor_id: m.floor_id, position: m.position });
    }
    const gone = new Set(edit.removed_openings || []), widths = edit.widened_openings || {};
    const openings = [];
    for (const o of base.openings) {
      if (gone.has(o.id)) {
        rows.push({ kind: "removed-door", id: o.id, text: `Removed door ${sides(o)}`, floor_id: o.floor_id, position: o.position });
        continue;
      }
      if (widths[o.id] != null && widths[o.id] !== o.width_m) {
        const text = `${o.width_m != null ? o.width_m : "?"} → ${widths[o.id]} m`;
        openings.push({ ...o, width_m: widths[o.id], widened_from: o.width_m, width_label: text });
        rows.push({ kind: "widened", id: o.id, text: `Widened door ${sides(o)}: ${text}`, floor_id: o.floor_id, position: o.position });
      } else openings.push(o);
    }
    return { assets, openings, rows, ghosts, news };
  }

  function apply(next, { animate = true } = {}) {
    const building = app.building;
    if (!building) return;
    if (!base || base.building !== building) snapshot(building);
    const edit = Object.fromEntries(FIELDS.filter((f) => next && next[f] && (Array.isArray(next[f]) ? next[f].length : Object.keys(next[f]).length)).map((f) => [f, next[f]]));
    const sig = JSON.stringify(edit);
    if (sig === signature) return;
    const before = new Map(building.assets.map((a) => [a.id, a]));
    const result = compose(edit);
    const widths = edit.widened_openings || {};
    const addedDoors = building.openings.filter((o) => o.added).map((o) => (widths[o.id] != null ? { ...o, width_m: widths[o.id] } : o));
    building.assets = result.assets;
    building.openings = [...result.openings, ...addedDoors];
    app.openings = new Map(building.openings.map((o) => [o.id, o]));
    list = result.rows;
    marks = { ghosts: result.ghosts, news: result.news.map((id) => building.assets.find((a) => a.id === id)).filter(Boolean) };
    state.version += 1;
    fx = animate ? effects(before, result) : null;
    signature = sig;
    renderList();
  }

  // Short-lived 2D effects: where things were (ghost), what appeared, what vanished. Only for what just changed.
  function effects(before, result) {
    const now = new Map(result.assets.map((a) => [a.id, a]));
    const ghosts = [], fades = [], moved = new Map();
    for (const [id, a] of before) {
      const b = now.get(id);
      if (!b) fades.push({ id, floor_id: a.floor_id, position: a.position, category: a.category });
      else if (b.floor_id !== a.floor_id || b.position[0] !== a.position[0] || b.position[1] !== a.position[1]) {
        ghosts.push({ id, floor_id: a.floor_id, position: a.position, category: a.category });
        moved.set(id, { from: a.position, floor_id: a.floor_id });
      }
    }
    const news = new Set(result.assets.filter((a) => !before.has(a.id)).map((a) => a.id));
    if (!ghosts.length && !fades.length && !news.size) return fx && fx.until > performance.now() ? fx : null;
    return { until: performance.now() + FX_MS, ghosts, fades, news, moved };
  }

  const live = () => (fx && performance.now() < fx.until ? fx : null);

  // ---------- 2D hooks ----------

  function assetClass(id) {
    const e = live();
    const cls = [];
    if (marks.news.some((a) => a.id === id)) cls.push("edit-new");
    if (e?.moved.has(id)) cls.push("edit-moved");
    return cls.join(" ");
  }

  function drawEffects(layer, floorId) {
    const e = live();
    if (!e) return;
    const make = (tag, attrs) => el(tag, attrs, layer);
    for (const g of e.ghosts) {
      if (g.floor_id !== floorId) continue;
      const [x, y] = svgPoint(g.position);
      make("circle", { cx: x, cy: y, r: 0.3, class: "asset-ghost" });
    }
    for (const f of e.fades) {
      if (f.floor_id !== floorId) continue;
      const [x, y] = svgPoint(f.position);
      make("circle", { cx: x, cy: y, r: 0.22, class: `asset ${f.category || ""} asset-fade` });
    }
    for (const id of e.news) {
      const a = app.building.assets.find((x) => x.id === id);
      if (!a || a.floor_id !== floorId) continue;
      const [x, y] = svgPoint(a.position);
      make("circle", { cx: x, cy: y, r: 0.7, class: "asset-new-ring" });
    }
    clearTimeout(drawEffects.timer);
    drawEffects.timer = setTimeout(() => app.building && render(), Math.max(50, e.until - performance.now() + 30));
  }

  // The moved asset glides from its old place: a CSS translate that animates to zero (not used with reduced motion).
  function glide(id, el) {
    const e = live();
    const from = e?.moved.get(id);
    if (!from || reduced() || from.floor_id !== app.floorId) return;
    const a = app.building.assets.find((x) => x.id === id);
    const [x0, y0] = svgPoint(from.from), [x1, y1] = svgPoint(a.position);
    el.style.setProperty("--dx", `${x0 - x1}px`);
    el.style.setProperty("--dy", `${y0 - y1}px`);
    el.classList.add("asset-glide");
  }

  function decorateOpening(group, o, x, y, r) {
    if (!o.width_label) return;
    const text = el("text", { x, y: y - r * 1.8, class: "width-label", "font-size": 0.5 }, group);
    text.textContent = o.width_label;
  }

  // ---------- Changes tab ----------

  function renderList() {
    const box = document.getElementById("edit-list");
    if (!box) return;
    box.innerHTML = list.length ? "" : '<div class="empty">No things or doors changed.</div>';
    for (const row of list) {
      const item = document.createElement("div");
      item.className = `item edit-${row.kind}`;
      item.tabIndex = 0;
      item.innerHTML = `<div>${esc(row.text)}<div class="kind">${esc(names.floor(row.floor_id))}</div></div>`;
      const go = () => focusPoint(row.floor_id, row.position, row.kind === "added" || row.kind === "moved" ? new Set([row.id]) : null);
      item.onclick = go;
      item.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
      box.appendChild(item);
    }
  }

  return { apply, assetClass, drawEffects, glide, decorateOpening, count: () => list.length, rows: () => list, marks: () => marks, state };
})();

window.edits = edits;
