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
