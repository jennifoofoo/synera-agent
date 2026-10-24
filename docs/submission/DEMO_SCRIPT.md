# Demo script

Persona: a new technician, day 1, hands full, phone in one hand. Does not know a single room name. Language: English, voice in and out. The assistant is called Wanda in the video (a name for the voice, not a name in the code). Building: one factory or campus from `data/dev` with a lift and a coffee machine. Run the whole script once beforehand and fix the building and the wording that work.

State checked against `main` at fe67dc3. Legend: **MAIN** = server and page work today. **NEEDS PAGE PART** = the server side is on main, the page side is not (Leonie's open work in `docs/STATUS.md`), so there is a fallback shot. Re-check `docs/STATUS.md` before recording.

## 90-second video

| # | Scene | On screen | Wanda says | User says | Sec | Status |
|---|---|---|---|---|---|---|
| 1 | Day 1 | Page loaded, empty chat | (voiceover) "First day, new building, no idea where anything is." | | 6 | MAIN |
| 2 | Position | Chat: the person says where they are | "Got it, you are at the main entrance." | "I'm at the main entrance." | 8 | Chat text MAIN. Blue dot NEEDS PAGE PART (`feat/position-page`). Fallback: show the chip-free chat reply and the route start on the plan. |
| 3 | Nearest | Hit pulses on the plan | "The nearest coffee machine is in Kitchen 0.12, 14 m away. Is that the one you mean?" | "Where is the coffee machine?" | 10 | Nearest search and assumption sentence MAIN (`find_nearest`). Pulse on the plan from chat hits: check on the page; if it does not pulse, show the route instead. Spoken rules (one short question, no lists) NEEDS PAGE PART: the page must send `voice: true`. |
| 4 | Offer | Chat | "It is on the ground floor, about a minute. Do you want me to guide you while you walk?" | "Yes." | 8 | Overview with offer and guided walking MAIN (`walk.py`). |
| 5 | Guided walk | Route animates, steps three at a time | "Leave through the door ahead, turn left at the press." | | 12 | Directions with landmarks MAIN. Auto-Pace timer (check-in after the estimated time) NEEDS PAGE PART. Fallback: user says "next". |
| 6 | Position again | Route restarts from the new spot | "From the lift: take it up one floor, then ..." | "I'm at the lift, where next?" | 10 | Position along the route MAIN (server). Moving dot NEEDS PAGE PART. |
| 7 | Facility manager | Confirmation card with the effect on the route | "Closing lift 1 makes your route 37 m longer, via lift 2. Shall I close it?" | "Close lift 1 for maintenance." | 12 | Card MAIN |
| 8 | Yes | Plan redraws live, lift marked closed | "Done. New route via lift 2." | "Yes." | 10 | Clear-yes guard and live route change MAIN |
| 9 | Level 4 (optional) | Drop a plan image, building appears in seconds, rooms with no way out in red, then a route in it | "I built 28 rooms. Two have no way out, want a door suggestion?" | "Route from room 0.03 to 0.21." | 14 | Upload page MAIN (`/api/level4/*`, merged, not browser-checked by Jennifer). Switching the page to the saved building NEEDS PAGE PART (W-L4b is merged locally, check). Image route only (vision, about 10 s); the SVG route is not on main. Fallback: terminal recording of `proc-campus-dev-000` floor 0. |
| 10 | Close | Title line | (voiceover) "Every number comes from tested code. Nothing changes without a clear yes." | | 6 | MAIN |

Total with scene 9: 96 s. Without scene 9: 82 s. Cut scene 3 or 6 first if over 90.

Rows 3, 4, 5, 6 need exact numbers in the voice track: record once, then copy the real numbers from the screen into the script.

## 3-minute pitch outline

| Time | Part | Content |
|---|---|---|
| 0:00 to 0:25 | Problem | Floor plans are PDFs, machines live in spreadsheets, the person who knows left. Outdoors you type and follow a line. Indoors nobody can. |
| 0:25 to 0:50 | Idea | Talk to the building. A deterministic core (graph of rooms, doors, stairs, lifts) does all the computing. The model only picks tools and phrases replies. |
| 0:50 to 1:50 | Demo | The video flow, live or recorded: where is the coffee, guided walk, "I'm at the lift", close the lift with card and yes, route changes. |
| 1:50 to 2:15 | What is different | Deterministic core. Asks back instead of guessing. Shows what it understood before any change. Independent verification: a separate agent re-implemented the 145 test answers (all match). |
| 2:15 to 2:40 | Numbers | Warm-up oracle 369 of 369. Our routing vs 1.1.0 labels: 1338 of 1338 at full marks. Parser 648 of 655 benchmark questions correct, 0 wrong, no API call. Level 4 on clean plans: recall 1.00, about 11 s and 0.02 USD a floor. Weak on dense Swiss plans (door recall 0.31). Sources: `docs/submission/TECHNICAL_EXPLANATION.md`. |
| 2:40 to 3:00 | Next | Accessibility mode (door widths, remembered profile, spec in `docs/specs/accessibility-mode.md`), time-bound closures (`docs/specs/live-updates.md`), a safety helper for exits (idea only, not built, `docs/IDEAS.md`). |

## Likely Q&A

1. **Why not photos of the plan?** A photo adds perspective, light and noise, and the scale is unknown. We take a clean plan image and read it with vision, then validate the result. The `scan` style scored lowest in our style test (graph Jaccard 0.05, `docs/eval-log.md`). Photos are not supported.
2. **Why SVG?** (Only if the SVG path is merged by the freeze.) A vector plan gives exact room outlines and door points, so no guessing. On `main` today Level 4 reads PNG through vision. Say which one is shown.
3. **What if the plan has no scale?** The agent asks for one known length, for example a door or a room width. A wrong scale makes every length wrong, the graph and the route order stay right.
4. **How do you know the answers are right?** Three checks. Tests against all labelled questions, the 369 of 369 oracle and 1338 route cases against the 1.1.0 labels, and a separate agent that re-implemented the 145 test answers without our code and matched all of them. We have not seen the organisers' scorer for the test set.
5. **What is not solved?** No positioning (the person says where they are). Door widths and equipment are not in a plan, so Level 4 estimates them. Dense Swiss plans lose rooms and doors. No closures with times. Forklift rules are rough. The campus format is our own, nothing in the data links buildings.
6. **Why not the new shortest-path algorithm from Tsinghua?** Our graph has under 2000 nodes and a route takes about 4 ms. Speed is not the bottleneck. The hard part is the geometry inside rooms (door to door, 15 cm from walls). Switching the algorithm would change nothing measurable.
7. **How does it handle ambiguity?** Name or number in the sentence wins. Otherwise the nearest hit from the stated position, said out loud with one check question. Otherwise it asks with at most two options. It never routes several candidates and picks one silently.
8. **Security and safety?** Every change needs a card and a clear yes in the person's next message, tested with adversarial variants (double yes, topic switch, "yes but not lift 1"). Position and Auto-Pace ticks never change the building. API keys stay on the server. The phone tunnel link is public while it runs. There is no evacuation feature, and nothing here is an escape plan.

## Recording checklist

- Devices: laptop with Chrome (Web Speech API), phone for the mobile shot, headset mic. Window 1280 x 720 or larger, zoom 110 to 125 %, no bookmarks bar.
- Phone over https: `scripts/tunnel.sh` (needs `brew install cloudflared`). The microphone only works on https. The link is public while it runs, share it with nobody, stop it with Ctrl+C.
- Keys in `.env`: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`. Never show `.env` in an editor or terminal. Check that the page status says chat and speech are available and the speaker is not muted.
- Quiet room, no keyboard clatter, test a 5 s clip. Grant the mic permission for the page address before recording.
- English everywhere, speak slowly in whole sentences.
- Building loaded, `Reset building` clicked, no closures left from earlier runs.
- No notifications, no personal tabs.
- Run the script twice without recording, then record. Keep the first good take. Also record one take with typed input in case the mic fails.
- If Wi-Fi is bad, `/api/speak` fails and the browser voice is the fallback.
- Export at most 90 s and watch it once with the sound off to check the plan alone tells the story.
