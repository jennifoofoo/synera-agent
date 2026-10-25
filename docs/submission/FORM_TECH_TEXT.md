# Short technical explanation (for the Hack and More form)

Draft by Leonie's session, Sunday morning. Every number has a source in the repo; check it is still true before pasting. Longer version: `docs/submission/TECHNICAL_EXPLANATION.md`.

---

**Wanda – the building that talks back.** A voice agent for service technicians that knows a building as well as its facility manager, and keeps what technicians learn on site right where it happened.

**Principle: facts from code, language from the model.** A deterministic core holds the building as a graph of rooms, doors, stairs, lifts and assets. Areas come from polygons, shared walls from outline distance, rooms above and below from floor overlap, door widths from the data, routes door to door on Synera's route model (stairs and lifts costed as in the scoring note). Claude only chooses tools, asks what is missing, shows what it understood and phrases the reply. All 145 test answers in `SUBMISSION/answers.json` are produced by code, so they are reproducible.

**Interaction.** Every change to the building (close a lift, add a door, move a machine) first shows a card with its effect and needs a clear "yes". Directions come in short steps with landmarks. Hands-free mode listens for "Hey Wanda": commands like "done", "next" or "how far" run instantly on the device; only real questions go to the agent.

**For the technician.** Inspection rounds: "all fire extinguishers on the ground floor" becomes the shortest round (nearest neighbour plus 2-opt on door-to-door distances, in code), guided stop by stop. What-if for the facility manager: "add a door here" re-plans the round (100 m → 62 m on our demo building). Place knowledge: notes and photos attached to a room or machine, read aloud when the next person is guided past.

**Any building, even from a plan (Level 4).** A floor plan image plus its SVG becomes a building: scale, storey heights, floor alignment over stairs and lifts, door widths, and room types read from furniture symbols (each symbol is one asset; room types at 99.9 % precision on the kit buildings). 83 % of our re-created Level 4 questions are answered correctly on buildings built from plans.

**Stack.** Python 3.12 (uv, shapely, networkx), Claude with tool use, a React + three.js twin (2D map and 3D model, Google/Apple-Maps-style directions), Web Speech for voice in, ElevenLabs for voice out. Tests are the contract: one test per question kind against all labelled answers, a live conversation suite, browser end-to-end tests.

---

Sources: `SUBMISSION/BENCHMARK.md`, `docs/WORK_IN_PROGRESS.md` (Level 4 83 %, live suite), `docs/eval-log.md` (furniture glyphs, route model), `docs/submission/VIDEO_2MIN.md` (round numbers).
