# Demo script

Persona: Sam, a new service technician on the first day. Does not know a single room name, has the phone in one hand.
Language: English, voice in and out. Building: pick one procedural factory or campus from `data/dev` that has a lift, a machine hall and a coffee spot. Run the whole script once beforehand and fix the building and wording that work.

Legend: MUST = works in main today. OPTIONAL = needs a feature that is not merged at the time of writing. Check `docs/STATUS.md` before recording and use the fallback if the feature is not in main.

## 90-second video

| Time | On screen | Said (voice) | Must work |
|---|---|---|---|
| 0:00 to 0:08 | Web page, building loaded, empty chat | Voiceover: "First day, new building, no idea where anything is. Sam just asks." | Page loads, building picker shows the building |
| 0:08 to 0:20 | Mic button pressed, Sam speaks, plan pulses on the hit | Sam: "Where can I get a coffee?" Agent answers aloud with the room and floor | MUST: voice in (browser), find tool, hit pulses on the plan, ElevenLabs reply |
| 0:20 to 0:38 | Route drawn and animated on the plan, floor switch marker | Sam: "Take me there, I am at the main entrance." Agent: three short steps with landmarks ("turn left at the CNC mill") | MUST: route animation, landmark directions, 3 steps per turn |
| 0:38 to 0:46 | Chat: "next" | Sam: "Next." Agent gives the next three steps | MUST: next_steps |
| 0:46 to 1:00 | Route turns step-free, longer, lift shown | Sam: "My colleague uses a wheelchair, what is the way for her?" Agent: step-free route, says how much longer, or says honestly if none | MUST: step-free routing |
| 1:00 to 1:18 | Confirmation card appears on screen, then the plan updates | Sam: "Lift 1 is out for maintenance." Agent shows a card with the effect on the route. Sam: "Yes." Route recomputes ("37 m longer, now via lift 2") | MUST: propose_change, card, clear-yes guard, what_changes |
| 1:18 to 1:30 | Close-up of the card, then the title line | Voiceover: "Every number comes from tested code. The model only talks, and nothing changes without a clear yes." | none |

### Optional shots (each has a fallback)

| Slot | Optional shot | Needs | Fallback shot |
|---|---|---|---|
| after 1:00 | Sam says "Put the second press next to the CNC" and the asset moves on the plan after the card (placement by voice) | placement by voice merged and wired in the page | Same card flow with "Close lift 1" (already in the table) |
| replaces 1:18 to 1:30 | 3D view with a walkthrough of the route | 3D view merged | Plan with route animation, stacked floors via the floor switcher |
| extra 5 s | Two buildings connected, route across the walkway (Level 3) | Level 3 campus merged | Skip. Mention in the pitch as "specified, not shipped" only if it is not merged |
| extra 8 s | Drop a floor plan image, the building appears with a red room "no way out" and a door suggestion (Level 4 upload page) | Level 4 upload page in `web/` (today Level 4 runs through chat tools with a file in `agent_output/uploads/`, not through the page) | Screen recording of the terminal or chat building a clean plan (`proc-campus-dev-000` floor 0), plus the table from `docs/eval-log.md` for one second |

## 3-minute pitch outline

| Time | Part | Content |
|---|---|---|
| 0:00 to 0:25 | Problem | Floor plans are PDFs, machines live in spreadsheets, the person who knows left. Outdoors we type and follow a line, indoors nobody can. |
| 0:25 to 0:50 | Solution | Talk to the building. Deterministic core (graph of rooms, doors, lifts), LLM only as interaction layer. Show the architecture picture for 10 s. |
| 0:50 to 1:50 | Live demo moment | One live run: voice question, route, step-free, lift closed, card, yes, new route. Same flow as the video, shortened. Have the recording ready as backup. |
| 1:50 to 2:20 | Numbers | Dev sample 72 of 72, route sequences at full points 92.4 % to 99.6 % after the door-to-door model (estimate), Level 4 on clean plans recall 1.00 at about 0.02 USD per floor. Honest line: weak on dense Swiss plans, the agent warns and asks. |
| 2:20 to 2:45 | What we added that was not asked | Understanding card with clear-yes guard, "what changes" for the whole building, plan upload with validation and door suggestions, parser fast path that answers known question types without an LLM call. Add only what is merged and shown. |
| 2:45 to 3:00 | Close | "Ask your building, and trust the answer." Repo, `BENCHMARK.md`, one command. |

## Likely Q&A (1 minute)

1. **How do you stop the LLM from making things up?** It computes nothing. Tools return facts from the building data, replies end with one `Answer:` line, an unknown room is never routed to, similar names are offered.
2. **What if the model misunderstands a change request?** Every change shows a card with its effect first. The tool refuses unless the person's later message is a clear yes. Tested with adversarial variants (double yes, "yes but not lift 1", topic switch).
3. **How do you score on routes?** Door-to-door graph with the organisers' stair and lift costs. In our own estimate 99.6 % of 672 sample cases reach full points, against 92.4 % with the kit model. We have not seen the organisers' scorer.
4. **Does it work on a building you have not seen?** One command, nothing hard-coded. A sweep runs all question kinds on all 280 buildings, and `scripts/preflight.py` checks a new building in seconds.
5. **How good is the plan upload (Level 4)?** Clean plans: all rooms and doors, area error 0.6 % median. Dense Swiss plans: recall 0.79 and door recall 0.31 median, so it warns about unreachable rooms and proposes doors that a person confirms.
6. **What does it cost and how fast is it?** About 11 s and 0.02 USD per floor for plan reading (list price). Known benchmark questions need no API call at all.
7. **What is voice built on?** Browser speech recognition in, ElevenLabs out, key on the server. Works best in Chrome or Edge. German and English both work, the demo is English.
8. **What did you not build?** Windows (not in the data), real campus links (our format is invented), forklift rules are only roughly tested, 3D and AR only if shown. Say what is missing, do not hide it.

## Recording checklist

- Browser: Chrome or Edge (Web Speech API), clean profile, no bookmarks bar, zoom 110 to 125 %, window about 1280 x 720 or larger.
- Mic: permission granted for `127.0.0.1:8765` before recording, test a 5 s clip, headset mic, quiet room, no keyboard clatter.
- `.env` has `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`. Check the status line of the page says chat and speech are available. The speaker button is on, not muted.
- English: language selector on English, English voice, speak slowly and in whole sentences.
- Data copy: building from `data/dev` loaded, `Reset building` clicked, no closures left from earlier runs.
- No secrets on screen: no terminal with `.env`, no key in the browser, no personal tabs or notifications. Do not show `.env` in any editor.
- Run the script twice without recording, then record. Keep the first good take.
- Backup: record the full flow once as a screen recording with audio and keep the file next to the live demo, plus a second take with typed input in case the mic fails.
- Network: if Wi-Fi is bad, `/api/speak` fails and browser voice is the fallback, say nothing and keep going.
- Length: video at most 90 seconds, export, watch it once with the sound off to check that the plan alone tells the story.
