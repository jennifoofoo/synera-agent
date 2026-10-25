# 2-minute video: "The knowledge stays in the building"

> **Status 03:30 (Jennifer's session):** on `main` today: place knowledge server (notes, issues, timed closures with "until", history, graph export), Walk with me, tap answers "where are you", Hey Wanda with follow-up listening. Coming tonight: Wanda's knowledge tools (`feat/knowledge-agent`) and the knowledge page (`feat/twin-knowledge-page`, notes layer, pins, photos). **Not on `main`:** the inspection round (`feat/twin-round`, `feat/agent-plan-round`) and the browser notes (`feat/twin-notes`) exist only on Leonie's laptop; Jennifer decided not to build new features except place knowledge. If the round is not merged by the shoot, use this fallback for 0:25-0:55: Tom asks "Hey Wanda, take me to fire extinguisher H-A2", Walk with me moves the dot, and on arrival Wanda reads Klaus's note; then "lift 1 is out until tomorrow" shows the timed closure and the reroute.

Language: English. **One device: the iPhone** (team decision Sunday). The whole story is mobile: "as easy as Google Maps, which everyone already knows, and you talk to it like to a person, however technical you are." Voice through the **Talk button** (push to talk; reliable on iOS). Filmed in the Urban Colab with printed signs; the twin shows the dataset building **"Produktion West 39"** (`train/proc-factory-train-015`). Say on screen once: "Demo building from the dataset, acted out in our venue."

Update (Leonie's session): the inspection round, `plan_round` and the browser notes are now pushed on `feat/inspection-round-and-notes` (on top of main); notes use `/api/facts` automatically.

**Rule: always say the start point** ("I start at the entrance in Main aisle H-B3"), otherwise Wanda asks for it (no entrance is marked as the main one).

Real numbers: all fire extinguishers on the ground floor, start at the entrance in Main aisle H-B3: **5 stops, about 100 m** (page 100 m, agent 99.1 m). (For Q&A only: a new door between Production zone H-A2 and Server room 0.16 makes it 62 m.)
Demo link (opens the round and the "Try a door" button): `#round=fire%20extinguisher&area=Ground%20floor&building=train/proc-factory-train-015&door=proc-factory-train-015-F0-S002,proc-factory-train-015-F0-S016`

## Cast and props
- **One person: Gisela**, service technician (team decision: one person only, women only; no facility manager in the 2-minute video).
- The knowledge from others appears only as notes already on the map ("from the night shift"), never as a second person on screen. Seed one note before the shoot at fire extinguisher 2 (Production zone H-A2) with a photo: "Bracket is loose, always check it first" (author: night shift).
- Printed signs on real spots: "Fire extinguisher" ×5 (numbered to match the stops), "Main aisle H-B3 – Entrance".
- iPhone (screen recording on), gloves, a tripod or second phone for the outside shot.

## Script (2:00: 60 s product, 60 s technology)

| Time | Picture | Said | Notes |
|---|---|---|---|
| 0:00–0:10 | Gisela at the hall entrance with gloves and the iPhone. Caption: "Gisela, service technician." | Voiceover: "By 2036, 12.9 million people in Germany reach retirement age. In maintenance, much of what they know was never written down." (Source: Federal Statistical Office via dbb magazin 9/2024.) Claim on screen: "The building talks back." | |
| 0:10–0:30 | Gisela walks; screen recording of the map | Gisela (Talk): "Inspection round: all fire extinguishers on the ground floor. I start at the entrance in Main aisle H-B3." Wanda: "Five stops, about 100 metres." Route appears, "Stop 1 of 5". Two stops with "Done", the rest as a 2-second time-lapse. | round |
| 0:30–0:45 | At stop 2 | Wanda: "**Note from the night shift:** the bracket is loose, always check it first." Photo fades in. Gisela checks it. | notes |
| 0:45–0:49 | Gisela at stop 4 takes a photo (3–4 s, no explanation) | Gisela (Talk): "Note: hose is cracked, replace next week." Pin with photo appears: the next person will hear it. | notes |
| 0:55–1:00 | End of the round | Gisela (Talk): "Finished." Job report: 5 of 5 stops, 2 notes with photos. | report |
| 1:00–1:25 | Diagram: voice → Wanda (agent) → tools → building graph | Voiceover: "Every fact comes from code, not from the language model: areas from polygons, shared walls, floors in 3D, door widths, door-to-door routes on Synera's route model. The model picks the tool and phrases the answer; the shortest round is computed, not guessed. That's why all 145 benchmark answers are reproducible." | |
| 1:25–1:45 | A floor plan image turning into the twin | Voiceover: "It works on any building, even from a floor plan: every furniture symbol becomes an asset, so we tell kitchens from offices." | Level 4 |
| 1:45–2:00 | Map full of note pins; roadmap card | Voiceover: "As easy as the maps you already use, and you just talk to it. The knowledge stays in the building. Today Gisela confirms where she is; with 6G, the building will know." Logo, team names. | |

Cut first if too long: the report (0:55–1:00). The what-if door (facility manager level) is not in the video; mention it in the live pitch or Q&A only.

## Shoot checklist
- iPhone: open the page over the tunnel (https, needed for the mic), allow the mic, speaker on, screen recording on; quiet spot for the voice takes.
- Reset the building before each take; open the demo link; check "5 stops · 100 m".
- Run the whole script twice without recording. Keep a screen recording of every take as backup.
- No secrets or personal tabs on screen.
- Cut to exactly 2:00; watch once without sound: the map alone should tell the story.
