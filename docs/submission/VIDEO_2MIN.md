# 2-minute video: "The knowledge stays in the building"

> **Status 03:30 (Jennifer's session):** on `main` today: place knowledge server (notes, issues, timed closures with "until", history, graph export), Walk with me, tap answers "where are you", Hey Wanda with follow-up listening. Coming tonight: Wanda's knowledge tools (`feat/knowledge-agent`) and the knowledge page (`feat/twin-knowledge-page`, notes layer, pins, photos). **Not on `main`:** the inspection round (`feat/twin-round`, `feat/agent-plan-round`) and the browser notes (`feat/twin-notes`) exist only on Leonie's laptop; Jennifer decided not to build new features except place knowledge. If the round is not merged by the shoot, use this fallback for 0:25-0:55: Tom asks "Hey Wanda, take me to fire extinguisher H-A2", Walk with me moves the dot, and on arrival Wanda reads Klaus's note; then "lift 1 is out until tomorrow" shows the timed closure and the reroute.

Language: English. **One device: the iPhone** (team decision Sunday). The whole story is mobile: "as easy as Google Maps, which everyone already knows, and you talk to it like to a person, however technical you are." Voice through the **Talk button** (push to talk; reliable on iOS). Filmed in the Urban Colab with printed signs; the twin shows the dataset building **"Produktion West 39"** (`train/proc-factory-train-015`). Say on screen once: "Demo building from the dataset, acted out in our venue."

Update (Leonie's session): the inspection round, `plan_round` and the browser notes are now pushed on `feat/inspection-round-and-notes` (on top of main); notes use `/api/facts` automatically.

**Rule: always say the start point** ("I start at the entrance in Main aisle H-B3"), otherwise Wanda asks for it (no entrance is marked as the main one).

Real numbers: all fire extinguishers on the ground floor, start at the entrance in Main aisle H-B3: **5 stops, about 100 m** (page 100 m, agent 99.1 m). With a new door between Production zone H-A2 and Server room 0.16: **62 m, 38 m shorter**.
Demo link (opens the round and the "Try a door" button): `#round=fire%20extinguisher&area=Ground%20floor&building=train/proc-factory-train-015&door=proc-factory-train-015-F0-S002,proc-factory-train-015-F0-S016`

## Cast and props
- **Klaus**, 63, retiring next month. **Tom**, 24, three weeks in the job. Both use the same iPhone app.
- Printed signs on real spots: "Fire extinguisher" ×5 (numbered to match the stops), "Production zone H-A2", "Server room 0.16", "Main aisle H-B3 – Entrance".
- iPhone (screen recording on), gloves, a tripod or second phone for the outside shot.

## Script (2:00: 60 s product, 60 s technology)

| Time | Picture | Said | Notes |
|---|---|---|---|
| 0:00–0:08 | Klaus at a machine. Caption: "Klaus, 63. 38 years in this plant. Retires next month." | Voiceover: "When Klaus retires, 38 years of knowledge leave with him." | |
| 0:08–0:15 | Klaus at fire extinguisher 2, iPhone, takes a photo | Klaus (Talk): "Note: the bracket here is loose, always check it first." Pin with photo appears. | notes |
| 0:15–0:35 | Tom walks with the iPhone; screen recording of the map | Tom (Talk): "Inspection round: all fire extinguishers on the ground floor. I start at the entrance in Main aisle H-B3." Wanda: "Five stops, about 100 metres." Two stops shown with "Done", the rest as a 2-second time-lapse. At stop 2: "**Klaus left a note here:** the bracket is loose." Photo fades in. | round + notes |
| 0:35–0:47 | Same iPhone, 2D map | "What if a door here?" (Try a door) → new door, new route, "Round 38 m shorter (100 → 62 m)". | round what-if |
| 0:47–1:00 | Tom at the end | Tom (Talk): "Finished." Job report: 5 of 5 stops, 1 note with photo. (Cut this scene first if the video is too long.) | report |
| 1:00–1:25 | Diagram: voice → Wanda (agent) → tools → building graph | Voiceover: "Every fact comes from code, not from the language model: areas from polygons, shared walls, floors in 3D, door widths, door-to-door routes on Synera's route model. The model picks the tool and phrases the answer. That's why all 145 benchmark answers are reproducible." | |
| 1:25–1:45 | A floor plan image turning into the twin | Voiceover: "It works on any building, even from a floor plan: every furniture symbol becomes an asset, so we tell kitchens from offices." | Level 4 |
| 1:45–2:00 | Map full of note pins; roadmap card | Voiceover: "As easy as the maps you already use, and you just talk to it. Klaus retires. His knowledge doesn't. With 6G, the building will know where you are." Logo, team names. | |

## Shoot checklist
- iPhone: open the page over the tunnel (https, needed for the mic), allow the mic, speaker on, screen recording on; quiet spot for the voice takes.
- Reset the building before each take; open the demo link; check "5 stops · 100 m".
- Run the whole script twice without recording. Keep a screen recording of every take as backup.
- No secrets or personal tabs on screen.
- Cut to exactly 2:00; watch once without sound: the map alone should tell the story.
