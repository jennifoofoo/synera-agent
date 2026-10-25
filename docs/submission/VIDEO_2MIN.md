# 2-minute video: "The knowledge stays in the building"

> **Status (Leonie's session, Sunday morning):** team decision: the video and the pitch use the **real venue, the Munich Urban Colab** (`user/plan-89323a15`, Jennifer's branch `feat/demo-urban-colab`), not a dataset building. The map shows the building we film in. Round, notes and report work on it (branch `feat/demo-urban-colab-prep`, checked with test extinguishers in a copy). **Blocked:** the building has **no fire extinguishers yet**; Jennifer adds them by hand from the plan photos. Until then the round numbers below are placeholders `[N stops]`, `[X m]`, and the round panel says "This map has no devices yet, so there is no round to plan."

Language: English. **One device: the iPhone** (team decision Sunday). The whole story is mobile: "as easy as Google Maps, which everyone already knows, and you talk to it like to a person, however technical you are." Voice through the **Wanda voice bar** at the bottom of the screen (tap the mic, or say "Hey Wanda" with hands-free on; push to talk is the reliable one on iOS).

**The building is real.** Level 4 read the Urban Colab from photos of its evacuation plans on site (ground floor and 1st floor); doors were added by hand because the plans draw no door widths. Room names are the venue's own (Foyer, Auditorium (Arena), Project Room, Café). Say on screen once: "This is the building you are standing in, read from its evacuation plans."

**Start point:** the round starts at the main entrance room, which is the page's default start: **Flur West** (`plan-89323a15-F0-S003`, the room behind the first entrance). Always say it ("I start at the entrance in Flur West"), otherwise Wanda asks where to start (the building has two entrances, Flur West and Flur Süd).

Real numbers (fill in once the extinguishers are in; `scripts/demo_seed.py` prints them): all fire extinguishers on the ground floor from Flur West: **[N stops], about [X m]**. The page panel and the chat use the same `plan_round` on the server, so both say the same; `tests/test_demo_urban_colab.py` checks that the round equals the route over the same stops (±1 m).

Demo link (opens the round panel on the ground floor and plans at once, start = Flur West):
`http://localhost:8798/?building=user/plan-89323a15#round=fire_extinguisher&area=Ground%20floor`
(over the tunnel: same path and hash on the https address).

## Before the shoot (once per machine)
1. `scripts/install_demo_buildings.sh` (copies the Urban Colab into `agent_output/buildings`; skips if it is already there, so after Jennifer adds the extinguishers delete `agent_output/buildings/plan-89323a15` first and install again).
2. Start the page: `uv run --env-file .env python -m web --port 8798`.
3. Seed the night shift's note: `uv run python scripts/demo_seed.py user/plan-89323a15 --port 8798 [--photo bracket.jpg]`. It puts "Bracket is loose, always check it first." (author "Night shift", kind issue) on the extinguisher at **stop 2** of the round from Flur West, prints the round (stops, metres) and adds nothing when run again. Without extinguishers it says so and exits.

## Cast and props
- **One person: Gisela**, service technician (team decision: one person only, women only; no facility manager in the 2-minute video).
- The knowledge from others appears only as notes already on the map ("from the night shift"), never as a second person on screen. The note is seeded with `scripts/demo_seed.py` (above), ideally with a photo of the real bracket.
- The real fire extinguishers of the Urban Colab (no printed signs needed); a sign "Entrance – Flur West" only if the entrance is not obvious on camera.
- iPhone (screen recording on), gloves, a tripod or second phone for the outside shot.

## Script (2:00: 60 s product, 60 s technology)

| Time | Picture | Said | Notes |
|---|---|---|---|
| 0:00–0:10 | Gisela at the Urban Colab entrance with gloves and the iPhone. Caption: "Gisela, service technician." | Voiceover: "By 2036, 12.9 million people in Germany reach retirement age. In maintenance, much of what they know was never written down." (Source: Federal Statistical Office via dbb magazin 9/2024.) Claim on screen: "The building talks back." | |
| 0:10–0:30 | Gisela walks; screen recording of the map of the room she is in | Gisela (voice bar): "Inspection round: all fire extinguishers on the ground floor. I start at the entrance in Flur West." Wanda: "[N] stops, about [X] metres." Route appears, "Stop 1 of [N]". Two stops with "Done", the rest as a 2-second time-lapse. | round |
| 0:30–0:45 | At stop 2 | Wanda: "**Night shift reported a problem here:** Bracket is loose, always check it first." Photo fades in. Gisela checks it. | notes |
| 0:45–0:49 | Gisela at a later stop takes a photo (3–4 s, no explanation) | Gisela (voice bar): "Note: hose is cracked, replace next week." Pin with photo appears: the next person will hear it. | notes |
| 0:55–1:00 | End of the round | Gisela (voice bar): "Finished." Job report: [N] of [N] stops, her note, "read during the round: Night shift". | report |
| 1:00–1:25 | Diagram: voice → Wanda (agent) → tools → building graph | Voiceover: "Every fact comes from code, not from the language model: areas from polygons, shared walls, floors in 3D, door widths, door-to-door routes on Synera's route model. The model picks the tool and phrases the answer; the shortest round is computed, not guessed. That's why all 145 benchmark answers are reproducible." | |
| 1:25–1:45 | The photo of the Urban Colab evacuation plan turning into the twin | Voiceover: "It works on any building, even from a plan on the wall: this is the building we are standing in, read from its evacuation plans." | Level 4 |
| 1:45–2:00 | Map full of note pins; roadmap card | Voiceover: "As easy as the maps you already use, and you just talk to it. The knowledge stays in the building. Today Gisela confirms where she is. Built today, ready for the 6G building." Logo, team names. | |

Cut first if too long: the report (0:55–1:00). The what-if door (facility manager level) is not in the video; mention it in the live pitch or Q&A only.

## Shoot checklist
- iPhone: open the page over the tunnel (https, needed for the mic), allow the mic, speaker on, screen recording on; quiet spot for the voice takes.
- Reset the building before each take (Gisela's own notes from the last take: Undo, or delete them on the server), keep the night shift's note; open the demo link; check "[N] stops · [X] m".
- Run the whole script twice without recording. Keep a screen recording of every take as backup.
- No secrets or personal tabs on screen.
- Cut to exactly 2:00; watch once without sound: the map alone should tell the story.
