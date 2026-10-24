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
