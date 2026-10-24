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
