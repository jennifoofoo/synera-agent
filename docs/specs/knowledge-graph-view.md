# Knowledge graph view (twin)

## Goal
Show for the pitch that the building is a real, typed, temporal knowledge graph: the room card gets a "Knowledge"
button that opens an ego graph of that room (plain SVG, no library), built from `GET /api/graph?key=` (JSON-LD,
Brick/RealEstateCore). A time slider shows how place knowledge appears and disappears; "Export as AAS" downloads the
Asset Administration Shell export. Frontend only, no backend change.

## Behaviour
- Centre: the room (Synera blue). Ring 1: assets located in it (machines, equipment, fixtures, then furniture) plus
  doors/openings and lifts/stairs that connect it; at most 16, the rest as one "+N" node.
- Ring 2: facts (notes, issues, closures) anchored at the room or at a ring 1 node. Resolving facts (`resolves`) are
  not drawn. Outer ring: the persons who reported them (`reportedBy`).
- Each node shows a short label and its main Brick/REC type as a tag (e.g. `brick:Fire_Extinguisher`).
- Time: one fetch with `at = slider max`; the facts are filtered client-side. At time t a fact is hidden if
  `validFrom > t`; it is open if `validTo` is empty or later than t; otherwise it has ended. Ended facts are hidden,
  or drawn faded when "Show ended" is on. Closures carry the closed language (danger stroke and bar).
- Slider range: oldest `validFrom` of the room's facts (or now - 1 day) to now + 3 days, 1 hour steps.
- Desktop: side panel on the right. Phone (390 px): bottom sheet. Reduced motion: no transitions.

## Acceptance criteria
1. Selecting a room shows a "Knowledge" button in its card; it opens the panel with the room in the centre.
2. A note seeded on a machine in that room is drawn with an edge to the machine and to its reporter.
3. A note with `valid_to` tomorrow is visible now and disappears when the slider is moved past tomorrow.
4. "Export as AAS" links to `/api/graph?key=<key>&format=aas` with a download name.
5. The panel fits 390 px wide without horizontal overflow; the existing mobile and overlap tests stay green.

## Test cases
- vitest `knowledgeGraph.test.ts`: ego graph from a small JSON-LD (centre, ring 1 cap with "+N", doors via
  `connects`, fact via asset anchor, person via `reportedBy`); `factStateAt` for open / ended / future / resolving.
- e2e `tests/e2e/test_knowledge_graph.py`: seed facts via POST, open the panel for the room, see the note nodes,
  move the slider to +2 days and the expiring note is gone, AAS link has `format=aas`.
