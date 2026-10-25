# Short technical explanation (paste into the form)

Copy everything between the two lines.

---

**Wanda – the building that talks back.** A voice guide for service technicians that knows a building like its facility manager, and keeps what technicians learn on site where it happened.

**Facts from code. Language from the model.** The building is a graph of rooms, doors, stairs, lifts and devices. Areas, walls, floors, door widths and routes are computed in Python on Synera's route model. Claude only picks a tool, asks what is missing and phrases the reply. All 145 benchmark answers in `SUBMISSION/answers.json` are produced by code, so they are reproducible. On the labelled dev set: 138 of 138.

**The knowledge stays in the building.** A technician taps the Wanda orb and says "note: the bracket is loose". The note sticks to that device, room, door or lift, with author, time and photo. "Lift 1 is out until tomorrow" reroutes everyone until then, then reopens by itself. Events and room bookings live in the same store ("is the Project Room free at 10?"). On the laptop each room opens as a knowledge graph (Brick and RealEstateCore types, Asset Administration Shell export).

**Guided work.** "All fire extinguishers on the ground floor" becomes the shortest round, one stop per device: in the Munich Urban Colab 8 stops and 98 m, against 234 m in name order. Wanda guides stop by stop, reads what the last shift left there, and "finished" shows a job report. Step-free mode avoids stairs. "Walk with me" counts steps and moves an estimated dot, no GPS.

**Any building, even from a plan (Level 4).** A floor plan becomes a building: scale, storeys, doors, room types and equipment from furniture symbols. Our demo building is the venue itself, read from photos of its evacuation plans.

**Safety.** Every change first shows a card with its effect and needs a clear yes.

**Stack.** Python 3.12 (shapely, networkx), Claude with tool use (Sonnet for the live chat, Opus for the benchmark agent), React and three.js for the 2D/3D map on laptop and phone, browser speech in, ElevenLabs voice out. 5,072 offline tests pass, with one file per question kind against all labelled answers.

---

## Sources

- 145 answers produced by code: all 145 questions of `data/test` match a sentence template of `building_agent/question_parser.py` and are answered by the kind functions without an API call (checked Sunday 25.10. on `main` 168f0b9); `building_agent.submission --check` says "ready to submit"; `SUBMISSION/answers.json` equals `answers/team_synera.csv` in all 145 replies.
- 138 of 138 dev questions: full `benchmark.evaluate data/dev` run by the team this weekend (not re-run here, it calls the API).
- Round: `plan_round` on `demo/buildings/plan-89323a15` (main), fire extinguishers on level 0, start Project Room (the start `scripts/demo_seed.py` uses): 8 stops, 98.4 m, exact order; name order 234.1 m. The video's floor-3 round is not on `main` yet, so it is not quoted here.
- Sonnet for chat, Opus for answers: `building_agent/agent.py` (`CHAT_MODEL`), `starter_agent/agent.py` (`MODEL`).
- Notes, end times, events, graph and AAS export: `building_agent/knowledge.py`, `knowledge_tools.py`, `knowledge_export.py`, `docs/specs/place-knowledge.md`, `docs/specs/events.md`.
- Tests: `uv run pytest -q` on main 168f0b9: 5072 passed, 21 skipped, 0 failed, no API key (live and browser tests are excluded by default).
