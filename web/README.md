# Building page: 2D plan and 3D view, route, changes, chat

A lean web page over `BuildingMap`: plain HTML/JS/SVG plus three.js for 3D, served by a stdlib `http.server`. No build step, no new dependencies, works offline (three.js is vendored).

## Start

```bash
uv run python -m web
```

Then open http://127.0.0.1:8765. Options: `--data DIR` (any folder with `*/building.json`, default `data`), `--port`, `--host`, `--env-file` (default `.env`, read for `ANTHROPIC_API_KEY`). Without a key the chat says so; the map, routes and changes still work.

## What it does

- Building picker (every building under `--data`, including a new Sunday building dropped there), floor switcher.
- Rooms from polygons with names or numbers, doors (orange ring = has a step), entrances, stairs (S) and lifts (L), things as small dots.
- Tap a room: start here, go here, add as stop, close/reopen the room or its stair/lift, add a door to a neighbour. Tap a door: close/reopen.
- Route tab: from/to by name, extra stops, step-free. Routes use the agent's people model (`building_agent.routing`, door to door, `"model": "people"` in the JSON), so map and chat show the same rooms and length; the line runs from the start room's centre through the doors to the destination's centre. The route is drawn per floor with A/B markers and floor-change markers (tap one to jump to the other floor). Floors on the route get a blue dot.
- Every closure or new door recomputes the current route and says what changed ("37.8 m longer, now via Lift 1" or "no route any more").
- Find tab: rooms and things by words; hits pulse on the plan.
- Changes tab: close/reopen every stair and lift, list of closures and new doors, reset.
- Things and doors the agent changed (`state.added_assets`, `moved_assets`, `removed_assets`, `removed_openings`, `widened_openings`; `static/edits.js`): the page's picture is always the loaded building plus this state, so undo and reset need no special case. 2D: added things are green with a ring, a moved thing glides from its old place (dashed ghost for a few seconds), a removed one fades, removed doors vanish, a widened door shows "1.2 → 1.6 m". All motion stops under `prefers-reduced-motion`. 3D: floors rebuild on a change; new things have a green halo, old places of moved/removed things a grey/red ghost. The Changes tab lists them in plain words with the room; tap one to focus it on the plan. Routes redraw with every state, the server already recomputes them against the edits.
- Chat tab: posts to `/api/chat`, see below.

## 3D view

The **2D | 3D** switch (top right of the map) shows the same building in 3D. Both views share one state: building, closures, new doors, the current route and a Level 4 draft. Tapping a room or a marked door in 3D opens the same popover as in 2D (start here, go here, close, add door). The floor tabs pick the focused floor in both views. The choice is remembered (`localStorage`), `?view=3d` opens in 3D, `?perf=1` shows fps, draw calls and build time.

- Rooms are floor slabs coloured by type (corridor, hall, stairs, lift, outdoor; production halls ochre, warehouse/logistics green-grey, labs blue) with low walls (42 % of the floor height, 1.1 to 3.2 m) so you can look in. Doors are gaps in the walls at their position and width; entrances are teal and steps orange posts; new doors are green and closed doors red panels.
- Stairs and lifts are see-through shafts between their stop floors. Things are boxes in true size from `footprint` (width, depth, rotation); machines orange, equipment blue. "Things: near" shows them on the focused floor (up to 2500) or when zoomed in, "all" everywhere, "off" never.
- Floors: **Stacked** (x-ray: floors above the focused one are see-through outlines), **Exploded** (floors pulled apart), **One floor**. The minimap (bottom left) shows the focused floor with the route and the camera; tap it to move the view there.
- The route is a glowing line through 3D, with vertical runs at stairs and lifts, drawn progressively like in 2D (static with `prefers-reduced-motion`), then small pulses flow along it. A new route is shown from its lowest floor so the whole climb stays visible. Closed rooms, stairs and lifts are red.
- Labels: room names near the camera only (rooms too small on screen get none, no overlaps, at most 60); hover shows name and type, or a thing's name and size.

Files: `static/view3d.js` (view state, sync with `app.js`, steering API, labels, minimap), `static/scene3d.js` (three.js rendering only), `static/vendor/three/` (three.js r170 + OrbitControls, MIT, see `VERSION.md`).
Data: `GET /api/building` now also carries `floors[].elevation_m`, `floors[].height_m` (drafts without them get 3 m per level) and `assets[].footprint` (`width_m`, `depth_m`, `rotation_deg`).

### Steering API (for the agent, later)

The view state lives in `view3d.js`; the renderer only draws it, so these calls work whether 3D is shown or not (camera moves wait until it is). Ids are space, asset, opening, connector or floor ids; exact names also work.

| Call | Does |
|---|---|
| `view3d.show()`, `view3d.hide()`, `view3d.toggle()`, `view3d.isActive()` | switch the map pane to 3D and back |
| `view3d.setFloorMode(mode, floorId?)` | `"stacked"`, `"exploded"` or `"single"` |
| `view3d.focusFloor(floor)` | floor id, name or level becomes the solid one (the 2D plan follows) |
| `view3d.focus(ids, {colour, name})` | highlight, focus their floor and fly there; returns `{unknown: [...]}` |
| `view3d.highlight(ids, colour, {name})` | colour rooms, things, doors, stairs/lifts; the same name replaces, other names add up |
| `view3d.clearHighlights(name?)` | one named highlight or all |
| `view3d.flyTo(target)` | id, or `{floor_id, point: [x, y], radius}` |
| `view3d.showRoute(route)` | draw a route in the `/api/route` shape (`null` hides; `undefined` follows the page's route again) |
| `view3d.playRoute()` | replay the route animation |
| `view3d.setThings(mode)` | `"auto"`, `"on"`, `"off"` |
| `view3d.resetView()` | overview of the building |
| `view3d.apply(spec)` | one call for a chat reply's `view` object, see below |
| `view3d.stats()`, `view3d.benchmark(ms)` | build time, draw calls, triangles, fps (benchmark spins the camera) |
| `view3d.state()` | current view state, e.g. for the agent to read back |

A chat reply may carry `{"reply": "...", "view": {...}}`; `app.js` passes `view` to `view3d.apply()`. Keys (all optional, applied in this order): `mode` (`"2d"`/`"3d"`), `floor_mode`, `floor`, `things`, `clear_highlights` (`true` or a name), `highlight` (`{ids, colour, name}` or a list), `focus` (ids), `fly_to` (id or `{floor_id, point}`), `route` (route object or `null`), `reset`. Example: closures for "What changes?"

```json
{"view": {"mode": "3d", "floor_mode": "stacked", "highlight": [{"ids": ["...-V02"], "colour": "#dc2626", "name": "closed"}, {"ids": ["...-F2-S014", "...-F2-S015"], "colour": "#f59e0b", "name": "impact"}], "fly_to": "...-V02"}}
```

Performance (largest kit building `dev/osm-way27917482`: 5 floors, 1623 spaces, 1799 openings, 5250 things; Chrome on a MacBook): all five floors built in about 30 to 40 ms, 20 to 36 draw calls (merged geometry per floor, one instanced mesh per floor for things, doors and shafts), 60 fps (display limit) while orbiting, also exploded with all 5250 things shown (108k triangles). It only renders when something moves. The focused floor is built first, the rest one per idle slice; things are built only when first shown.

## Click selection (context for the chat)

Clicks pick what the next chat message is about, in 2D and 3D alike. A chip above the chat input shows it ("Selected: Office 1.04"), the × clears it, and the plan highlights it (blue room outline, blue dot, blue ring).

| Click | Selects | `context` sent |
|---|---|---|
| a room | the room (and the room menu opens as before) | `{space_id, floor_id}` |
| a thing (dot on the plan, box in 3D) | the thing | `{asset_id, space_id, floor_id}` |
| a room with Shift held, or the menu entry "Select this spot" | the point, "Point in Hall 1" | `{space_id, point: [x, y], floor_id}` |

Doors, lifts and stairs stay menu-only, and a click while placing a new door only picks the neighbour. Points are model metres (+y north); `floor_id` is the floor of the room, not of the camera. The selection is one-shot: it goes with the next message (typed or spoken) and is cleared once a reply arrives. If the reply has `selection_ignored`, the chat says "I couldn't use the selection: <reason>" and the chip stays so you can retry; a failed request keeps it too. Switching building clears it.

## New building from floor plans (Level 4)

"+ New building" (or the New tab): drop one PNG/JPG per floor, give its floor and one length you know in metres (or tick "scale bar printed"), "Read plans". Each floor is read in the background (one vision call, 10 to 20 s), then the draft is drawn on the plan with suspicious rooms and doors in red and one findings line. Fix it on the plan (tap a room: add a door to a neighbour, set its type; tap a door: remove it) or set the scale per floor. "Save building…" shows the understanding card; only "Yes, save" saves (with "Save anyway" ticked if problems remain). The building then appears under "built from plans" in the picker and is loaded, so routes and chat work on it.

The page uses the same tools as the chat agent (`building_agent/level4/tools.py`), so card and yes rules are identical. The chat (building_agent backend) gets these tools too and shares the page's draft: a draft the agent builds is shown on the plan, a building it saves is opened.
Uploads: PNG/JPG only (magic bytes and Pillow), at most 10 MB, stored as `agent_output/uploads/plan-<random>.png|jpg`; the browser only sends upload ids, never paths. Saved buildings: `agent_output/buildings/<id>/building.json` (key `user/<id>`).
Offline demo without API calls: `uv run python -m web --fake-plans data/dev/proc-campus-dev-000` reads every uploaded image as that building's floor (with a printed scale bar and one door missing, so a red finding shows).

## Files

| File | What |
|---|---|
| `server.py` | HTTP server and JSON API (endpoint list in the module docstring) |
| `api.py` | Pure functions over `BuildingMap`: building view, route geometry, closures, doors |
| `chat.py` | Chat adapter, one-line switch `BACKEND` |
| `level4_api.py` | Upload, background build, preview, fixes, card and save for new buildings from floor plans |
| `static/` | `index.html`, `app.js`, `edits.js` (agent edits to things and doors), `style.css`, `voice.js`, `plan.js` (new building flow), `view3d.js` + `scene3d.js` (3D view), `vendor/three/` |

Tests: `tests/test_web.py`, `tests/test_web_edits.py`, `tests/test_web_level4.py`, `tests/test_web_view3d.py` (no API calls).

## Chat backend

`web/chat.py` has `BACKEND = "auto"`: it uses `building_agent.agent.answer(building_dir, question)` when it imports, otherwise the starter agent.
`answer()` is stateless today (fresh map per question), so chat follow-ups lose context and the agent's closures/doors/routes do not reach the map. With `BACKEND = "starter"` the chat uses `starter_agent.BuildingAgent` on the same `BuildingMap` the page draws, so its changes and its last route show up on the plan.
To wire our agent fully it needs a stateful entry point that takes the page's `BuildingMap`, e.g. `Session(building_map).ask(text) -> str`, and sets `building_map.last_route` when it routes.

State lives in server memory per building (single-user demo); restart or "Reset building" to start clean.
