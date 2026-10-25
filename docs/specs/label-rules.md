# Spec: when which map label shows (Leonie, Sunday ~05:30)

Problem (Leonie): it feels random when room names, areas and machine names appear or disappear. Jennifer pointed to fixed rules from cartography. This spec writes them down so Jennifer's design session and Leonie's sessions work from the same rules.

## Rules from cartography (what map apps follow)
1. **Fixed priority:** every label has a rank. On overlap the higher rank always wins, never the one that happened to be drawn first.
   Our ranks, high to low: destination of the route > "you are here" > tapped/selected room > current round stop > route landmarks (rooms the steps name) > areas/zones (largest rooms) > POI symbols (exit, WC, lift, stairs) > room names > machine names > furniture.
2. **Fixed zoom tiers:** each kind of label has a zoom range where it may show (already in `twin/src/scene/mapZoom.ts`: far = zones and POIs; mid = all room names; near = machine names). A label never shows outside its range.
3. **Töpfer's radical law:** the number of labels grows only with the square root of the scale change. Zooming in twice as far may show about 1.4 times as many labels, not twice as many. Use it as a cap per tier (density budget per screen area).
4. **Hysteresis:** a label that is shown stays shown until it is clearly out of its range or clearly covered (for example 15 % more zoom or a few pixels more overlap than the threshold that hides it). This stops labels flickering at a boundary.
5. **Stable placement:** what stays the same when the map only pans or rotates must not appear or disappear. Collision and density are decided per zoom step, not per frame.

## What we do today (main, Sunday ~05:30)
- Rules 1 and 2 exist: priority order and fixed tiers in `Labels.tsx` / `mapZoom.ts` (area, far, mid, near by metres per pixel). Zoom-tier hysteresis exists too (`HYSTERESIS` in `mapZoom.ts`).
- **Why it still feels random (checked in code):** (a) in the mid tier a room name shows only if it fits inside its room at that scale (`FIT_OVERFLOW`), so visibility depends on room size, not importance; (b) in 3D the tier is measured at the floor centre, so tilting or rotating changes metres per pixel and flips tiers without zooming; (c) `Declutter.tsx` re-measures overlaps about every 90 ms on any camera move.
- `scene/Declutter.tsx` (Jennifer, "hide overlapping map labels measured on screen") measures overlaps on screen **on every camera change**, so panning or rotating hides and shows labels: this breaks rule 5 and makes it feel random.
- No hysteresis for the overlap test, no density cap (rule 3).

## Change (branch `feat/twin-label-rules`)
- Decide visibility only when the zoom step changes (and when the set of candidate labels changes: route, selection, floor), not on pan/rotate. Between those events the visible set stays fixed.
- Hysteresis on the overlap test (zoom tiers already have it).
- Replace "fits inside its room" by priority + density cap per tier.
- In 3D take the tier from zoom (camera distance), not from tilt/rotation.
- Priority order exactly as in rule 1, one shared list used by `Labels.tsx` and `Declutter.tsx`.
- Density cap per tier (rule 3), counted per screen area.
- Keep: no overlaps ever (the overlap test still runs, but only at the decision points above), destination label biggest, existing e2e tests (`tests/e2e/test_semantic_zoom.py`, overlap audit) green.
- No styling changes (Jennifer's design session owns the look).
