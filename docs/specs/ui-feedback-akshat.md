# UI feedback (Akshat, Saturday night) and what follows from it (Leonie)

Status: input for the next UI pass. Jennifer's `ui-polish` (in `main`) already covers part of it; the team does not like the current look yet, so this is the checklist for the next pass.

## What Akshat said (mentor)
- The UI looks cheap ("looks shit"), especially the grey 3D; competitors look more expensive (they use dark mode).
- UX is a very important part of the judging; it is "all about execution", the idea alone does not win.
- Use Fable for UI work and invest in a proper workflow/skills setup instead of iterating small fixes.
- The knowledge idea (aging workforce, knowledge loss, notes at the place) is strong; build it as a simple store, not a custom knowledge graph.
- He liked "Walk with me" (counting steps, no GPS indoors).

## Leonie's direction
- **Apple Maps light mode, not dark mode.** Dark looks more expensive but does not fit technicians in a factory hall. Clean, high-end, familiar.
- Floating frosted panels, clear type hierarchy, round category-coloured POI glyphs, soft shadows, smooth camera.
- Synera blue `#004fab` only for route, selection and primary buttons; destination pin red; never overlapping elements.
- 3D as a light architecture model: walls cut at about 1.2–1.5 m with a thin top edge, soft light with shadows, floor slabs with thickness and pale room colours, recognisable furniture shapes instead of grey boxes.
- **Knowledge must be visible:** note/problem pins with photo are the app's signature; during guidance a "Klaus left a note here" card with the photo is the eye-catcher.
- Guidance screen: big current step, "Stop 3 of 14", a living Hey-Wanda state (waves while listening).

## What we neglected so far (honest)
1. No single design pass: four style switches in two days (blue/gold, blueprint/orange, blue, Google Maps), each as a separate fix in a different session, so there is no common hand.
2. Function before look: correctness and benchmark first (right for the 55 points), but the jury sees the surface first.
3. 3D as grey boxes (partly our own "flat and minimal" rule, right for 2D, too bare for 3D).
4. The story was missing in the product until the knowledge features.
5. No rehearsed demo path on a real device.
6. No design brief and no Fable workflow until Saturday night.

## For the next pass
- One brief, one Fable session, on the current `main`, no changes to logic or API contracts.
- Before it starts: 2–3 screenshots of what the team dislikes, each with one sentence, plus 1–2 reference apps they like.
- Check against this list and `twin/DESIGN.md`; screenshots at 1440×900 and 390×844 before and after.
