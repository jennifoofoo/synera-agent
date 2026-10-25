# Short technical explanation (paste into the form)

Copy everything between the two lines.

---

**Wanda – the building that talks back.** A voice guide for service technicians that knows a building like its facility manager, and keeps what people learn on site where it happened.

**Facts from code. Language from the model.** The building is a graph of rooms, doors, stairs, lifts and devices. Areas, walls, floors, door widths and routes are computed in Python on Synera's route model. Claude only picks a tool, asks what is missing and phrases the reply. All 145 benchmark answers come from code without a model call, so they are reproducible; on the labelled dev set 138 of 138 are correct. One command runs the same system on a new building.

**Talk to it, hands busy.** Tap the Wanda orb and ask, in English or German. Tap the map to say where you are. "Where is the nearest toilet?" draws the route, "yes" starts guiding. Directions come turn first with metres ("Walk 5 m, then turn left"). "Walk with me" counts steps and moves an estimated dot, no GPS. Step-free mode avoids stairs. The mic stays muted while walking so noise never triggers it.

**Guided rounds.** "All fire extinguishers on floor 3" becomes the shortest round, one stop per device: 6 stops, 114 m, 38 m shorter than name order. At each stop Wanda reads what the last shift left there. "Note: hose cracked" saves on that device, "finished" shows the job report.

**The knowledge stays in the building.** Notes, problems, timed closures, events and room bookings hang on a room, device, door or lift, with author, time and photo. Nothing is deleted, a fix supersedes. Problem words make a note a problem, a closure reroutes until it ends. Each room opens as a knowledge graph with Brick and RealEstateCore types and an Asset Administration Shell export.

**Any building, even from a plan.** A floor plan becomes a building: scale, storeys, doors and room types from furniture symbols. Our demo building is the venue, read from photos of its evacuation plans.

**Safe by design.** Every change shows a card with its effect and needs a clear yes.

**Stack.** Python (shapely, networkx), Claude with tool use (Sonnet for fast chat, Opus for benchmark answers), React and three.js for the 2D/3D map, browser speech and ElevenLabs for voice. Over 5,000 offline tests, a live conversation suite and browser tests on laptop and phones.

---

## Sources

- 145 answers produced by code: all 145 questions of `data/test` match a sentence template of `building_agent/question_parser.py` and are answered by the kind functions without an API call (checked Sunday 25.10. on `main` 168f0b9); `building_agent.submission --check` says "ready to submit"; `SUBMISSION/answers.json` equals `answers/team_synera.csv` in all 145 replies.
- 138 of 138 dev questions: full `benchmark.evaluate data/dev` run by the team this weekend (not re-run here, it calls the API).
- Round: `plan_round` on `demo/buildings/plan-89323a15` (main), fire extinguishers on Floor 3, start Main Stairs (the start the page picks for a one-floor round): 114.2 m; name order 152.7 m, 38.5 m saved (`compare_hint`), 6 stops per device as on the panel and in the video.
- Sonnet for chat, Opus for answers: `building_agent/agent.py` (`CHAT_MODEL`), `starter_agent/agent.py` (`MODEL`).
- Notes, end times, events, graph and AAS export: `building_agent/knowledge.py`, `knowledge_tools.py`, `knowledge_export.py`, `docs/specs/place-knowledge.md`, `docs/specs/events.md`.
- Tests: `uv run pytest -q` on main 168f0b9: 5072 passed, 21 skipped, 0 failed, no API key (live and browser tests are excluded by default).
