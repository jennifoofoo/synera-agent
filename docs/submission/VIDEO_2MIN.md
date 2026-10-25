# 2-minute video: "The knowledge stays in the building"

> **Status 03:30 (Jennifer's session):** on `main` today: place knowledge server (notes, issues, timed closures with "until", history, graph export), Walk with me, tap answers "where are you", Hey Wanda with follow-up listening. Coming tonight: Wanda's knowledge tools (`feat/knowledge-agent`) and the knowledge page (`feat/twin-knowledge-page`, notes layer, pins, photos). **Not on `main`:** the inspection round (`feat/twin-round`, `feat/agent-plan-round`) and the browser notes (`feat/twin-notes`) exist only on Leonie's laptop; Jennifer decided not to build new features except place knowledge. If the round is not merged by the shoot, use this fallback for 0:25-0:55: Tom asks "Hey Wanda, take me to fire extinguisher H-A2", Walk with me moves the dot, and on arrival Wanda reads Klaus's note; then "lift 1 is out until tomorrow" shows the timed closure and the reroute.

Language: English. Device: Chrome on the laptop (hands-free "Hey Wanda" listens reliably there), laptop on a trolley the technician pushes. Filmed in the Urban Colab with printed signs; the twin shows the dataset building **"Produktion West 39"** (`train/proc-factory-train-015`). Say on screen once: "Demo building from the dataset, acted out in our venue."

**Rule: always say the start point** ("I start at the entrance in Main aisle H-B3"), otherwise Wanda asks for it (no entrance is marked as the main one).

Real numbers (twin round planner, checked against `/api/route`): all fire extinguishers on the ground floor, start at the entrance in Main aisle H-B3: **5 stops, 100 m**. With a new door between Production zone H-A2 and Server room 0.16: **62 m, 38 m shorter**.
Demo link (opens the round and the "Try a door" button): `#round=fire%20extinguisher&area=Ground%20floor&building=train/proc-factory-train-015&door=proc-factory-train-015-F0-S002,proc-factory-train-015-F0-S016`

Legend: BUILT = in the twin today. BUILDING = on a branch today (`feat/twin-round`, `feat/agent-plan-round`, `feat/twin-notes`, place knowledge server by Jennifer). If a BUILDING part is not merged by the shoot, use the fallback.

## Cast and props
- **Klaus**, 63, retiring next month (older-looking team member or a friend). **Tom**, 24, three weeks in the job. **Facility manager** (voice only or on the laptop).
- Printed signs on real spots: "Fire extinguisher" ×5 (numbered to match the stops), "Production zone H-A2", "Server room 0.16", "Main aisle H-B3 – Entrance".
- Trolley with the laptop, a phone for the photo, gloves.

## Script

| Time | Picture | Said | Status / fallback |
|---|---|---|---|
| 0:00–0:12 | Klaus at a machine, hand on a lever. Caption: "Klaus, 63. 38 years in this plant. Retires next month." | Voiceover: "When Klaus retires, 38 years of knowledge leave with him. Where things are, what breaks, which lever to pull first." | none |
| 0:12–0:25 | Klaus at Fire extinguisher 2, takes a photo | Klaus: "Hey Wanda, note: the bracket here is loose, always check it first." Wanda: "Saved at Production zone H-A2." Pin with photo on the map. | BUILDING (notes). Fallback: show the pin added by tap, voiceover says it |
| 0:25–0:55 | Tom pushes the trolley, the twin follows. Split screen: real hall / twin with route and stops | Tom: "Hey Wanda, inspection round: all fire extinguishers on the ground floor. I start at the entrance in Main aisle H-B3." Wanda: "Five stops, 100 metres. First: …" At each sign: "Hey Wanda, done." At stop 2: "**Klaus left a note here:** the bracket is loose, always check it first." Photo fades in. | Round: BUILT (button), voice start BUILDING (`plan_round`). Note readout: BUILDING. Fallback: start the round from the panel, "Next" by voice |
| 0:55–1:10 | Laptop, facility manager taps two rooms | FM: "What if we add a door between Production zone H-A2 and Server room 0.16?" Screen: new door ringed, new route, "Round 38 m shorter (100 → 62 m)". | BUILT (panel "What if a door here?") |
| 1:10–1:15 | Tom at the end | Tom: "Hey Wanda, finished." Job report: 5 of 5 stops, 100 m, 1 note with photo. | BUILDING (report). Fallback: skip, voiceover "and the report writes itself" |
| 1:15–1:40 | Diagram: voice → Wanda (agent) → tools → building graph; then a plan image turning into a twin | Voiceover: "Every fact comes from code, not from the language model: areas from polygons, shared walls, floors in 3D, door widths, door-to-door routes on Synera's own route model. The model picks the tool and phrases the answer. That's why all 145 benchmark answers are reproducible. It works on any building, even from a floor plan: every furniture symbol becomes an asset, so we tell kitchens from offices." | none |
| 1:40–1:50 | Split: "Hey Wanda, done" jumps instantly / a real question shows "Wanda is thinking" | Voiceover: "Commands like 'done' or 'how far' run instantly on the device. Only real questions reach the agent." | BUILT |
| 1:50–2:00 | Klaus hands Tom the gloves; map full of note pins; roadmap card | Voiceover: "Klaus retires. His knowledge doesn't. Today you tell Wanda where you are. With 6G, the building will know." Logo, team names. | none |

## Shoot checklist
- Chrome on the laptop, mic allowed for the page, speaker on, quiet spot for the voice takes (record voice close to the laptop mic).
- Reset the building before each take; open the demo link; check "5 stops · 100 m".
- Run the whole script twice without recording. Keep a screen recording of every take as backup.
- No secrets or personal tabs on screen.
- Cut to exactly 2:00; watch once without sound: the map alone should tell the story.
