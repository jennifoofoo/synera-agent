# 2D page: floor plan, route, changes, chat

A lean web page over `BuildingMap`: plain HTML/JS/SVG, served by a stdlib `http.server`. No build step, no new dependencies.

## Start

```bash
uv run python -m web
```

Then open http://127.0.0.1:8765. Options: `--data DIR` (any folder with `*/building.json`, default `data`), `--port`, `--host`, `--env-file` (default `.env`, read for `ANTHROPIC_API_KEY`). Without a key the chat says so; the map, routes and changes still work.

## What it does

- Building picker (every building under `--data`, including a new Sunday building dropped there), floor switcher.
- Rooms from polygons with names or numbers, doors (orange ring = has a step), entrances, stairs (S) and lifts (L), things as small dots.
- Tap a room: start here, go here, add as stop, close/reopen the room or its stair/lift, add a door to a neighbour. Tap a door: close/reopen.
- Route tab: from/to by name, extra stops, step-free. The route is drawn per floor with A/B markers and floor-change markers (tap one to jump to the other floor). Floors on the route get a blue dot.
- Every closure or new door recomputes the current route and says what changed ("37.8 m longer, now via Lift 1" or "no route any more").
- Find tab: rooms and things by words; hits pulse on the plan.
- Changes tab: close/reopen every stair and lift, list of closures and new doors, reset.
- Chat tab: posts to `/api/chat`, see below.

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
| `static/` | `index.html`, `app.js`, `style.css`, `voice.js`, `plan.js` (new building flow) |

Tests: `tests/test_web.py`, `tests/test_web_level4.py` (no API calls).

## Chat backend

`web/chat.py` has `BACKEND = "auto"`: it uses `building_agent.agent.answer(building_dir, question)` when it imports, otherwise the starter agent.
`answer()` is stateless today (fresh map per question), so chat follow-ups lose context and the agent's closures/doors/routes do not reach the map. With `BACKEND = "starter"` the chat uses `starter_agent.BuildingAgent` on the same `BuildingMap` the page draws, so its changes and its last route show up on the plan.
To wire our agent fully it needs a stateful entry point that takes the page's `BuildingMap`, e.g. `Session(building_map).ask(text) -> str`, and sets `building_map.last_route` when it routes.

State lives in server memory per building (single-user demo); restart or "Reset building" to start clean.
