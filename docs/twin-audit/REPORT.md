# Twin audit: what is drawn versus what the data says

Branch `fix/twin-openings` (on top of origin/main 765b9d7, which contains feat/twin). Scope: `twin/` plus `scripts/twin_audit.sh`,
`tests/e2e/`, this folder. Evidence: screenshots in this folder, and the audit table at the end (125 checks, 0 mismatches on the tip).

## The bug that started it

In proc-factory-dev-003 the route H-A4 -> H-A3 crossed what looked like a wall. The route was right (server points
(-7.2, 59.9) -> (-7.2, 51.3) -> (-7.2, 42.8)); the shared edge of the two zones is an `opening` (width 14.6 m, whole edge is 14.5 m)
and `buildFloorGeometry` cut the 3D wall piece but still drew the slab outline of both polygons (grey line in the plan, thin dark strip in 3D).
Fix: gaps are computed once per opening and cut from wall pieces, slab outline lines and slab sides.

- Between two spaces: gap = width_m centred on `position` projected onto the shared boundary of the two polygons (collinear
  edges within 0.35 m), clamped to it; an `opening` wider than the boundary opens all of it.
- Entrances, and doors with no shared boundary near: width_m (min 0.6 m) along the polygon edge nearest to `position`; at a
  polygon corner both edges open (OSM entrances sit on vertices).
- Before/after: `before-factory-003-*.png` / `after-factory-003-*.png` (desktop 2D and 3D, mobile 2D), same for `swiss-203`
  (doors 0.8 to 0.9 m, thin walls) and `osm-27326387` (rotated building). `after-resplan-1465-*.png` too.

## Mismatch table

| ID | What is drawn | What data / server says | Evidence | Status |
|---|---|---|---|---|
| A1 | Outline line across every `opening` (and slab side strip in 3D) | opening = no wall, width_m up to 17.2 m | before/after screenshots; audit row `openings as gaps` fails 0/17 with the fix disabled | fixed (118617d, 03595ef, 446d117) |
| A2 | Gap only if the position was within 0.35 m of an edge of the same space; swiss walls leave 0.15 to 0.3 m between room polygons, 2 cm corner stubs stayed in gaps | thin-wall data | audit on swiss-203: 10 of 24 openings blocked before 03595ef | fixed (03595ef) |
| A3 | OSM entrance at a polygon vertex opened an arbitrary one of its two edges | entrance 0.9 m at a corner | audit osm-360544293: 7 entrances blocked | fixed (446d117) |
| A4 | A door added with /api/door stayed wall; removed/widened doors (state.removed_openings, widened_openings) not applied | `building.openings` after /api/door has 141 vs 140, `state.added_doors` has it | audit rows `added door drawn as gap`, `removed door drawn as wall` (failed on 8 of 10 buildings before) | fixed (d56d07a); server puts the new door at the END of the shared wall (corner), twin now opens the shared boundary (446d117) |
| A5 | Phone: open Directions sheet covers the top of the floor rail, floors 1 and 0 unreachable on 360x640 | topInset known in store | `before-rail-directions-360x640.png`, `after-rail-directions-360x640.png` | fixed (62ccdaa, uses existing `topInset`) |
| A6 | Doors with `step_free: false` had no mark anywhere | openings[].step_free | `stepfree-marker-mobile.png` (data patched in flight: only one entrance in the 10 buildings is not step-free) | fixed (b824288, 2D plan only) |
| A7 | Pale banded rectangle displaced from the building at the lower right (3D, Chromium and WebKit) = drei ContactShadows (one baked 512 px frame on a plane 1.6x the building, 0.05 m above the ground plane beside the grid) | nothing | `ghost-before-home.png` vs hidden plane experiment vs `ghost-after-home.png` | fixed on main already by Leonie (00523be removed it); matches Jennifer's iPad "ghost with soft shadows". Flicker not measured here (controls agent) |
| A8 | 2D home fit ignores the dock and fits by the diagonal: on a 1024x700 iPad the tall floor spans y = -44 .. 674, dock top 630 (top cut off, bottom under the dock) | floor bounds | measured with projected floor corners (see `camera-fit-proposal.patch`) | not fixed here: CameraRig is owned by fix/twin-controls; patch (fitPlan: zoom = usable px / extent) attached as a proposal |
| A9 | Wheel zoom 5 x 500 on 1024x700: lands at zoom 60 (about 60 px per metre) inside one empty hall, so the screen is plain grey with one wall line (`before-wheel-5.png`). The "compact layout" is the worker profile, switched by width < 1100 px by design | n/a | `before-wheel-0.png`, `before-wheel-5.png` | not fixed here (controls agent). Suggestion: cap 2D zoom at about 4x the fit zoom except for fly-to |
| B1 | Route polyline | server `segments[].points` | audit `routes follow server points`: 5 random pairs x 10 buildings, deviation <= 2 cm | ok, no mismatch (drawn = server points, door to door) |
| B2 | Closed door, room, connector markers; reopen removes them | /api/close | audit `closed ... drawn` | ok |
| B3 | Route after closing its connector | server recomputes `state.route` (85.9 m via V01 -> 90.9 m via V02) | audit `route avoids closed connector` | ok (the UI only redraws state.route) |
| B4 | Stairs/lifts: every stop space is drawn on its floor; 2D POI icons (lift / stairs) per floor; 3D shafts; closed ones red | connectors[] | audit `connectors (all stops)` 10/10 buildings | ok |
| B5 | Assets: instance count equals data (limit 4000 per floor) | assets[] | audit `assets` | ok. Rotation/size sign checked by reading the code (rotation.y = deg, z = -y): consistent for CCW degrees; not verified against a true polygon because data assets all lie inside their own space polygon (0 of 4400 outside) and the audit only counts them |
| B6 | Campus site map route | `legs[].world_points`, link ends | audit `campus route legs drawn` 14 = 14 | ok |
| B7 | You are here + guide leg + "Next:" chip | state.position, state.guide.leg.segments | `guide-position-mobile.png` (state injected with `applyState`, because chat needs a key) | implemented (position marker, stronger guide line, Next chip) |
| B8 | Labels: anchors | `space.anchor` inside polygon | data check: 0 of 1,500 anchors outside; duplicate names exist (campus 24, no collision rule needed, labels cull on overlap) | ok |
| C1 | Polygons with holes | none in the data (every polygon is one ring) | data check | cannot happen with this data |
| C2 | Same polygon on several floors | allowed, each floor is its own geometry | audit spaces 79/79 etc. | ok |
| C3 | Level 4 flow (upload, preview, saved building) | needs the vision model (API key) | not run | cannot test without a key; the preview building goes through the same geometry, so openings/gaps apply |
| C4 | Doors/openings have no glyph, only gaps; entrances have a POI only in 2D and only if no label is near | n/a | screenshots | by design; not changed |
| C5 | Opening positions far from any wall (osm Terminal 2: 32 of 33 openings, 6 in swiss-1689, 2 in N3) | position more than 0.8 m from both polygons | audit prints `off-wall in data` | data issue, nothing to cut; cannot fix in the twin |

## Audit output on the tip (b824288)

```
building                   check                          data    drawn  result
dev/proc-factory-dev-003   spaces                           79       79  ok
dev/proc-factory-dev-003   connectors (all stops)            2        2  ok
dev/proc-factory-dev-003   assets                          505      505  ok
dev/proc-factory-dev-003   doors as gaps                    64       64  ok
dev/proc-factory-dev-003   entrances as gaps                 4        4  ok
dev/proc-factory-dev-003   openings as gaps                 17       17  ok
dev/proc-factory-dev-003   routes follow server points        5        5  ok
dev/proc-factory-dev-003   closed door drawn                 1        1  ok
dev/proc-factory-dev-003   closed room drawn                 1        1  ok
dev/proc-factory-dev-003   closed connector drawn            2        2  ok
dev/proc-factory-dev-003   route avoids closed connector      V01  avoided  ok
dev/proc-factory-dev-003   added door drawn as gap           1        1  ok
dev/proc-factory-dev-003   removed door drawn as wall        1        1  ok
dev/proc-factory-dev-005   spaces                          132      132  ok
dev/proc-factory-dev-005   connectors (all stops)            2        2  ok
dev/proc-factory-dev-005   assets                          844      844  ok
dev/proc-factory-dev-005   doors as gaps                   113      113  ok
dev/proc-factory-dev-005   entrances as gaps                 4        4  ok
dev/proc-factory-dev-005   openings as gaps                 20       20  ok
dev/proc-factory-dev-005   routes follow server points        5        5  ok
dev/proc-factory-dev-005   closed door drawn                 1        1  ok
dev/proc-factory-dev-005   closed room drawn                 1        1  ok
dev/proc-factory-dev-005   closed connector drawn            3        3  ok
dev/proc-factory-dev-005   route avoids closed connector      V01  avoided  ok
dev/proc-factory-dev-005   added door drawn as gap           1        1  ok
dev/proc-factory-dev-005   removed door drawn as wall        1        1  ok
dev/proc-campus-dev-000    spaces                          152      152  ok
dev/proc-campus-dev-000    connectors (all stops)            6        6  ok
dev/proc-campus-dev-000    assets                          944      944  ok
dev/proc-campus-dev-000    doors as gaps                   147      147  ok
dev/proc-campus-dev-000    entrances as gaps                 2        2  ok
dev/proc-campus-dev-000    routes follow server points        5        5  ok
dev/proc-campus-dev-000    closed door drawn                 1        1  ok
dev/proc-campus-dev-000    closed room drawn                 1        1  ok
dev/proc-campus-dev-000    closed connector drawn            5        5  ok
dev/proc-campus-dev-000    route avoids closed connector      V01  avoided  ok
dev/proc-campus-dev-000    added door drawn as gap           1        1  ok
dev/proc-campus-dev-000    removed door drawn as wall        1        1  ok
dev/swiss-203              spaces                          144      144  ok
dev/swiss-203              connectors (all stops)           10       10  ok
dev/swiss-203              assets                          424      424  ok
dev/swiss-203              doors as gaps                   112      112  ok
dev/swiss-203              entrances as gaps                 4        4  ok
dev/swiss-203              openings as gaps                 24       24  ok
dev/swiss-203              routes follow server points        3        3  ok
dev/swiss-203              closed door drawn                 1        1  ok
dev/swiss-203              closed room drawn                 1        1  ok
dev/swiss-203              closed connector drawn            4        4  ok
dev/swiss-203              route avoids closed connector      V01  avoided  ok
dev/swiss-203              added door drawn as gap           1        1  ok
dev/swiss-203              removed door drawn as wall        1        1  ok
dev/swiss-1689             spaces                          362      362  ok
dev/swiss-1689             connectors (all stops)           13       13  ok
dev/swiss-1689             assets                          940      940  ok
dev/swiss-1689             doors as gaps                   363      363  ok
dev/swiss-1689             entrances as gaps                 6        6  ok
dev/swiss-1689             openings as gaps                 12        6  ok off-wall in data: 6
dev/swiss-1689             routes follow server points        3        3  ok
dev/swiss-1689             closed door drawn                 1        1  ok
dev/swiss-1689             closed room drawn                 1        1  ok
dev/swiss-1689             closed connector drawn            5        5  ok
dev/swiss-1689             route avoids closed connector      V04  avoided  ok
dev/swiss-1689             added door drawn as gap           1        1  ok
dev/swiss-1689             removed door drawn as wall        1        1  ok
dev/osm-way27326387        spaces                           61       61  ok
dev/osm-way27326387        connectors (all stops)            1        1  ok
dev/osm-way27326387        assets                          184      184  ok
dev/osm-way27326387        doors as gaps                    66       66  ok
dev/osm-way27326387        entrances as gaps                 2        2  ok
dev/osm-way27326387        routes follow server points        5        5  ok
dev/osm-way27326387        closed door drawn                 1        1  ok
dev/osm-way27326387        closed room drawn                 1        1  ok
dev/osm-way27326387        closed connector drawn            3        3  ok
dev/osm-way27326387        route avoids closed connector      V01  avoided  ok
dev/osm-way27326387        added door drawn as gap           1        1  ok
dev/osm-way27326387        removed door drawn as wall        1        1  ok
dev/osm-way22744230        spaces                          325      325  ok
dev/osm-way22744230        connectors (all stops)            7        7  ok
dev/osm-way22744230        assets                          890      890  ok
dev/osm-way22744230        doors as gaps                   354      354  ok
dev/osm-way22744230        entrances as gaps                18       18  ok
dev/osm-way22744230        openings as gaps                 14       12  ok off-wall in data: 2
dev/osm-way22744230        routes follow server points        4        4  ok
dev/osm-way22744230        closed door drawn                 1        1  ok
dev/osm-way22744230        closed room drawn                 1        1  ok
dev/osm-way22744230        closed connector drawn            7        7  ok
dev/osm-way22744230        route avoids closed connector      V06  avoided  ok
dev/osm-way22744230        added door drawn as gap           1        1  ok
dev/osm-way22744230        removed door drawn as wall        1        1  ok
dev/osm-way360544293       spaces                           46       46  ok
dev/osm-way360544293       connectors (all stops)            8        8  ok
dev/osm-way360544293       assets                          217      217  ok
dev/osm-way360544293       doors as gaps                     9        9  ok
dev/osm-way360544293       entrances as gaps                19       19  ok
dev/osm-way360544293       openings as gaps                 33        1  ok off-wall in data: 32
dev/osm-way360544293       routes follow server points        4        4  ok
dev/osm-way360544293       closed door drawn                 1        1  ok
dev/osm-way360544293       closed room drawn                 1        1  ok
dev/osm-way360544293       closed connector drawn            2        2  ok
dev/osm-way360544293       route avoids closed connector      V06  avoided  ok
dev/osm-way360544293       added door drawn as gap           1        1  ok
dev/osm-way360544293       removed door drawn as wall        1        1  ok
dev/resplan-1465           spaces                           10       10  ok
dev/resplan-1465           connectors (all stops)            0        0  ok
dev/resplan-1465           assets                           35       35  ok
dev/resplan-1465           doors as gaps                     6        6  ok
dev/resplan-1465           entrances as gaps                 1        1  ok
dev/resplan-1465           openings as gaps                  3        3  ok
dev/resplan-1465           routes follow server points        5        5  ok
dev/resplan-1465           closed door drawn                 1        1  ok
dev/resplan-1465           closed room drawn                 1        1  ok
dev/resplan-1465           added door drawn as gap           1        1  ok
dev/resplan-1465           removed door drawn as wall        1        1  ok
dev/resplan-3832           spaces                            8        8  ok
dev/resplan-3832           connectors (all stops)            0        0  ok
dev/resplan-3832           assets                           31       31  ok
dev/resplan-3832           doors as gaps                     6        6  ok
dev/resplan-3832           entrances as gaps                 1        1  ok
dev/resplan-3832           openings as gaps                  1        1  ok
dev/resplan-3832           routes follow server points        5        5  ok
dev/resplan-3832           closed door drawn                 1        1  ok
dev/resplan-3832           closed room drawn                 1        1  ok
dev/resplan-3832           added door drawn as gap           1        1  ok
dev/resplan-3832           removed door drawn as wall        1        1  ok
campus example             campus route legs drawn          14       14  ok

125 checks, 0 mismatches
```

## How to run it after every push

```bash
cd twin && npm install                      # once
uv run --with playwright playwright install chromium   # once
scripts/twin_audit.sh                       # 10 buildings, about 3 to 5 minutes, exit code 1 on a mismatch
scripts/twin_audit.sh -n 3                  # first 3 only
scripts/twin_audit.sh --building dev/swiss-203 --no-campus
TWIN_AUDIT_BASE=http://localhost:5180 scripts/twin_audit.sh   # reuse a running twin + server
uv run --with playwright pytest -m e2e tests/e2e/test_twin_audit.py -s   # same thing as a test (skips without Playwright, node_modules or data)
```

It starts `python -m web` (no API key) and the twin dev server on free ports and reads the scene through `window.__twinAudit`
(`twin/src/audit.ts`). If someone renames the pieces it relies on, the audit fails loudly: group name `floor:<id>` (FloorMesh),
Line2 name `route-line` (RouteLine), group name `closed-marker` (Markers), `data-audit="campus-route"` (CampusMap2D). It is not
part of `scripts/check.sh` (the `e2e` marker is excluded by `addopts`).

The probes mirror the gap rule in an independent implementation (tests/e2e/twin_audit.py); I verified that the audit fails
(0/17 openings as gaps) when the fix is switched off.

## Commits (oldest first)

| Commit | What | Touches shared state? |
|---|---|---|
| f85e1ae | twin: expose draw counts for the audit (`audit.ts`, names on route line and closed markers) | no (reads `useTwin`, does not change `store.ts`) |
| 118617d | cut a gap of width_m into walls and plan outlines at openings | no |
| 03595ef | 0.35 m shared-boundary tolerance, drop corner stubs inside a gap | no |
| fd6554a | audit hook for the campus route | no |
| 3bfae1c | repeatable twin audit (script, e2e test) | no |
| 62ccdaa | phone: floor rail below the directions sheet | reads `topInset` from the store, `FloorRail.tsx` only |
| d56d07a | draw doors added, removed or widened in the session | reads `state` in `FloorMesh.tsx`; no change to `store.ts` |
| 1e36667 | audit: edits, faster | no |
| 446d117 | doors between two spaces open their shared boundary; corner entrances open both edges | no |
| f7bc935 | audit probes mirror that rule | no |
| b824288 | step marker for not-step-free doors (2D) | no |

No commit changes `store.ts`. `FloorMesh.tsx` (d56d07a) and `FloorRail.tsx` (62ccdaa) are Leonie's files: please review those two first.
