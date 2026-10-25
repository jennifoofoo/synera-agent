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

## Round 2 (after the five moments)
| # | Moment | Files | Model |
|---|---|---|---|
| 6 | Destination as a blue body with a route (walls and floor, opacity .32), nothing blue without a route | `scene/Markers.tsx` | done |
| 7 | New building by voice and button: planner gets a visible "+ Building" entry; the voice/text command "new building", "neues Gebäude", "new floor plan" opens the same upload sheet; corrections and the yes stay with the agent | `ui/Omnibox.tsx`, `ui/TopBar.tsx` or `ui/Planner.tsx`, `ui/newBuildingStore.ts` | Sonnet |
| 8 | Talk and Ask as round icon-only buttons (aria-labels unchanged); while listening the Talk button shows a stop icon; the Wanda ring stays | `ui/Omnibox.tsx`, `ui/Omnibox.css` | Sonnet |
| 9 | Guide me follow-cam (behind and above the dot, heading-up, walked part fades, next-turn badge, smooth return) | new `scene/FollowCam.tsx`, `scene/RouteLine.tsx` | Opus, running |
| 10 | Walk sheet like Maps turn-by-turn: collapsed row with big distance and one-line instruction, list and settings on swipe-up, one voice control | `ui/Walk.tsx`, `ui/Walk.css`, `ui/PhoneSheet.tsx` | Sonnet, running |
| 11 | Studio look: seamless backdrop, soft baked shadows, Lightformer environment, plinth, fov 32, no view cube, Apple-style labels | `scene/Scene.tsx`, `scene/Effects.tsx`, `scene/GroundGrid.tsx`, `styles.css`, `Labels.tsx` | Opus, running |

## Round 3 (competitor photo: restraint, keep our 3D)
| # | Moment | Files | Model |
|---|---|---|---|
| 12 | Welcome card at start: "Hi, I'm Wanda. Welcome to <building>.", "What can I help you find?", 3–4 chips from the real building (toilet, coffee, lab/machine, "What if <lift> is closed?"); gone after the first question or tap | new `ui/Welcome.tsx/.css`, `App.tsx` (one line) | Sonnet, running |
| 13 | One bottom voice bar instead of Ask/Talk: Wanda orb (blue gradient, breathes idle, pulses with audio level), live caption, mic, stop while speaking; text input expands from the bar | `ui/Omnibox.tsx/.css` | Opus, running |
| 14 | Fewer controls: building name + floor as one pill top-left; zoom +/-, 3D/2D, recenter as one slim stack bottom-right; closures counter only when something is closed | `ui/TopBar.tsx`, `ui/FloorRail.tsx`, `ui/Recenter.tsx`, `styles.css`, `Phone.css` | after the studio look lands |
| 15 | Labels: small coloured POI dots with text beside them, no boxes | part of 11 | Opus, running |
