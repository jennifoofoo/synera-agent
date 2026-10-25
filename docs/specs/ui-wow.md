# UI wow moments (after the white-model polish, branch `ui-polish`)

Goal: the demo should not look like every indoor-map competitor (map, card, search box). What only we have: Wanda
talks, and the building answers. Five moments, each its own commit, built in parallel on throwaway branches from
`ui-polish` and cherry-picked back. UI only, no Python, no API changes. Tests stay green (`tests/e2e/`).

| # | Moment | Files | Model |
|---|---|---|---|
| 1 | Focus mode: with a route, rooms and furniture off the route fade to 40 %, the route rooms stay white, the destination gets a blue edge and a light floor tint; a chat-made route is framed like a Directions route, with a slow turn while the line draws in | `scene/FloorMesh.tsx`, `scene/geometry.ts` (withCutaway shader), `scene/Things.tsx`, `scene/Markers.tsx`, `scene/CameraRig.tsx`, `model/palette.ts` | Opus |
| 2 | Wanda lives in the Talk button: a ring that pulses with the real microphone level while listening and breathes with the reply while speaking; "Ask Wanda" | `ui/Omnibox.tsx`, `ui/Omnibox.css`, new `audioLevel.ts` (voice.ts only if unavoidable, minimal) | Sonnet |
| 3 | The building builds up: on open and on floor change the floor rises from the ground in 600 ms (slab and walls together), furniture follows; off under reduced motion | new `scene/FloorRise.tsx`, `scene/Scene.tsx` (wrap the per-floor group only) | Sonnet |
| 4 | Chaos moment: closing a lift re-routes live (server does it already); the old line dissolves (300 ms) before the new one draws in | `scene/RouteLine.tsx` | Sonnet |
| 5 | Small: route card collapsed by default ("4 steps" opens the list, chips always visible); the destination's label larger than every other label | `ui/Card.tsx`, `ui/Card.css`, `scene/Labels.tsx`, `styles.css` | Sonnet |

Rules for every agent: branch from `ui-polish` (`git reset --hard ui-polish` first), `cd twin && npm run build` green,
screenshots with `scripts/ui_shots.py`, the e2e tests named in the brief green, one commit, report the hash, no push.
