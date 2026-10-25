# Knowledge graph view (twin)

## Goal
Show for the pitch that the building is a real, typed, temporal knowledge graph. The audience is the planner on a
laptop (facility manager, pitch), not the technician. The technician on the phone uses "What's here?" (notes and
photos, read aloud while guiding); the graph would be overkill there. The room card gets a "Knowledge" button that opens an ego graph of that room (plain SVG, no library), built from `GET /api/graph?key=` (JSON-LD,
Brick/RealEstateCore). A time slider shows how place knowledge appears and disappears; "Export as AAS" downloads the
Asset Administration Shell export. Frontend only, no backend change.

## Behaviour
- The "Knowledge" button shows only in the planner profile (laptop, never phone/worker) and only for a room with at
  least one note or issue (now or in its history). Without notes it is not rendered.
- Centre: the room (Synera blue). Ring 1: only what carries a note, plus lifts/stairs that connect the room; every
  other asset or door collapses into one "+N more" node, which opens as a plain text list under the graph. A room
  whose notes are all hidden at the slider time shows its 6 most relevant things (lifts/stairs, doors, safety
  devices first) with names and the rest as "+N more".
- Labels are never cut with "...": up to two lines, outside the node (left of nodes on the left half, right on the
  right half). Radii and viewBox follow the number of nodes, so a small graph is compact.
- Ring 2: facts (notes, issues, closures) anchored at the room or at a ring 1 node. Resolving facts (`resolves`) are
  not drawn. Outer ring: the persons who reported them (`reportedBy`).
- Each node shows a short label and its main Brick/REC type as a tag (e.g. `brick:Fire_Extinguisher`).
- Time: one fetch with `at = slider max`; the facts are filtered client-side. At time t a fact is hidden if
  `validFrom > t`; it is open if `validTo` is empty or later than t; otherwise it has ended. Ended facts are hidden,
  or drawn faded when "Show ended" is on. Closures carry the closed language (danger stroke and bar).
- Slider range: oldest `validFrom` of the room's facts (or now - 1 day) to now + 3 days, 1 hour steps.
- Desktop: side panel on the right. Phone (390 px): bottom sheet. Reduced motion: no transitions.

## Acceptance criteria
1. Selecting a room with notes shows a "Knowledge" button in its card on the laptop (none on the phone, none for a
   room without notes); it opens the panel with the room in the centre.
2. A note seeded on a machine in that room is drawn with an edge to the machine and to its reporter.
3. A note with `valid_to` tomorrow is visible now and disappears when the slider is moved past tomorrow.
4. "Export as AAS" links to `/api/graph?key=<key>&format=aas` with a download name.
5. The panel fits 390 px wide without horizontal overflow; the existing mobile and overlap tests stay green.

## Test cases
- vitest `knowledgeGraph.test.ts`: ego graph from a small JSON-LD (centre, ring 1 collapse with "+N more", no-notes fallback, doors via
  `connects`, fact via asset anchor, person via `reportedBy`); `factStateAt` for open / ended / future / resolving.
- e2e `tests/e2e/test_knowledge_graph.py`: seed facts via POST, open the panel for the room (planner viewport), see the note nodes,
  move the slider to +2 days and the expiring note is gone, AAS link has `format=aas`.
