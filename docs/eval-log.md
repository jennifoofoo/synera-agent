# Eval log

## Level 4

### Run 2026-10-24 (claude-sonnet-5-5, prompt 9f2a64f5)

| Floor | Rooms found/true | Recall | Precision | Area err (median) | Door recall | Route err (median) | Findings | Unreachable warned | Tokens in/out | Seconds | Cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 28/28 | 1.00 | 1.00 | 0.6% | 1.00 | 0.3% (162) | 0 | no | 1688/2228 | 10.4 | 0.026 |
| proc-campus-dev-001:0 | 22/22 | 1.00 | 1.00 | 0.8% | 1.00 | 0.1% (126) | 0 | no | 1626/1772 | 8.7 | 0.021 |
| proc-factory-dev-003:0 | 47/47 | 1.00 | 1.00 | 0.1% | 0.96 | 0.0% (276) | 0 | no | 2734/3864 | 17.4 | 0.044 |
| resplan-439:0 | 8/8 | 1.00 | 1.00 | 0.6% | 1.00 | 0.2% (42) | 0 | no | 1613/875 | 5.1 | 0.012 |
| resplan-1465:0 | 10/10 | 1.00 | 1.00 | 1.7% | 1.00 | 19.0% (54) | 1 | no | 1613/958 | 7.4 | 0.013 |
| swiss-31:0 | 25/30 | 0.80 | 0.96 | 8.6% | 0.35 | 7.3% (19) | 3 | yes | 1643/2132 | 12.6 | 0.025 |
| swiss-203:0 | 28/36 | 0.78 | 1.00 | 8.6% | 0.26 | 12.2% (7) | 4 | yes | 1667/2262 | 14.3 | 0.026 |
| osm-way27326387:0 | 18/21 | 0.86 | 1.00 | 10.2% | 0.67 | 6.3% (75) | 2 | yes | 1577/1698 | 11.4 | 0.020 |

- Clean (procedural, ResPlan), 5 floors, medians: recall 1.00, precision 1.00, door recall 1.00, area err 0.6%, route err 0.2%, floors with an unreachable-room finding: 0/5
- Swiss, 2 floors, medians: recall 0.79, precision 0.98, door recall 0.31, area err 8.6%, route err 9.8%, floors with an unreachable-room finding: 2/2
- OSM, 1 floors, medians: recall 0.86, precision 1.00, door recall 0.67, area err 10.2%, route err 6.3%, floors with an unreachable-room finding: 1/1
- All 8 floors: median seconds 10.9, median cost 0.023 USD, total 0.186 USD (list price, not checked against an invoice).
- Targets on clean floors: room recall met, room precision met, door recall met, area error met, route error met, unreachable on at most 1 of 10 floors met
- Swiss floors with missing rooms or doors that were also warned about: 2/2 (target 100%).

### After door snapping (2026-10-24, same cached extractions, prompt 9f2a64f5, no API call)

Doors are projected onto the stretch of wall the two rooms share (entrances onto the room's outside wall), nearest to the point the model gave. A door that is moved more than 0.5 m gets the warning `door_moved`; doors more than 0.6 m from a wall are still dropped as `door_not_on_wall`.

| Floor | Rooms found/true | Recall | Precision | Area err (median) | Door recall | Route err (median) | Findings | Unreachable warned | Tokens in/out | Seconds | Cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 28/28 | 1.00 | 1.00 | 0.6% | 1.00 | 0.3% (162) | 0 | no | 1688/2228 | 10.4 | 0.026 |
| proc-campus-dev-001:0 | 22/22 | 1.00 | 1.00 | 0.8% | 1.00 | 0.1% (126) | 0 | no | 1626/1772 | 8.7 | 0.021 |
| proc-factory-dev-003:0 | 47/47 | 1.00 | 1.00 | 0.1% | 0.96 | 0.0% (276) | 1 | no | 2734/3864 | 17.4 | 0.044 |
| resplan-439:0 | 8/8 | 1.00 | 1.00 | 0.6% | 1.00 | 0.2% (42) | 0 | no | 1613/875 | 5.1 | 0.012 |
| resplan-1465:0 | 10/10 | 1.00 | 1.00 | 1.7% | 1.00 | 19.0% (54) | 1 | no | 1613/958 | 7.4 | 0.013 |
| swiss-31:0 | 25/30 | 0.80 | 0.96 | 8.6% | 0.35 | 7.3% (19) | 4 | yes | 1643/2132 | 12.6 | 0.025 |
| swiss-203:0 | 28/36 | 0.78 | 1.00 | 8.6% | 0.26 | 12.2% (7) | 5 | yes | 1667/2262 | 14.3 | 0.026 |
| osm-way27326387:0 | 18/21 | 0.86 | 1.00 | 10.2% | 0.67 | 5.2% (75) | 3 | yes | 1577/1698 | 11.4 | 0.020 |

- Clean (procedural, ResPlan), 5 floors, medians: recall 1.00, precision 1.00, door recall 1.00, area err 0.6%, route err 0.2%, floors with an unreachable-room finding: 0/5
- Swiss, 2 floors, medians: recall 0.79, precision 0.98, door recall 0.31, area err 8.6%, route err 9.8%, floors with an unreachable-room finding: 2/2
- OSM, 1 floors, medians: recall 0.86, precision 1.00, door recall 0.67, area err 10.2%, route err 5.2%, floors with an unreachable-room finding: 1/1
- All 8 floors: median seconds 10.9, median cost 0.023 USD, total 0.186 USD (list price, not checked against an invoice).
- Targets on clean floors: room recall met, room precision met, door recall met, area error met, route error met, unreachable on at most 1 of 10 floors met
- Swiss floors with missing rooms or doors that were also warned about: 2/2 (target 100%).

- Route error before to after: proc-campus-dev-000 0.3% to 0.3%, proc-campus-dev-001 0.1% to 0.1%, proc-factory-dev-003 0.0% to 0.0%, resplan-439 0.2% to 0.2%, resplan-1465 19.0% to 19.0%, swiss-31 7.3% to 7.3%, swiss-203 12.2% to 12.2%, osm-way27326387 6.3% to 5.2%. No floor got worse.
- Findings went up by one on four floors (factory-003, swiss-31, swiss-203, osm): these are `door_moved` warnings, not new errors.
- resplan-1465 did not improve: its door positions are now within 0.06 m of the original for 8 of 10 doors (0.4 m for two), so the 19% does not come from the doors. The remaining error comes from the room anchor (`representative_point` in BuildingMap), which jumps by up to 4.9 m for the big concave room when its outline differs a little from the original.
- A larger snap distance (1.5 m or 3 m instead of 0.6 m) made swiss-203 (12% to 42%) and osm (6% to 18%) much worse, so the 0.6 m limit stays.

### Judge metric (2026-10-24, same cached extractions, prompt 9f2a64f5, no API call)

The kit metric routes anchor to anchor on both buildings. The judge metric routes with our agent (`building_agent.routing.route`, door to door) on the extracted building, maps the room sequence back to original ids via the room matching and measures it on the original with the judge's geodesic rule (`judge_score`): score = best length on the original / length of our sequence, error = 1 - score. Same room pairs as the kit metric (6 random sources, all matched targets, pairs with an original route only). Invalid = a step has no door in the original. No route = the extracted building has no route between two rooms that are connected in the original (a door was not extracted); counts as score 0. Median and mean are over all pairs, invalid and no-route pairs count as error 100%.

| Floor | Kit route err (median) | Judge err (median) | Judge err (mean) | Pairs >= 0.99 | Invalid sequences | No route found | Pairs |
|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 0.3% | 0.0% | 0.0% | 100% | 0 | 0 | 156 |
| proc-campus-dev-001:0 | 0.1% | 0.0% | 0.0% | 100% | 0 | 0 | 120 |
| proc-factory-dev-003:0 | 0.0% | 0.0% | 41.4% | 58% | 108 | 0 | 264 |
| resplan-439:0 | 0.2% | 0.0% | 0.0% | 100% | 0 | 0 | 30 |
| resplan-1465:0 | 19.0% | 0.0% | 0.0% | 100% | 0 | 0 | 40 |
| swiss-31:0 | 7.3% | 100.0% | 93.6% | 6% | 1 | 116 | 125 |
| swiss-203:0 | 12.2% | 100.0% | 97.4% | 3% | 0 | 147 | 151 |
| osm-way27326387:0 | 5.2% | 10.5% | 33.0% | 34% | 0 | 23 | 89 |
| All 8 floors | 2.7% | 0.0% | 41.3% (pair-weighted) | 55% (pair-weighted) | 109 | 286 | 975 |

In plain words:

- resplan-1465 is not bad under the judge metric: all 40 pairs score 1.0 (0.0% error, no invalid sequence). The 19% was an artefact of the kit metric (the room anchor of the big concave room jumping), not a real route problem. Door to door our agent picks the same room sequences as the optimum on the original. Fix A (snapping room outlines) was therefore not needed and not tried; `convert.py` is unchanged.
- The clean floors proc-campus-dev-000/001 and resplan-439 are at 0.0% error, 100% of pairs full marks.
- proc-factory-dev-003 has a different problem the kit metric hid: the extraction invented an entrance (outside to F0-S019, and outside to F0-S033) that does not exist in the original. Our router uses `outside` as a free shortcut through it, and 108 of 264 pairs become invalid sequences. Valid pairs are fine. A spurious entrance is worth a validation warning or a check against the real entrances.
- The Swiss floors and the OSM floor fail because doors were not extracted (door recall 0.35, 0.26, 0.67): the extracted building has no route where the original has one. That is an extraction recall problem, not a geometry one. On osm the pairs that do route often score below 0.99 (wrong detours, probably from differing outlines or doors).
- Takeaway: use the judge metric for Level 4 route quality. The remaining route risk is spurious or missing doors, not outline differences.

### Entrance diagnosis (2026-10-24, cached extractions, no API call)

Question: why did proc-factory-dev-003 get entrances the original does not have? The outer boundary is the outline of the union of all room polygons (gaps under 0.3 m closed).

- Original factory-003: 4 entrances (S010, S012, S013, S016), all exactly on the outer boundary.
- Extraction: 6 entrance markers. 4 are on the outer boundary (distance 0.00 m to it): rooms C3, C2 (west wall), B5 (top hall), c16 (corridor, east). 2 are wrong: r33 and r19 (the "Hall access" lobbies). Their markers sit 2.60 m and 2.67 m inside the outer boundary, exactly on the wall these lobbies share with the big hall (A4 resp. A1), distance 0.00 m to that hall.
- So it is not a neighbour mix-up: both lobbies do touch the outside (4.8 m of exterior wall each), the model drew the red marker on the interior wall between lobby and hall. The old converter then snapped the marker to the nearest exterior stretch of the lobby (`point_on_wall(exterior_wall(room))`), which produced a plausible looking but invented entrance and a free `outside` shortcut (108 of 264 pairs invalid).
- Other floors: campus-000/001, resplan-439/1465: all markers 0.00 to 0.04 m from the outer boundary, correct room. swiss-31: 4 markers, 0.09 to 0.39 m off (2 stair rooms and 2 rooms, one touches no room). swiss-203: 4 markers at 0.14 to 0.36 m from the boundary but 0.9 to 1.2 m away from the room they name (they sit in the gap next to a neighbour, door recall of that floor is 0.34 anyway). osm: markers 0.02 to 0.42 m off.
- Original entrances can sit off the union outline too (swiss-2074: 1.27 m, wall faces a gap); that is why the snap radius is 1.5 m and the validator only warns at 0.6 m.

Fix (convert.py `snap_entrance`, validate.py `outer_boundary`): marker farther than 1.5 m from the outer boundary: dropped with `entrance_dropped`; within 1.5 m: snapped to the exterior wall of the room that touches the boundary there (the named room if it does, a neighbour only if the marker is within 0.6 m of the named room, warning `entrance_reattached`); more entrances than max(8, rooms/3): extras dropped. Validator warning `entrance_not_on_outer_wall` (0.6 m). The optional `entrance_markers` count (d) was skipped: extract.py would have to read it and is outside this change.

Before (row 'Judge metric' above) and after (same cached extractions, judge metric, 975 pairs):

| Floor | Invalid before | Invalid after | Judge err mean before | Judge err mean after | No route before | No route after |
|---|---|---|---|---|---|---|
| proc-factory-dev-003:0 | 108 | 0 | 41.4% | 5.8% | 0 | 0 |
| swiss-31:0 | 1 | 1 | 93.6% | 93.6% | 116 | 116 |
| swiss-203:0 | 0 | 0 | 97.4% | 97.4% | 147 | 147 |
| osm-way27326387:0 | 0 | 0 | 33.0% | 33.0% | 23 | 23 |
| All 8 floors | 109 | 1 | 41.3% | 31.7% | 286 | 286 |

### After entrance fix (2026-10-24, same cached extractions, no API call)

| Floor | Rooms found/true | Recall | Precision | Area err (median) | Door recall | Route err (median) | Findings | Unreachable warned | Tokens in/out | Seconds | Cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 28/28 | 1.00 | 1.00 | 0.6% | 1.00 | 0.3% (162) | 0 | no | 1688/2228 | 10.4 | 0.026 |
| proc-campus-dev-001:0 | 22/22 | 1.00 | 1.00 | 0.8% | 1.00 | 0.1% (126) | 0 | no | 1626/1772 | 8.7 | 0.021 |
| proc-factory-dev-003:0 | 47/47 | 1.00 | 1.00 | 0.1% | 0.96 | 0.0% (276) | 1 | no | 2734/3864 | 17.4 | 0.044 |
| resplan-439:0 | 8/8 | 1.00 | 1.00 | 0.6% | 1.00 | 0.2% (42) | 0 | no | 1613/875 | 5.1 | 0.012 |
| resplan-1465:0 | 10/10 | 1.00 | 1.00 | 1.7% | 1.00 | 19.0% (54) | 1 | no | 1613/958 | 7.4 | 0.013 |
| swiss-31:0 | 25/30 | 0.80 | 0.96 | 8.6% | 0.35 | 7.3% (19) | 4 | yes | 1643/2132 | 12.6 | 0.025 |
| swiss-203:0 | 28/36 | 0.78 | 1.00 | 8.6% | 0.26 | 12.2% (7) | 6 | yes | 1667/2262 | 14.3 | 0.026 |
| osm-way27326387:0 | 18/21 | 0.86 | 1.00 | 10.2% | 0.67 | 5.2% (75) | 4 | yes | 1577/1698 | 11.4 | 0.020 |

- Clean (procedural, ResPlan), 5 floors, medians: recall 1.00, precision 1.00, door recall 1.00, area err 0.6%, route err 0.2%, floors with an unreachable-room finding: 0/5
- Swiss, 2 floors, medians: recall 0.79, precision 0.98, door recall 0.31, area err 8.6%, route err 9.8%, floors with an unreachable-room finding: 2/2
- OSM, 1 floors, medians: recall 0.86, precision 1.00, door recall 0.67, area err 10.2%, route err 5.2%, floors with an unreachable-room finding: 1/1
- All 8 floors: median seconds 10.9, median cost 0.023 USD, total 0.186 USD (list price, not checked against an invoice).

| Floor | Kit route err (median) | Judge err (median) | Judge err (mean) | Pairs >= 0.99 | Invalid sequences | No route found | Pairs |
|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 0.3% | 0.0% | 0.0% | 100% | 0 | 0 | 156 |
| proc-campus-dev-001:0 | 0.1% | 0.0% | 0.0% | 100% | 0 | 0 | 120 |
| proc-factory-dev-003:0 | 0.0% | 0.0% | 5.8% | 81% | 0 | 0 | 264 |
| resplan-439:0 | 0.2% | 0.0% | 0.0% | 100% | 0 | 0 | 30 |
| resplan-1465:0 | 19.0% | 0.0% | 0.0% | 100% | 0 | 0 | 40 |
| swiss-31:0 | 7.3% | 100.0% | 93.6% | 6% | 1 | 116 | 125 |
| swiss-203:0 | 12.2% | 100.0% | 97.4% | 3% | 0 | 147 | 151 |
| osm-way27326387:0 | 5.2% | 10.5% | 33.0% | 34% | 0 | 23 | 89 |
| All 8 floors | 2.7% | 0.0% | 31.7% (pair-weighted) | 62% (pair-weighted) | 1 | 286 | 975 |

- Targets on clean floors: room recall met, room precision met, door recall met, area error met, route error met, unreachable on at most 1 of 10 floors met
- Swiss floors with missing rooms or doors that were also warned about: 2/2 (target 100%).

### Door suggestions (2026-10-24, `building_agent/level4/suggest.py`, no API call)

`scripts/eval_suggest.py` proposes doors for rooms with no way out and applies them to a copy. A suggestion counts as real when the original floor has a door between the same two rooms (rooms matched by overlap). "Judge >= 0.99" is the share of room pairs whose route scores at least 0.99 on the original. Reachable is the share of rooms with a way out (validator rule).

**Cached extractions (real vision output, 8 floors)**

| floor | runs | isolated rooms | suggestions | real doors | precision | reachable before | after | judge >= 0.99 before | after |
|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 1 | 0 | 0 | 0 | n/a | 100% | 100% | 100% | 100% |
| proc-campus-dev-001:0 | 1 | 0 | 0 | 0 | n/a | 100% | 100% | 100% | 100% |
| proc-factory-dev-003:0 | 1 | 0 | 0 | 0 | n/a | 100% | 100% | 58% | 58% |
| resplan-439:0 | 1 | 0 | 0 | 0 | n/a | 100% | 100% | 100% | 100% |
| resplan-1465:0 | 1 | 0 | 0 | 0 | n/a | 100% | 100% | 100% | 100% |
| swiss-31:0 | 1 | 19 | 7 | 3 | 43% | 24% | 100% | 6% | 6% |
| swiss-203:0 | 1 | 23 | 14 | 4 | 29% | 18% | 100% | 3% | 6% |
| osm-way27326387:0 | 1 | 2 | 2 | 1 | 50% | 89% | 100% | 34% | 45% |
| all | 8 | 44 | 23 | 8 | 35% | 79% | 100% | 63% | 64% |

| source | runs | isolated rooms | suggestions | real doors | precision | reachable before | after | judge >= 0.99 before | after |
|---|---|---|---|---|---|---|---|---|---|
| procedural | 3 | 0 | 0 | 0 | n/a | 100% | 100% | 86% | 86% |
| resplan | 2 | 0 | 0 | 0 | n/a | 100% | 100% | 100% | 100% |
| swiss | 2 | 42 | 21 | 7 | 33% | 21% | 100% | 5% | 6% |
| osm | 1 | 2 | 2 | 1 | 50% | 89% | 100% | 34% | 45% |
| all | 8 | 44 | 23 | 8 | 35% | 79% | 100% | 63% | 64% |

**Artificial extractions (16 real floors x 3 seeds, 50 percent of the doors dropped, entrances kept)**

| floor | runs | isolated rooms | suggestions | real doors | precision | reachable before | after | judge >= 0.99 before | after |
|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 3 | 39 | 39 | 39 | 100% | 54% | 100% | 22% | 99% |
| proc-campus-dev-001:1 | 3 | 33 | 33 | 33 | 100% | 56% | 100% | 29% | 100% |
| proc-campus-dev-009:0 | 3 | 47 | 47 | 47 | 100% | 51% | 100% | 23% | 99% |
| proc-factory-dev-003:0 | 3 | 50 | 48 | 48 | 100% | 65% | 99% | 26% | 64% |
| proc-factory-dev-004:1 | 3 | 23 | 23 | 23 | 100% | 60% | 100% | 26% | 100% |
| resplan-439:0 | 3 | 10 | 9 | 7 | 78% | 58% | 100% | 30% | 89% |
| resplan-15179:0 | 3 | 17 | 14 | 11 | 79% | 53% | 100% | 17% | 90% |
| resplan-1677:0 | 3 | 18 | 13 | 13 | 100% | 40% | 100% | 14% | 100% |
| resplan-7336:0 | 3 | 14 | 11 | 10 | 91% | 48% | 100% | 9% | 90% |
| swiss-31:1 | 3 | 85 | 52 | 24 | 46% | 17% | 97% | 10% | 34% |
| swiss-2074:0 | 3 | 32 | 21 | 18 | 86% | 37% | 100% | 21% | 65% |
| swiss-450:1 | 3 | 31 | 21 | 18 | 86% | 48% | 100% | 14% | 46% |
| swiss-3254:0 | 3 | 45 | 23 | 17 | 74% | 25% | 100% | 14% | 74% |
| osm-way22744230:0 | 3 | 57 | 47 | 28 | 60% | 57% | 100% | 11% | 28% |
| osm-way27326387:0 | 3 | 32 | 21 | 10 | 48% | 49% | 100% | 15% | 28% |
| osm-way360544293:0 | 3 | 53 | 44 | 41 | 93% | 12% | 100% | 0% | 88% |
| all | 48 | 586 | 466 | 387 | 83% | 46% | 100% | 17% | 75% |

| source | runs | isolated rooms | suggestions | real doors | precision | reachable before | after | judge >= 0.99 before | after |
|---|---|---|---|---|---|---|---|---|---|
| procedural | 15 | 192 | 190 | 190 | 100% | 57% | 100% | 25% | 92% |
| resplan | 12 | 59 | 47 | 41 | 87% | 50% | 100% | 17% | 92% |
| swiss | 12 | 193 | 117 | 77 | 66% | 32% | 99% | 15% | 55% |
| osm | 9 | 142 | 112 | 79 | 71% | 39% | 100% | 9% | 48% |
| all | 48 | 586 | 466 | 387 | 83% | 46% | 100% | 17% | 75% |

In plain words:

- Reachability: after applying the suggestions nearly every room has a way out again (46% to 100% on the artificial floors, 21% to 100% on the cached Swiss floors). That is by construction, it only fails when no neighbour shares a wall of 0.9 m.
- Precision depends on how regular the plan is: procedural 100%, ResPlan 87%, Swiss 66%, OSM 71% on the artificial floors. On the two real cached Swiss floors only 7 of 21 suggestions are real doors (33%), on the cached OSM floor 1 of 2. Wrong suggestions are often a plausible door into the wrong neighbour, so they are proposals, never silent fixes.
- Route quality: on the artificial floors the judge share goes from 17% to 75% (procedural 25% to 92%, ResPlan 17% to 92%, Swiss 15% to 55%, OSM 9% to 48%). On the real cached Swiss floors it stays at 5% to 6%: there the routes fail because rooms are missing or merged in the extraction, not only because of doors. Suggesting doors cannot repair that. OSM cached improves 34% to 45%.
- Fewer suggestions than isolated rooms is expected: one door frees a whole group of rooms behind it.
- What the data said while tuning (same floors as measured, 4 weights, a plateau and not a peak, so mild optimism): the corridor/hall bonus is essential (without it precision falls from 73% to 48%). A bonus for neighbours that already have many doors (corridor proxy when the room type says nothing) raised precision from 73% to 80% (procedural 92% to 100%). More weight on wall length lowered precision (1.5 per metre: 65%), so it only breaks ties. The stair/lift penalty hardly matters (0 vs 5: 74% vs 73%), kept mild. The wet-room penalty helps ResPlan a little. Two fixes mattered more than weights: the shared wall from `convert.shared_wall` is about 0.5 m too long (buffer overshoot, trimmed by 0.4 m, so the 0.9 m rule means 0.9 m), and rooms nested inside a big OSM polygon have no shared outline, so their longest edge is used (OSM reachable 69% to 100%).
- Limits: precision is measured against the original doors only, a wrong-but-reasonable door counts as a miss. Only 3 of the 8 cached floors have isolated rooms. Only same-floor doors are suggested, never stairs or entrances (entrances are the other agent's job).

### Marker detection 2026-10-24 (claude-sonnet-5-5, prompt 9f2a64f5)

| Floor | Door recall (model) | Door recall (+markers) | Pairs >= 0.99 (model) | Pairs >= 0.99 (+markers) | Invalid (model) | Invalid (+markers) | No route (model) | No route (+markers) | Pairs |
|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 1.00 | 1.00 | 100% | 100% | 0 | 0 | 0 | 0 | 156 |
| proc-campus-dev-001:0 | 1.00 | 1.00 | 100% | 100% | 0 | 0 | 0 | 0 | 120 |
| proc-factory-dev-003:0 | 0.96 | 1.00 | 58% | 100% | 108 | 0 | 0 | 0 | 264 |
| resplan-439:0 | 1.00 | 1.00 | 100% | 100% | 0 | 0 | 0 | 0 | 30 |
| resplan-1465:0 | 1.00 | 1.00 | 100% | 100% | 0 | 0 | 0 | 0 | 40 |
| swiss-31:0 | 0.35 | 0.35 | 6% | 5% | 1 | 14 | 116 | 105 | 125 |
| swiss-203:0 | 0.26 | 0.32 | 3% | 5% | 0 | 4 | 147 | 137 | 151 |
| osm-way27326387:0 | 0.67 | 0.74 | 34% | 46% | 0 | 2 | 23 | 0 | 89 |

Detection alone (`building_agent/level4/markers.py`, no model), measured against the markers the kit drew (SVG positions, match within 4 px), 117 dev floors over all four sources, floor_N_plain.png:

| Source | Door recall / precision | Opening recall / precision | Entrance recall / precision |
|---|---|---|---|
| proc (45 floors) | 1.00 / 1.00 (1239) | 1.00 / 1.00 (174) | 1.00 / 1.00 (43) |
| resplan (10) | 1.00 / 1.00 (60) | 1.00 / 1.00 (12) | 1.00 / 1.00 (10) |
| swiss (46) | 0.98 / 1.00 (1330) | 1.00 / 1.00 (195) | 1.00 / 1.00 (43) |
| osm (16) | 1.00 / 1.00 (1894) | 0.92 / 1.00 (50) | 0.96 / 1.00 (135) |

- Colours are exact on every image: door (139,69,19), opening (158,158,158), entrance (211,47,47). Room fills (243,239,230), (207,232,196), (244,177,131), (180,167,214), (255,242,179), (220,220,220) never clash.
- Missed doors (23 on swiss) lie under a red entrance triangle. Missed openings (4 on osm) overlap a door dot. The floor_N.png with furniture gives identical numbers.
- The eval table shows that markers are not the bottleneck on dense plans: the model's rooms are missing or shifted there, so a marker often finds fewer than two matching outlines or the wrong pair (swiss-31: 2 of 27 markers dropped, 5 pairs changed). Where rooms are right, markers fix kinds and positions (factory-003: invented entrances become doors or openings, 108 invalid sequences gone).
- When the outline pair and the model pair disagree the outline pair wins (tested: model pair wins gives factory-003 108 invalid again, swiss-31 only 2 invalid instead of 14, so this trade-off is open for swiss).
- Does not work for plans that draw doors as arcs or leaves, scans, JPEG below quality 90, or images resized after rendering (dots smaller than 4 px or blurred).

### Room segmentation 2026-10-24 (claude-sonnet-5-5, prompt 9f2a64f5)

Segmentation against the true polygons of 122 dev floors (all four sources, no API, truth from the floor svg), then the cached model extractions of the 8 default floors with the combination model -> segment -> markers -> convert -> validate.

| Source | Floors | True rooms | Recall | Precision | IoU median | Area err median | Floors with a missed room | Regions merging 2 true rooms | Seconds median (max) |
|---|---|---|---|---|---|---|---|---|---|
| osm | 19 | 2055 | 0.986 | 0.988 | 0.971 | 0.8% | 8 | 9 | 0.13 (1.19) |
| procedural | 45 | 1402 | 1.000 | 1.000 | 0.977 | 0.6% | 0 | 0 | 0.04 (0.23) |
| resplan | 10 | 81 | 1.000 | 1.000 | 0.968 | 1.1% | 0 | 0 | 0.02 (0.03) |
| swiss | 48 | 1606 | 1.000 | 0.992 | 0.939 | 3.1% | 0 | 0 | 0.04 (0.17) |
| all | 122 | 5144 | 0.995 | 0.993 | 0.967 | 1.1% | 8 | 9 | 0.04 (1.19) |

| Floor | Variant | Room recall | Door recall | Pairs >= 0.99 | Invalid | No route | Pairs |
|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | model | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | model + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | model + markers | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | model + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | segment | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | segment + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | segment + markers | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-000:0 | segment + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 156 |
| proc-campus-dev-001:0 | model | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | model + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | model + markers | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | model + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | segment | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | segment + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | segment + markers | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-campus-dev-001:0 | segment + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 120 |
| proc-factory-dev-003:0 | model | 1.00 | 0.96 | 81% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | model + suggest | 1.00 | 0.96 | 81% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | model + markers | 1.00 | 1.00 | 100% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | model + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | segment | 1.00 | 0.96 | 81% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | segment + suggest | 1.00 | 0.96 | 81% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | segment + markers | 1.00 | 1.00 | 100% | 0 | 0 | 264 |
| proc-factory-dev-003:0 | segment + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 264 |
| resplan-439:0 | model | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | model + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | model + markers | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | model + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | segment | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | segment + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | segment + markers | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-439:0 | segment + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 30 |
| resplan-1465:0 | model | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | model + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | model + markers | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | model + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | segment | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | segment + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | segment + markers | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| resplan-1465:0 | segment + markers + suggest | 1.00 | 1.00 | 100% | 0 | 0 | 40 |
| swiss-31:0 | model | 0.80 | 0.35 | 6% | 1 | 116 | 125 |
| swiss-31:0 | model + suggest | 0.80 | 0.45 | 6% | 117 | 0 | 125 |
| swiss-31:0 | model + markers | 0.80 | 0.35 | 5% | 14 | 105 | 125 |
| swiss-31:0 | model + markers + suggest | 0.80 | 0.42 | 5% | 119 | 0 | 125 |
| swiss-31:0 | segment | 1.00 | 0.58 | 6% | 0 | 149 | 159 |
| swiss-31:0 | segment + suggest | 1.00 | 0.74 | 8% | 146 | 0 | 159 |
| swiss-31:0 | segment + markers | 1.00 | 0.87 | 9% | 0 | 145 | 159 |
| swiss-31:0 | segment + markers + suggest | 1.00 | 0.87 | 9% | 145 | 0 | 159 |
| swiss-203:0 | model | 0.78 | 0.26 | 3% | 0 | 147 | 151 |
| swiss-203:0 | model + suggest | 0.78 | 0.37 | 6% | 142 | 0 | 151 |
| swiss-203:0 | model + markers | 0.78 | 0.32 | 5% | 4 | 137 | 151 |
| swiss-203:0 | model + markers + suggest | 0.78 | 0.34 | 5% | 140 | 0 | 151 |
| swiss-203:0 | segment | 1.00 | 0.32 | 3% | 1 | 193 | 200 |
| swiss-203:0 | segment + suggest | 1.00 | 0.53 | 6% | 188 | 0 | 200 |
| swiss-203:0 | segment + markers | 1.00 | 0.89 | 19% | 0 | 108 | 200 |
| swiss-203:0 | segment + markers + suggest | 1.00 | 0.89 | 19% | 108 | 0 | 200 |
| osm-way27326387:0 | model | 0.86 | 0.67 | 34% | 0 | 23 | 89 |
| osm-way27326387:0 | model + suggest | 0.86 | 0.70 | 45% | 5 | 0 | 89 |
| osm-way27326387:0 | model + markers | 0.86 | 0.74 | 46% | 2 | 0 | 89 |
| osm-way27326387:0 | model + markers + suggest | 0.86 | 0.74 | 46% | 2 | 0 | 89 |
| osm-way27326387:0 | segment | 1.00 | 0.67 | 22% | 14 | 54 | 108 |
| osm-way27326387:0 | segment + suggest | 1.00 | 0.70 | 33% | 55 | 0 | 108 |
| osm-way27326387:0 | segment + markers | 1.00 | 0.96 | 89% | 0 | 6 | 108 |
| osm-way27326387:0 | segment + markers + suggest | 1.00 | 1.00 | 94% | 0 | 0 | 108 |

- Segment alone lifts room recall on the cached floors (swiss 0.80/0.78, osm 0.86 to 1.00) but not routes: added rooms have no doors. Segment + markers is what pays off: osm pairs >= 0.99 34% to 89% (94% with suggestions), swiss-203 3% to 19%, swiss-31 6% to 9%, invalid sequences 0 everywhere, clean floors unchanged. Suggestions only turn no-route into invalid on swiss (guessed doors that do not exist).
- Swiss limit: the doors between apartment and stairwell are not drawn in the plain image, so no marker finds them (diagnosed on swiss-31: 5 of 31 true openings missing, 4 of them stairwell doors).
- Segmentation limits: same-coloured rooms with no wall drawn between them (osm-way360544293, grey rooms inside a grey hall) cannot be separated; closets of about 10 px under door dots are lost; fills that are not flat (hatching, photos) are skipped via the fill-share guard. Swiss polygons run about 3% large (rotated walls are wider, IoU median 0.94).

### Live test: two floors, furniture, other style (2026-10-24, claude-sonnet-5-5, prompt 9f2a64f5)

Real vision calls through the real conversation tools (`build_from_plan`, `preview_draft`, `save_building`, same Rig wiring as `tests/test_level4_tools.py`), script `scripts/level4_live_test.py`. 11 vision calls, 0.240 USD in total (list price, not checked against an invoice), limits were 20 calls and 1.00 USD. The scale is the true floor width per call. No pipeline code was changed. Cached extractions: `agent_output/level4_cache/live_*`.

#### A. Two floors (level 0 then level 1 from `floor_N_plain.png`, then card, then save)

Per floor, against the original floor (same measures as the single-floor eval):

| Building:floor | Rooms found/true | Doors found/true | Entrances found/true | Area err (median) | Judge pairs >= 0.99 | Judge invalid / no route | Seconds | Cost USD |
|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000:0 | 28/28 | 27/27 | 2/2 | 0.5% | 100% (156) | 0 / 0 | 10.3 | 0.0254 |
| proc-campus-dev-000:1 | 31/31 | 30/30 | 0/0 | 0.6% | 100% (174) | 0 / 0 | 11.0 | 0.0269 |
| swiss-1785:0 | 35/35 | 36/35 | 2/2 | 3.0% | 99% (197) | 0 / 0 | 15.4 | 0.0263 |
| swiss-1785:1 | 35/35 | 36/35 | 0/0 | 2.7% | 94% (87) | 0 / 0 | 17.3 | 0.0248 |
| osm-way360544293:0 | 9/20 | 0/18 | 7/7 | 0.7% | 0% (35) | 0 / 35 | 6.3 | 0.0186 |
| osm-way360544293:1 | 11/19 | 0/18 | 8/11 | 1.3% | 0% (40) | 0 / 40 | 9.3 | 0.0190 |

swiss-1785 was picked as the multi-floor Swiss building with stairs and a lift between levels 0 and 1. The first pick, osm-way360544293 (8 lifts), is the known hard OSM case (see the segmentation limits above), so it is reported as a second data point. Floor widths used as known length: proc 14.4 m, swiss 26.0 m on both floors, osm 260 m and 288 m.

After saving and loading the building (`BuildingMap.load`): cross-floor routes between matched rooms of level 0 and level 1 with `routing.route`, scored with the judge rule (best length on the original / length of our room sequence, mapped back to original ids):

| Building | Floors saved | Connectors original (0-1) | Connectors created | Cross-floor pairs | Pairs >= 0.99 | No route | Invalid | Step-free pairs reached by our route |
|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000 | 2 | 6 (3 stairs, 3 lifts) | 0 | 292 | 0% | 292 | 0 | 0 of 292 |
| swiss-1785 | 2 | 3 (2 stairs, 1 lift) | 0 | 350 | 0% | 350 | 0 | 0 of 225 (125 more pairs are not step-free in the original either) |
| osm-way360544293 | 2 | 8 (lifts) | 0 | 96 | 0% | 96 | 0 | 0 of 90 |

Result: all three buildings loaded with 2 floors and the right room counts, but no stairs or lifts were created, so there is no route between the floors at all, step-free included. Reason: the vision model typed every numbered stair and lift room as `room` (proc, swiss), and Swiss and OSM plans have no separate stair shape (numbered "stair hall" corridors). Connectors are only linked between rooms typed `stair` or `lift` (`convert._link_connectors`). Extraction of proc floor 0: 27 `room`, 1 `corridor`, no `stair`, no `lift`.

What the person sees, proc as the example:
- After the second `build_from_plan`: "31 rooms have no way out, doors are probably missing: 1.01, 1.02, ..." (floor 1 has no entrance of its own, floor 0 has two). The card has `can be saved: false` and "saving blocked".
- `save_building` with "yes, save it" is refused (correctly) because of that error. Saving needs `accept_problems` and a reply with "anyway". After that the building is saved and active, with no way between the floors and no warning about missing stairs. The text blames missing doors, not missing stairs or lifts.
- No `connector_single_floor` finding appears, because no room was typed as stair or lift.
- Fix attempt: `fix_draft set_room_type` for all true stair and lift rooms (0.04, 1.04, 0.05, 1.05, ...) answers "0.04 is now a stairwell." each time, but the draft still has 0 connectors and the same "no way out" problem (swiss: the same). The fix changes only `room_type`, the linking reads the extraction `type`, so it cannot repair this, while the reply sounds like success.

Upper bound (not what the person gets): the same cached extractions with the true stairs and lifts retyped as `stair` and `lift` (matched by ref and level), then the real tools again, no API call:

| Building | Connectors created / original | Cross-floor pairs >= 0.99 | No route | Invalid | Step-free pairs >= 0.99 | Our length / original `route` length (median, max) | Card |
|---|---|---|---|---|---|---|---|
| proc-campus-dev-000 | 6 / 6 (kinds right) | 100% (292) | 0 | 0 | 100% (292) | 0.95 (0.98), step-free 0.98 (0.99) | No problems found, plain yes saves |
| swiss-1785 | 1 / 3 | 31% (350) | 240 | 0 | 0% (0 of 225) | 0.99 (1.01) | "1 stair or lift could not be matched to a room on another floor: 1.34", 20 rooms with no way out, blocked |

So conversion and routing across floors work when the types are right (proc: every pair full marks, the step-free route over the lift works, our lengths are 2 to 5% shorter than the kit `route` because of the door-to-door model, the judge rule gives full marks). The Swiss case is only partly a typing problem: the true building hangs a stair and a lift on the same stair-hall space, and the hall number changes per floor (0.35, 1.34, 2.30), so ref-based linking links one connector. For osm the upper bound was not possible (no usable refs). Floor images are cropped per floor (osm 1387 and 936 px wide, proc 276 and 275), so overlap linking (`MIN_STAIR_OVERLAP`) depends on aligned frames; harmless on proc (1 px), untested on osm.

OSM findings the person would also see (known extraction limits): 9 of 20 rooms on floor 0, 0 doors (5 door and 13 opening markers found but dropped with "does not join two rooms (0 rooms within 8 px)", the merged rooms are too big), "the building would be an unlikely size, the scale is probably wrong" and "4 rooms have an unlikely size" although the 260 m wide building is real, 17 pairs of overlapping rooms, 3 entrance markers left out. The image was downscaled from 1387x3119 to 1334x3000 px. The card proposed 17 doors.

#### B. Plans with furniture (`floor_0.png` against `floor_0_plain.png`, level 0, true width as known length)

| Building | Image | Model rooms/openings (before segment, markers) | Segments (fill share) | Markers door/opening/entrance | Rooms found/true | Doors found/true | Entrances found/true | Area err (median) | Judge pairs >= 0.99 | Seconds | Cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| proc-campus-dev-000 | plain | 28/29 | 28 (0.945) | 27/0/2 | 28/28 | 27/27 | 2/2 | 0.5% | 100% (156) | 10.3 | 0.0254 |
| proc-campus-dev-000 | furniture | 28/25 | 28 (0.829) | 27/0/2 | 28/28 | 27/27 | 2/2 | 2.7% | 100% (156) | 10.0 | 0.0247 |
| resplan-439 | plain | 8/8 | 8 (0.935) | 6/1/1 | 8/8 | 7/7 | 1/1 | 1.0% | 100% (30) | 5.1 | 0.0120 |
| resplan-439 | furniture | 8/8 | 8 (0.785) | 6/1/1 | 8/8 | 7/7 | 1/1 | 1.3% | 100% (30) | 5.1 | 0.0120 |

- Colour segmentation still works with furniture. The furniture colours (tan, blue, green pieces) did not become extra rooms (28 and 8 regions in both versions, no `room_added_from_image`). The flat-fill share drops from 0.95 to 0.83 and from 0.94 to 0.79 but stays far above the 0.5 guard. Marker detection finds exactly the same doors, openings and entrances as on the plain image (no false markers from furniture). Scale handling is identical (0.072 and 0.0386 m/px, same known length).
- What changes: the model alone misses 4 of 27 doors on the proc furniture plan (23 doors, 2 entrances), the markers repair all of them (27/27). The median room area error rises from 0.5% to 2.7% on proc (1.0% to 1.3% on resplan). Not diagnosed; probably furniture ink inside the fills shrinks or notches the segmented outlines. Routes are not affected (judge 100%, 0 invalid).
- The two resplan answers (plain and furniture) have identical counts; they are two separate calls (two cache files, slightly different token costs).

#### C. Other drawing style (negative control, floor 0 of proc-campus-dev-000, palette swapped with PIL)

| Image | Segments (fill share) | Markers door/opening/entrance | Card notes | Rooms found/true | Doors found/true | Entrances found/true | Area err (median) | Judge pairs >= 0.99 | Seconds | Cost USD |
|---|---|---|---|---|---|---|---|---|---|---|
| original | 28 (0.945) | 27/0/2 | none | 28/28 | 27/27 | 2/2 | 0.5% | 100% (156) | 10.3 | 0.0254 |
| inverted colours | 0 (0.003), not usable | 0/0/0 | "segmentation_skipped: no regions" | 28/28 | 27/27 | 2/2 | 0.6% | 100% (156) | 10.8 | 0.0254 |
| greyscale | 25 (0.904), usable | 0/0/0 | 3 x "room_without_region: ... keeps the model polygon" | 28/28 | 27/27 | 2/2 | 0.6% | 100% (156) | 13.7 | 0.0251 |

- Clean fallback, no crash. Inverted: no flat fill is found, segmentation is skipped with a note on the card, marker detection finds nothing (silently, no note), the model polygons and doors are used. Greyscale: the fills are learned as extra colours (`fill_c0c0c0`, `fill_efefef`), 25 of 28 rooms get a region, 3 keep the model polygon (noted), the brown door dots turn dark grey and are not found as markers.
- Quality is as good as the original (28/28, 27/27, 2/2, area error 0.6%) because the model reads the recoloured plan as well as the original and this plan is simple and clean. This is a palette swap, not a real other style (line drawing, photo, hatching). It shows the fallback is safe, not that arbitrary plans work. The swiss and osm runs above (rooms 9/20, 0 doors on osm) show what happens on harder plans.

#### Defects found (report only, nothing fixed)

| # | Severity | Defect |
|---|---|---|
| 1 | High | Two-floor builds create no stairs or lifts (0 of 6, 0 of 3, 0 of 8), so there is no route between floors at all, step-free included. The vision model types numbered stair and lift rooms as `room`, the linker needs `stair` or `lift`. No fallback by name, ref, colour or by asking. |
| 2 | High | `fix_draft set_room_type` ("stairwell", "lift") cannot repair it: it answers "is now a stairwell" but changes only `room_type`, connectors are built from `type` in the conversion, so the connector count stays 0 and the problem stays. A silent no-op that looks like success. |
| 3 | High | Misleading card: floors above the entrance level without connectors give "N rooms have no way out, doors are probably missing", saving is blocked, and the person can only save with "save anyway". There is no message like "no stairs or lifts between the floors found, which rooms are the stairs?". |
| 4 | Medium | Stair halls (swiss, osm): stairs and lift hang on the same corridor-typed hall, with a different number per floor. A stair or lift cannot be its own room there, so even correct typing links 1 of 3 (swiss-1785). |
| 5 | Medium | The unlikely-size check fires on real large buildings (osm 260 m and 288 m wide) and blocks saving, although the person gave the length. |
| 6 | Medium | Floor frames are not aligned (each image has its own crop, osm 1387 vs 936 px). Overlap linking of stairs would fail there, ref linking needs equal numbers. Untestable because of defect 1. |
| 7 | Low | Furniture raises the median area error from 0.5% to 2.7% (proc), and the model alone misses 4 of 27 doors (markers repair them). Not diagnosed. |
| 8 | Low | A plan where marker detection finds nothing (inverted, greyscale) gives no card note, so the person does not learn that door checking ran on the model alone. |
| 9 | Known | OSM floors: 9/20 rooms and 0 doors found (markers dropped as "0 rooms within 8 px"), as in the segmentation limits above. |

#### What this implies

- The single-floor numbers do not carry over to buildings: with 100% rooms and doors on both floors the person still gets a building without stairs, which can only be saved with "save anyway", and every cross-floor question fails. With the stairs typed right the same pipeline gives 100% cross-floor routes (proc, 292 pairs, step-free included), so the gap is the typing and the repair path, not routing.
- Next steps in this order: (1) when 2 or more floors have no connector, ask on the card which rooms are the stairs and lifts, and make `set_room_type` with a stair or lift type set `type` and relink (test: two-floor draft, `fix_draft`, then `vertical_connectors` is not empty, currently red); (2) say "no stairs or lifts found between the floors" instead of "doors missing", and do not count upper floors as "no way out" before connectors exist; (3) let the prompt and the linker also use name and ref hints ("stair", "lift", "Treppe", "Aufzug"); (4) decide how stair halls with stairs and a lift on one space are represented; (5) relax the unlikely-size check when the person gave the length themselves.
- Reproduce (cached, no API cost): `uv run python scripts/level4_live_test.py a --building proc-campus-dev-000` (also `swiss-1785`, `osm-way360544293`), `b --building resplan-439`, `c --building proc-campus-dev-000 --mode invert`. A changed image or prompt costs about 0.01 to 0.03 USD per floor and needs the key via `uv run --env-file`.

#### After connector fixes (2026-10-24, same cached extractions, no API call)

Code: `building_agent/level4/convert.py` (`detect_connector`, `relink_connectors`, `tag_fills`), `validate.py`, `tools.py` (`fix_draft` `link_floors`, questions), one optional field `ExtractedRoom.fill`. Reproduce: the same three `level4_live_test.py a` commands (cached). New tests: `tests/test_level4_connectors.py` (36, offline; the three cached-real tests skip when `agent_output/level4_cache` is missing).

What the cached model answers contain (this decided the design): stairs and lifts have no name at all, only numbers like 0.04 (the plain image prints only numbers). In the proc plan stairs are orange and lifts purple (the kit palette; orange or purple is present on all 45 proc dev floors, on 17 of the 18 osm floors that have stairs or lifts and on the one resplan floor with stairs, and on no floor without them; checked per image, not per room). So the fill colour of the region (segmentation) is the only hint for proc. Swiss and OSM halls are grey like any corridor and carry no hint at all, so nothing is detected there and the person is asked.

| Building | Connectors created (before / after) / original | Cross-floor pairs at full marks (before / after) | Step-free pairs at full marks (before / after) | Card (after) |
|---|---|---|---|---|
| proc-campus-dev-000 | 0 / 6 of 6 | 0 of 292 / 292 of 292 | 0 of 292 / 292 of 292 | no blocking problem, a warning lists the 12 rooms taken as stairs or lift by colour, plain "yes, save it" saves |
| swiss-1785, as built | 0 / 0 of 3 | 0 of 350 / 0 of 350 | 0 of 225 / 0 of 225 | "I found 2 floors but no stairs or lifts between them. Which rooms are the stairs and lifts?" plus a question listing candidate halls (floor 0: 0.35, 0.34, 0.10, ...), 15 rooms without a way out (was 69 counted globally) |
| swiss-1785, after the person answers with `link_floors` (0.35/1.34 stairs, 0.35/1.34 lift, 0.35/1.35 stairs) | 3 of 3 | 350 of 350 | 225 of 225 | length ratio to the kit route 0.99 (max 1.01) |
| osm-way360544293 | 0 / 0 of 8 | 0 of 96 / 0 of 96 | 0 of 90 / 0 of 90 | no crash, "no stairs or lifts between them" error plus question, no wrong links; "unusual size for the length you gave" is now a warning, saving is still blocked by the 17 overlapping rooms and other known OSM errors |

- proc is the measured upper bound, reached without any oracle: 6 of 6 connectors with the right kinds, 292 of 292 pairs at full marks, 292 of 292 step-free over the lift, our length 0.95 (0.98) of the kit `route` length, step-free 0.98 (0.99).
- The swiss as-built row stays at 0 because the extraction has nothing to detect. With artificial extractions of the true swiss floors that name the halls ("Stair hall 0.35", test `test_swiss_stair_hall_links_stairs_and_asks_for_the_lift`) the stairs link and a `lift_not_found` question is asked: a hall space is never turned into a lift that nobody named. The row with `link_floors` shows the repair path works for hall numbers that differ per floor. The script's `connectors_recovered` reads 1 of 3 there only because the three original connectors share two stop rooms, the routes are all at full marks.
- Stale in the JSON: `oracle_types` of swiss (retyping by ref cannot express stairs and lift on one hall).

Defects of the list above:

| # | Status |
|---|---|
| 1 No connectors on two-floor builds | Fixed where the plan carries a hint (proc: colour or name). Not fixable from the image alone for swiss and osm halls; the person is asked and answers with `set_room_type` or `link_floors`. |
| 2 `set_room_type` stairwell/lift is a silent no-op | Fixed: sets `type` and relinks, the reply says how many connectors exist. Taking the type back (office) unlinks. |
| 3 Card blames missing doors | Fixed: `no_vertical_connectors` replaces per-room "no way out" for upper floors, reachability is computed per floor when no connector exists. Saving such a draft needs "save it anyway". |
| 4 Stair halls with different numbers per floor | Partly: overlap (of the smaller room, 30 percent), then centred floors (warning `connector_aligned_by_centre`), then one stair or lift per floor (warning `connector_linked_by_order`). A hall that holds stairs and lift is linked twice via `link_floors`, or automatically only when its name says both. Nothing is detected without a hint. |
| 5 Size check blocks large real buildings | Fixed for a length the person gave (warning `scale_unusual_known`); the error stays for a printed scale bar and for a door width used as ruler. |
| 6 Floor frames not aligned | Handled for stair and lift matching only (centre of all rooms, warned). Not tested on a real cropped pair (osm has no detectable lifts). |

### Swiss stair doors and SVG check 2026-10-24 (no API)

SVG check (all 48 Swiss dev floors, `floor_<n>.svg` next to the png, matplotlib output):
- The svg holds room patches (stroke #333333, fill by class: room #f3efe6, balcony #cfe8c4, stairwell and corridor both #dcdcdc), furniture patches (opacity 0.75), the markers as `line2d` points (door #8b4513, opening #9e9e9e, entrance #d32f2f) and room refs as comments (`<!-- 1.01 -->`, no text elements, only for about 4 of 5 rooms). No groups with ids or classes beyond matplotlib's running numbers, no hidden or white elements, no stair symbols, no stair hall label (a landing is a plain grey patch).
- Every true opening is drawn as a marker: 1634 of 1634 building.json openings match an svg marker within 4 px, including all 266 that touch a stairwell. So the stairwell doors are drawn (also in the plain png: detect_markers finds them). The eval log line "not drawn" above is wrong for swiss-31:0: the 4 missing doors (kitchen or corridor to landing) are detected but merge_markers keeps the outline pair, and with the model's rooms that pair is another one ("The model joined r17 and r21 ... but the outlines say r21 and r24").
- Extra information in the svg compared with the png: exact room polygons (png segmentation: IoU median 0.94 on swiss) and marker positions to the pixel (png: 98% recall). Nothing else.
- A deterministic reader (two nearest outlines per marker, entrance = nearest outline plus outside) finds 1632 of 1634 true doors (99.9%, 0 invalid; the 2 misses are swiss-5097 floors -1 and 0) and all 48 floors have the right room count. Implemented as `building_agent/level4/svg_read.py` (optional, not wired in; only useful if the Sunday input carries a kit-style svg, which is unknown).

Stair hall rule (`building_agent/level4/stair_doors.py`), `uv run python scripts/eval_suggest.py --stairs`. Artificial floors: every Swiss floor with all doors that touch a stair or lift space dropped (entrances stay), precision = suggested door equals a real door by room pair. Dev 48 floors, train 361 floors (85 buildings).

| Source | Variant | Suggestions | Real | Precision | Dropped doors restored | Judge >= 0.99 before | after |
|---|---|---|---|---|---|---|---|
| dev | generic suggest_doors | 230 | 124 | 54% | 56% | 36% | 59% |
| dev | stair rule | 138 | 138 | 100% | 62% | 36% | 61% |
| dev | stair, then generic | 233 | 145 | 62% | 65% | 36% | 63% |
| train | generic suggest_doors | 1380 | 752 | 54% | 53% | 33% | 55% |
| train | stair rule | 774 | 760 | 98% | 54% | 33% | 54% |
| train | stair, then generic | 1397 | 871 | 62% | 62% | 33% | 61% |

- Precision target 0.9 met (100% dev, 98% train). The rule only proposes a door when a stair hall (type stair or lift, room_type stairwell or lift, or a name like Treppenhaus, stair, landing) is the neighbour, one per room group, at most 3 per hall, living room before kitchen, corridors before plain rooms, wet rooms and balconies last. The weights were tuned on train, dev stayed untouched until the final run.
- Recall is capped at about 54 to 62%: of the dropped doors about 11% are landing to landing doors (a landing next to a landing, no apartment involved) and the rest are apartments that already have a second door to the stair side or a cluster that lost its hall to another one (not analysed further). The judge gain is largest on the ground floors (swiss-31:0 9 to 100%, swiss-203:0 17 to 100%, swiss-2074:0 28 to 100%); on upper floors the landing to landing doors are missing, so the gain is 5 to 10 points.
- The generic rule on its own already reaches 59% (dev) because any door that connects a cluster to the rest lifts the judge pairs a bit, even a wrong one; the stair rule is the same judge result with 100% instead of 54% precision, and stair then generic is best (63% and 61%).
- Cached real extractions (segment + markers): no gain. swiss-31:0 and swiss-203:0 judge pairs stay at 9% and 19% with the stair rule (0 suggestions on swiss-203:0, 2 wrong ones on swiss-31:0 if entrance rooms are treated as halls, which is why that was left out). In swiss-203:0 the 4 missing true doors are the landing to outside entrances, which the pairing attaches to other rooms; in swiss-31:0 they are the 4 kitchen or corridor to landing doors, the model gave no types that identify the landings. Target "clear gain on swiss-31 and swiss-203" is not reached on the real extractions; the cause is the marker pairing on imperfect rooms, not the missing door.
- osm and the clean floors: the rule does nothing (no stair hall without a door, 0 suggestions), unchanged numbers.
