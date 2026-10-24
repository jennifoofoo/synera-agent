# twin/ architecture

React + TypeScript + Vite, `@react-three/fiber` (three r170), drei, postprocessing (N8AO), zustand, fuse.js.
Talks only to Jennifer's JSON API (`web/server.py`, `web/api.py`); no backend code here.

## One screen, one input

The building fills the screen. Top left the building name (tap = switch building). Left edge the floor
rail (numbers; tap the active one again = only this floor; `⇕` pulls the floors apart; `⌂` home).
Bottom centre the dock: **one card** (the selected room/thing with 3 actions, or the last reply) above
**one input** ("Ask or search…", mic). A small pill top right appears only when the building has changes.
Nothing else by default. Popovers only on click, never hover. No tabs, panels, breadcrumbs, KPI numbers.

## Folders and owners

| Path | What | Owner |
|---|---|---|
| `src/api/types.ts`, `src/api/client.ts` | API shapes and fetch wrappers. Additions welcome (append only). | shared |
| `src/model/model.ts` | `BuildingModel`: lookups, bounds, `floorElevation` per floor mode | scene session |
| `src/model/palette.ts` | colours (blue groups, status, gold accent) and `spaceGroup()` | scene session |
| `src/store.ts` | the one zustand store (see below). Add new fields/actions in small, named blocks; tell the scene session when you do. | shared, scene session merges |
| `src/scene/**` | everything inside the `<Canvas>`: floors, things, route, markers, labels, camera, effects | **scene session only** |
| `src/ui/TopBar.tsx`, `src/ui/FloorRail.tsx`, `src/ui/ChangesPill.tsx`, `src/App.tsx` | the shell | scene session |
| `src/ui/Omnibox.tsx` | ask-or-search input, hits, voice in, spoken replies | **chat/search session** |
| `src/ui/Card.tsx` | selection card (Route here / I'm here / Close) and reply card | **card session** |
| `src/ui/Position.tsx` (stub) | "You are here" chip with clear, guide "Step k of n" + Next, arrival text | **position session** |
| `src/ui/Phone.tsx` (stub) | phone glue: header buttons, audio unlock, wake lock, bottom-sheet card, mobile audit fixes; rules in `MOBILE.md` | **phone session** |
| `src/voice.ts` | Web Speech in, `/api/speak` out (fallback browser voice), audio unlock, wake lock | chat/search session (mobile session may add unlock/wake lock) |
| `src/styles.css` | base styles at the top (scene session); each component owns its marked block (`===== Omnibox`, `===== Card`, `===== Phone`). Prefer a component-local `X.css` imported by the component if the block grows. | per block |

Conventions:
- A UI component reads the store with selectors (`useTwin((s) => s.state)`) and writes only through actions.
  Never mutate `state`/`model`; never call the API directly from a component (add an action instead).
- Styles: base tokens in `src/styles.css` `:root` (`--bg --panel --line --text --muted --accent --gold --ok --warn
  --danger`); each component keeps its own `X.css` next to it (import it in the component) or its marked block.
  Colours inside the scene come from `src/model/palette.ts`.
- Ids are the API's ids (`space.id`, `asset.id`, `connector.id`); `flyTo(id)` and `select()` accept them as is.
- Every fact comes from the API; the UI never computes routes, distances or counts.

Rule: a session edits only its own files/blocks. Need something in the store or scene? Message the scene
session with the exact field/action you need (name, type, when it changes) instead of editing `scene/`.

## Store (`useTwin`)

State: `buildings, buildingKey, building, model, state (BuildingState from the API: closed, added_doors,
route, position, guide, asset edits), loading, error, chatAvailable, speechAvailable`.

UI: `profile ("planner" | "worker", by width < 1100 px or a coarse-pointer phone; worker = no AO, bigger targets),
viewMode ("2d" | "3d"; worker is 2D only, setViewMode("3d") is ignored there), bottomInset (px of UI covering the bottom; the camera frames above it),
draft (a Level 4 draft is shown instead of the building; ui/newBuildingStore sets it), rightInset (px of a side sheet at the right edge; the camera frames left of it, setRightInset), floorMode
("stacked" | "exploded" | "single"), focusedFloorId, thingsMode, cutaway, ao, reducedMotion, selection
(kind space|asset|point|connector, id, floor_id, space_id?, point?), popover (screen position of the last
click), highlights {name: {ids, colour}}, camera (request with nonce), replyShown, chat[], chatBusy, voiceOut,
hereArmed`.

Actions: `loadBuildings, openBuilding(key), applyState(state), setViewMode, setBottomInset(px), setFloorMode, focusFloor, setThingsMode,
toggleCutaway, select(selection | null, screen?), closePopover, setHighlight(name, highlight | null),
requestCamera({kind: home|object|floor|point, ids?, floorId?, point?, radius?}), flyTo(id) (sets the floor and
frames the object), dismissReply, setVoiceOut, armHere(on), route(start, destination, stepFree?), clearRoute,
setClosed(element, closed), addDoor(first, second), reset, ask(message, voice?, opts?: {here}) -> ChatReply | null`.

`ask` sends the selection as `context` (space_id/asset_id/point/floor_id), adds `context.here` when
`hereArmed`, sends top-level `voice: true` when the message came from speech, stores the reply in `chat`,
applies `reply.state`, focuses the route's first floor / the guide leg's floor / the position's floor, and for
`located` hits sets the `found` highlight and flies to the first one.

Every fact comes from the API. The scene draws `state` as is: route (glowing line, floor changes vertical),
`position` (You are here), `guide.leg` (stronger line, "Next: …"), `closed` (red circles, radius ~ sqrt(n)),
asset edits (green added, grey removed, dashed moved), `highlights`, `selection` (gold).

## Scene (for reference)

`geometry.ts` merges each floor into one BufferGeometry (slab + low walls with door gaps, vertex colours per
blue group, `spaceIndex` per vertex for picking via three-mesh-bvh, `wallNormal` for the dollhouse cutaway
shader that lowers outer walls facing the camera) plus one line geometry for the fine edges. `FloorMesh`
swaps materials for ghost floors (white glass 0.1). `Things` is one InstancedMesh per floor (true footprint
size) plus an inverted-hull outline. `CameraRig` wraps drei `CameraControls` with limits (never below the
floor, bounded target, min/max distance) and handles `camera` requests; reduced motion = no transitions.
Planner only: N8AO, SMAA, vignette 0.32, contact shadows, ViewCube.

## Run

```bash
uv run python -m web            # API on 127.0.0.1:8765 (from the repo root)
cd twin && npm install && npm run dev   # http://localhost:5180, /api proxied
```

`npm run build` writes `twin/dist/` (static files; `web/server.py` could serve them from a `/twin/` path later).
