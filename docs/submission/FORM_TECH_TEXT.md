# Short technical explanation (for the Hack and More form)

Draft by Leonie's session, revised by Jennifer's session (Sunday about 03:30). Only claims what is on `main` or merged before the freeze; re-check every number before pasting. Items marked [ROUND] depend on Leonie's inspection round branch being pushed and merged; delete them if it is not. Longer version: `docs/submission/TECHNICAL_EXPLANATION.md`.

---

**Wanda: the building that talks back.** A voice agent for service technicians that knows a building as well as its facility manager, and keeps what technicians learn on site right where it happened.

**Principle: facts from code, language from the model.** A deterministic core holds the building as a graph of rooms, doors, stairs, lifts and assets. Areas come from polygons, shared walls from outline distance, rooms above and below from floor overlap, door widths from the data, routes door to door on Synera's route model (stairs and lifts costed as in the scoring note). Claude only chooses tools, asks what is missing, shows what it understood and phrases the reply. All 145 test answers in `SUBMISSION/answers.json` are produced by code, so they are reproducible.

**Knowledge that stays in the building.** Technicians attach what they learn to a room, a machine, a door or a lift, by voice: "remember here: the valve on press 2 drips", "lift 1 is out until tomorrow". Every fact has a valid-from and valid-to time, an author and its source sentence; "fixed" supersedes a fact instead of deleting it, so Wanda answers "what is wrong here now?" and "what broke this week?". A timed closure reroutes everyone until it expires and then reopens by itself. Together with the building this forms a time-aware knowledge graph, exported as JSON-LD with Brick Schema and RealEstateCore types and an Asset Administration Shell view for machines.

**Interaction.** Every change (close a lift, add a door, move a machine, remember a fact) first shows a card with its effect and needs a clear "yes". Directions come in short steps with landmarks; tapping the map answers "where are you?". Hands-free mode listens for "Hey Wanda", keeps listening briefly after each answer, and runs commands like "next" or "how far" instantly on the device; only real questions go to the agent. "Walk with me" counts steps and moves an estimated dot along the route, no GPS needed. [ROUND] Inspection rounds: "all fire extinguishers on the ground floor" becomes the shortest round, guided stop by stop.

**Any building, even from a plan (Level 4).** A floor plan image plus its SVG becomes a building: scale, storey heights, floor alignment over stairs and lifts, door widths, and room types read from furniture symbols (each symbol is one asset). 83 % of our re-created Level 4 questions are answered correctly on buildings built from plans.

**Stack.** Python 3.12+ (uv, shapely, networkx), Claude with tool use, a React + three.js twin (2D map with zoom levels and 3D model, Maps-style directions), Web Speech for voice in, ElevenLabs for voice out, browser motion sensors for step counting. Tests are the contract: one test per question kind against all labelled answers, a live conversation suite against the real model, browser end-to-end tests on desktop and phones.

---

Sources: `SUBMISSION/BENCHMARK.md`, `docs/specs/place-knowledge.md` (facts with time, graph export), `docs/WORK_IN_PROGRESS.md` (Level 4 83 %, live suite), `twin/src/motion/README.md` (Walk with me).
