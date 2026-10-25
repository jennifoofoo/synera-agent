# Video storyboard (2:00): "Wanda – the building that talks back"

The single source for the jury video: timing, picture, exact lines, captions, shots, prep. `VIDEO_2MIN.md` only points here.

**Story:** one person, Gisela, service technician. She plans her fire-extinguisher round on the laptop, walks it in the real Munich Urban Colab with Wanda on her phone, hears what the night shift left at an extinguisher, leaves her own note, gets the job report. Problem first, then product, then why you can trust it.

**Picture rule:** the round runs as a **split screen**: left the real Gisela walking (camera), right the phone screen recording (map). Everything else is full frame.

## 0. Facts the video may use (checked Sunday 25.10. on `main` 622c1c5 and `feat/round-per-device` 57c3d9f)

| Claim | Status | Where it is true |
|---|---|---|
| Building = the Urban Colab, read from its evacuation-plan photos (ground floor + floor 1, English room names) | true on main | `demo/buildings/plan-89323a15` |
| Round from **South Corridor**, all fire extinguishers on the ground floor: **7 stops · 81.6 m** (one stop per room) | true on main | `plan_round`, North Corridor holds 2 extinguishers = 1 stop |
| Same round: **8 stops · 106.7 m**, "Stop n of m · Fire extinguisher 0.0x" (one stop per device) | **only after `feat/round-per-device` is merged** | branch, not in main yet |
| Stop 1 = Fire extinguisher 0.05 (South Corridor, where she starts), stop 2 = **Fire extinguisher 0.04 (West Corridor)** | true on both | order identical on both branches |
| Round panel: what (chips), from (tap the map), "N stops · X m · about N min", Start round, "What if a door here?" → "Round X m shorter (before → after m)" | true on main | `twin/src/ui/Round.tsx`, `round.ts whatIfLine` |
| Voice: "done" / "how far" run on the phone; "note: …" saves a note; "finished" shows the job report | true on main | `handsFree.ts`, notes |
| Night-shift note read aloud with photo when she is guided to that extinguisher | true on main (verified in the browser by demo-urban-colab-prep) | `scripts/demo_seed.py --photo` |
| All 145 benchmark answers produced by code, reproducible | true | `SUBMISSION/answers.json`, `BENCHMARK.md` |
| "By 2036, 12.9 million people in Germany reach retirement age" | sourced | Federal Statistical Office, via dbb magazin 9/2024 (show source in the caption) |

**Rule for the cut:** never say a number aloud that is not on screen. Wanda's spoken numbers come from the LLM phrasing the tool result, so the caption shows the panel's number and the voiceover does not repeat it. Re-read the numbers from the panel on shoot day: the handover `docs/HANDOVER_URBAN_COLAB_FLOORS.md` may add the ground-floor west part (E.06) with more extinguishers, which changes N and X.

Placeholders in the table below: **[N] / [X]** = **[N stops · X m]** as the panel shows it on shoot day. Today on main: 8 extinguishers, **7 stops · 81.6 m** (per room, North Corridor holds 2). After `feat/round-per-device`: **8 stops · 106.7 m** (per device). Note in the edit which one the footage shows.

## 1. Storyboard, second by second

Shot: **F** = full frame, **L|R** = split screen (left camera, right phone recording). VO = voiceover (Leonie or Jennifer, one voice, calm). Lines in quotes are exact.

| Time | Shot | On screen | Spoken (exact) | Caption (burned in) | Purpose |
|---|---|---|---|---|---|
| 0:00–0:03 | F | Close-up: Gisela's gloved hand on a fire extinguisher bracket in a corridor, dim. Cut to black on the last word. | VO: "Every building has one person who knows it by heart." | – | **Hook 1** (see §2) |
| 0:03–0:06 | F | Black, white text appears. | VO: "Last spring, that person retired." | "Last spring, that person retired." | Turn the hook into a loss |
| 0:06–0:13 | F | Slow push-in on Gisela at the South Corridor entrance, iPhone in hand, looking at a wall full of doors. | VO: "By 2036, 12.9 million people in Germany reach retirement age." | "12.9 million people reach retirement age by 2036 (Destatis, via dbb magazin 9/2024)" | The one sourced number, big |
| 0:13–0:21 | F | Gisela opens a paper folder: a printed plan, a handwritten list "Extinguishers, ground floor", crossed out, coffee stain. | VO: "What they knew was never written down. Which extinguisher has the loose bracket. Which door is always locked." | – | Concrete: knowledge lives in heads |
| 0:21–0:29 | F | Gisela walks into a dead end (closed door), turns back, checks her phone (generic, no app). Time stamp caption ticks up. | VO: "So the new shift searches. Asks around. Writes it up later, if at all." | "06:12 … 06:31" (ticking) | Pain 2 + 3: time lost, handover lost |
| 0:29–0:38 | F | Still of Gisela in the corridor, text builds line by line. | VO: "Maintenance software knows what. Location tracking knows roughly where. Nobody tells you, hands-free, where to go, and nobody keeps what you learned there." | "Knows what. Knows roughly where. Nobody guides you. Nobody remembers." | Positioning line = the gap |
| 0:38–0:41 | F | Logo card: "Wanda – the building that talks back". | VO: "This is Wanda." | "Wanda – the building that talks back" | Product name |
| 0:41–0:52 | F (laptop screen recording, slight zoom) | Laptop, 3D twin of the Urban Colab. Gisela clicks **Round**: what = fire extinguisher, where = Ground floor, from = taps South Corridor on the map. Panel: "[N] stops · [X] m · about N min", stops in order, route drawn. Quick pan to the knowledge view with note pins. | VO: "Gisela plans her fire-extinguisher round on the laptop. The shortest order is computed on the building's own plans, and she sees what colleagues left at each stop." | "Plan: [N] stops · [X] m" (copy from panel) | Laptop beat: planning + knowledge overview |
| 0:52–0:57 | L\|R | L: Gisela at the South Corridor entrance, raises the phone, taps the Wanda orb. R: phone map, orb listening. | Gisela: "Hey Wanda, fire extinguisher round, ground floor. I start in the South Corridor. Guide me." | "Same round, on her phone, hands-free" | Hand-off to the walk |
| 0:57–1:02 | L\|R | L: Gisela checks extinguisher 0.05 next to her. R: "Stop 1 of [N]", dot at the device. | Gisela: "Done." | "Stop 1 of [N]" | Stop 1 live |
| 1:02–1:08 | L\|R | L: walks to the West Corridor, follows the turn. R: route line moves, step sheet "Turn left …". | Gisela: "How far?" Wanda answers (keep the real audio, about 2 s). | – | Guidance live |
| 1:08–1:18 | L\|R | L: arrives at extinguisher 0.04. R: note card pops up, **photo of the loose bracket** fades in. Gisela wiggles the bracket. | Wanda (real app audio): "Night shift reported a problem here, today [time]: Bracket is loose, always check it first." | "From the night shift, at this extinguisher" | **Mid hook**: knowledge arrives at the right place |
| 1:18–1:20 | L\|R | L: Gisela tightens the bracket. R: Stop 2 checked. | Gisela: "Done." | "Stop 2 of [N]" | Close the loop |
| 1:20–1:24 | L\|R time-lapse | Stops 3 to [N]–1 at 8× speed, both sides in sync; R shows the stop counter running. | (music only) | "Stops 3–[N−1]" | Middle stops as 2–4 s time-lapse |
| 1:24–1:28 | L\|R | L: last stop (North Corridor), Gisela takes a photo of a cracked hose. R: note pin with photo appears. | Gisela: "Note: hose is cracked, replace next week." | "Her note stays here for the next shift" | She leaves knowledge (3 s) |
| 1:28–1:32 | L\|R | L: Gisela lowers the phone. R: job report: [N] of [N] stops, metres walked, 1 note left, "read during the round: Night shift". | Gisela: "Finished." | "Job report, written for her" | Documentation without typing |
| 1:32–1:42 | F (diagram) | Simple diagram: voice → Wanda (Claude picks a tool) → deterministic tools → building graph → answer. A tool result JSON flashes on the "tools" box. | VO: "Every fact comes from code, not from the language model. Areas, walls, floors, door widths, routes: computed on Synera's route model. The model only picks the tool and phrases the answer." | "Facts from code. Language from the model." | Trust 1: architecture |
| 1:42–1:47 | F | Terminal or `SUBMISSION/BENCHMARK.md`: "145 answers, all produced by code" (not a claim that all are correct). | VO: "That's why all 145 benchmark answers are reproducible." | "145 benchmark answers, reproducible" | Trust 2: proof |
| 1:47–1:55 | F | Photo of the real evacuation plan on the Urban Colab wall → crossfade → the 2D map → 3D twin. | VO: "And it works on any building, even from the evacuation plan on the wall. This is the building we're standing in." | "Read from its evacuation plans" | Trust 3: any building (Level 4) |
| 1:55–2:00 | F | Map full of note pins, Wanda orb glows, logo + team names. | VO: "The knowledge stays in the building." | "Wanda – the building that talks back · Built today, ready for the 6G building." | **Last line** + product name |

### Timing summary

| Block | Time | Length |
|---|---|---|
| Hook + problem | 0:00–0:38 | 38 s |
| Product name | 0:38–0:41 | 3 s |
| Laptop planning | 0:41–0:52 | 11 s |
| Split-screen round (stops 1–2 live, time-lapse, own note, report) | 0:52–1:32 | 40 s |
| Why you can trust it | 1:32–1:55 | 23 s (+5 s close = 28 s) |
| Close | 1:55–2:00 | 5 s |

VO word budget: about 2.3 words per second. Problem VO is 70 words in 38 s, trust VO 55 words in 23 s: both fit with pauses. If the cut runs long, cut in this order: (1) "How far?" beat 1:02–1:08 (just walk), (2) knowledge-view pan in the laptop beat, (3) the dead-end shot shortened to 4 s. Never cut the night-shift note, the sourced number or the last line.

## 2. Hooks (pick marked ★)

**First 3 seconds / thumbnail**
1. ★ "Every building has one person who knows it by heart." + gloved hand on an extinguisher bracket, then "Last spring, that person retired." Emotional, universal, sets up the note payoff. Thumbnail: split frame, Gisela left, phone with "Stop 2 of [N]" and the night-shift card right, text "The building remembers."
2. "Where's the extinguisher with the loose bracket? Only one person knew." More concrete, but needs the context to land.
3. "12.9 million people retire by 2036. Their knowledge goes with them." Strong number, but colder as the first frame; better as the third beat.

**Mid hook (about 1:08)**
1. ★ Wanda reads the night-shift note at the exact extinguisher, photo fades in: the problem from 0:13 solved on camera.
2. "Round [X] m shorter (before → after m)" from "What if a door here?" on the laptop: impressive for engineers, but adds a second story and needs the what-if door shot (keep for the live pitch).
3. "No GPS, no beacons: the building's own evacuation plan." Good, but it is the trust section's job.

**Last line**
1. ★ VO "The knowledge stays in the building." + caption "Built today, ready for the 6G building." Echoes the hook (the person retired, the knowledge stays).
2. "Built today, ready for the 6G building." spoken as the last line: forward-looking, but loses the emotional loop.
3. "Ask your building, and trust the answer." Strong for the trust part, weaker on the problem.

## 3. Shot list

Devices: **iPhone A** = Gisela's phone (screen recording on, Wanda page over the https tunnel). **Camera B** = second phone or camera on a gimbal/tripod, 4K 30 fps, landscape. **Laptop** = screen recording (QuickTime or OBS), 1920×1080, browser zoom 110 %. Audio: clip-on mic on Gisela (for her lines) plus the phone's own app audio from the screen recording (for Wanda's voice).

| # | What | Where | Device | Notes |
|---|---|---|---|---|
| S1 | Close-up gloved hand on bracket (hook) | any extinguisher, ideally 0.04 West Corridor | Camera B, handheld, low light | 5 s, two takes |
| S2 | Gisela at the entrance, push-in | South Corridor entrance | Camera B, gimbal | 8 s |
| S3 | Paper folder, crossed-out list, printed plan | table in the Foyer | Camera B, top-down | prop: print the evacuation plan + handwritten list |
| S4 | Dead end: closed door, turn back | any closed door | Camera B | no app visible on her phone |
| S5 | Laptop planning (round panel, start South Corridor, knowledge view) | anywhere | Laptop screen recording | record 3 takes, keep the cleanest; mouse slow |
| S6 | **Round, camera side**: the whole walk from South Corridor, stops 1 → last | ground floor | Camera B follows 2–3 m behind/side | one continuous take, Gisela speaks her lines |
| S7 | **Round, phone side**: same walk | – | iPhone A screen recording **with mic audio on** (long-press record button → Microphone on) | starts before the sync cue |
| S8 | Photo of the cracked hose (her note) | last stop | iPhone A (in-app camera) | real object or tape on a hose |
| S9 | Evacuation-plan photo on the wall | wherever the E.05 plan hangs | Camera B, straight on | also usable: `demo/plans/urban-colab/photos/E05_ground_floor.jpeg` |
| S10 | Diagram + 145 table | – | Keynote/Figma export, 1080p | made by the editor, no filming |

**Split-screen sync trick:** at the start of S6/S7, with both recording, Gisela holds iPhone A into Camera B's frame and **claps once next to it while tapping the Wanda orb**. The clap is a spike in both audio tracks; the orb lighting up is a visible frame in both pictures. Align on that frame, then trim. Do it again at the last stop (second clap) to check drift; if the two clips drift, re-align per segment at each "Done" (the stop counter changes on screen, the word is audible on camera).

**Fallback if the ground floor is not accessible**
- **Partial ground floor:** film live only from South Corridor to West Corridor (stops 1–2, the note) — that is all the video shows in real time. For the time-lapse, film any corridor walk (Camera B) and pair it with the phone recording of the remaining stops, done by tapping "Done" while standing still (map side stays truthful, camera side is labelled "time-lapse").
- **Floor 1 instead:** the model has floor 1 with 7 fire extinguishers (Work Area, Seminar Rooms 1-3, Auditorium upper rows, CAD-Center, First Floor Corridor ×2). Say "all fire extinguishers on floor 1, I start at the Main Stairs" and **re-plan on the laptop first** to read stops, metres and stop 2. Re-seed the night-shift note: `scripts/demo_seed.py` only seeds the ground floor, so put the note on floor 1's stop 2 by hand on the page (Notes sheet, author "Night shift") before the shoot. Change every "ground floor" line to "floor 1".
- **Nothing accessible:** film S6 in any corridor of the venue, keep the phone side as the real round (run on the page with "Done" taps), caption "Map: the real Urban Colab ground floor". Do not claim she is at the stop.

## 4. Prep checklist (shoot day)

- [ ] `git pull` on the demo machine; decide: is `feat/round-per-device` merged? If yes, numbers are per device ([N] = 8 today), lines say "Stop n of m · Fire extinguisher 0.0x"; if no, [N] = 7 and no device name in the stop line. **Do not mix takes from both.**
- [ ] Building fresh: `rm -rf agent_output/buildings/plan-89323a15 && scripts/install_demo_buildings.sh`, then start `uv run --env-file .env python -m web --port 8798`.
- [ ] Open the round panel, start South Corridor, write down [N] stops · [X] m and which extinguisher is stop 2 (today: 0.04, West Corridor).
- [ ] Seed the night-shift note with the bracket photo: `uv run python scripts/demo_seed.py user/plan-89323a15 --port 8798 --photo bracket.jpg`. It plans from the page's default start (the entrance room with the lowest id, today Project Room) and puts the note at that round's stop 2, which is also **0.04 West Corridor** = stop 2 from South Corridor. Check the printed asset name says 0.04.
- [ ] **Duplicate note risk:** `scripts/demo_knowledge_seed.py` (knowledge view history) writes the same text "Bracket is loose, always check it first." by "Night shift" on **Fire extinguisher 0.05** = stop 1 from South Corridor. If both seeds run, Wanda may read the note at stop 1 and again at stop 2. For the round takes, either skip the knowledge seed or ask Jennifer to change that line's text/device (her file; not changed here).
- [ ] Reset between takes: Undo Gisela's own note (or delete it on the server), clear the round, keep the night-shift note.
- [ ] Demo link on iPhone A (https tunnel, needed for the mic): `/?building=user/plan-89323a15#round=fire_extinguisher&area=Ground%20floor`. Mic allowed, speaker on, Do Not Disturb on, battery > 50 %, screen brightness max, auto-lock off.
- [ ] Mic: clip-on on Gisela; 5-s test take in the corridor (echo); quiet moment for the voice lines.
- [ ] Rehearse the full round twice without recording. Gisela says the lines exactly as in §1.
- [ ] No secrets on screen: no terminal with `.env`, no API keys, no personal tabs, no notifications, no tunnel URL in the browser bar of the laptop recording (crop or full-screen).
- [ ] Captions burned in (jury may watch muted), font large enough for a phone, source line on the 12.9 million caption.
- [ ] Cut to **exactly 2:00** (export check: 00:02:00:00 or less), watch once muted: the map side alone must tell the round.
- [ ] Keep every raw take and screen recording as backup; one person uploads (agreed in chat).

## 5. Depends on unmerged or unstable work (flag before the cut)

- `feat/round-per-device` (not in main 622c1c5): 8 stops · 106.7 m, "Stop n of m · <device>", device-to-device legs. Without it: 7 stops · 81.6 m, stops per room, and stop 1 has no step sheet (start room = stop room).
- `docs/HANDOVER_URBAN_COLAB_FLOORS.md`: adding the ground-floor west part (E.06) or more floors can add extinguishers and change [N]/[X] and the stop order. Re-read the panel after any building change.
- Wanda's spoken sentence for the round (number of stops/metres) is phrased by the LLM: do not script it, keep the real audio or mute it under the caption.
- Laptop and phone are separate sessions: the video says "same round", which is true because both call the same `plan_round`, but it does not claim the laptop plan syncs to the phone.

## 6. Production (one person, a Mac, about 2 hours after the shoot)

**Rule:** all narration is **voiceover**, recorded after the shoot to the final picture. On camera only two kinds of sound: Gisela's short lines to Wanda ("Hey Wanda …", "Done", "Note: …", "Finished") and Wanda's real app voice. Nothing else is spoken on location. Clean means: no ums, no room noise under the VO, no UI clutter, no secrets.

### Toolchain (pick the left column unless you already know the right one)

| Job | Recommended (fast, Mac) | Alternative |
|---|---|---|
| Laptop screen recording | macOS screenshot bar (Cmd+Shift+5 → "Record Selected Portion", Options → microphone off) | **Screen Studio** or **Cap** if installed: smooth auto-zoom on clicks makes the 11-s laptop beat look produced; not worth installing under time pressure |
| Phone screen recording | iPhone Control Centre → Screen Recording, **long-press → Microphone on** (so Gisela's line and Wanda's voice are in the file for sync) | – |
| Camera | second iPhone, 4K 30 fps, landscape, locked exposure (long-press on the subject) | any camera |
| Edit, split screen, captions | **CapCut desktop** (free): drag both clips onto two tracks, "Picture in picture" / crop to 50/50, auto-captions → edit → burn in on export | **iMovie** (split screen exists, captions are weak), **DaVinci Resolve** only if someone knows it, **Descript** if you want to edit by deleting words in the transcript |
| Voiceover | Record: iPhone Voice Memos or QuickTime, a headset/lavalier mic, small quiet room with soft surfaces (no corridor echo) | Generate: **ElevenLabs** (we already use it in the app). Use one narrator voice that is clearly **not** Wanda's app voice (`ELEVENLABS_VOICE_ID`), so the jury can tell narrator and product apart |
| Captions | CapCut auto-captions, fix names by hand ("Wanda", "Urban Colab", "South Corridor"), white text, dark box, bottom third, at least 5 % of frame height | Descript captions |
| Music | royalty-free, calm, no vocals (CapCut library, YouTube Audio Library, Pixabay Music), at **−25 to −30 dB** under the VO, ducked further under Wanda's voice | none (fine) |
| Architecture diagram | **Keynote** with Magic Move (see below), export as 1080p movie | an HTML motion slide (below), screen-recorded |

**Code-based options, honestly:**
- **Remotion** (render video from React) has official agent skills (`remotion-dev/skills` on GitHub), and community skills exist (e.g. `video-shotcraft`). It could render the split screen, animated captions and the diagram from our own twin components. But it needs a Node project, a render setup and someone who checks frame timing: realistic first result 2–4 hours. **Not before a 13:00 deadline.** Good later for a polished version.
- **HTML motion slide** for the 10-s diagram beat: one self-contained HTML file with CSS animations (boxes appear, arrows draw, a JSON snippet flashes), opened full screen and screen-recorded. A Claude session can write it in about 15 minutes, no install. Use it only if Keynote is not at hand.
- Agentic "do the whole edit" repos (OpenMontage etc.) are not worth the setup today.

### Step-by-step plan (times for one person)

| Step | What | Time |
|---|---|---|
| 1 | Prep checklist (§4), seed, reset, rehearse twice | 20 min |
| 2 | Shoot S1–S4, S9 (problem shots, plan photo) | 20 min |
| 3 | Shoot S6+S7 (round, split screen), 2–3 full takes, sync clap each take | 25 min |
| 4 | Record S5 (laptop planning), 3 takes | 10 min |
| 5 | Build the diagram (Keynote or HTML) and the 145 card | 20 min |
| 6 | AirDrop everything to the Mac, rename (below), pick best takes | 10 min |
| 7 | Rough cut in CapCut to the storyboard timings, split screen synced on the clap | 25 min |
| 8 | Record/generate the VO to the rough cut, place it, trim to fit | 15 min |
| 9 | Captions (auto, then correct), music, levels | 15 min |
| 10 | Export 1080p, QA (below), upload | 15 min |

Total about 3 h 15 min including the shoot; the edit alone (steps 5–10) is about 1 h 40 min. If short on time: skip music, skip the knowledge-view pan, use one round take.

**File naming** (one folder `video/`, not in git): `S06_round_cam_take2.mov`, `S07_round_phone_take2.mp4`, `S05_laptop_take1.mov`, `VO_problem_v2.m4a`, `DIAG_architecture.mov`, exports `wanda_2min_v1.mp4`, `wanda_2min_FINAL.mp4`.

**Export and upload:** 1920×1080, 30 fps, H.264, about 10–16 Mbit/s, AAC 48 kHz. Upload as **YouTube unlisted** (most reliable playback for the jury) or Loom; open the link in a private window to check it plays without login. One person uploads, agreed in chat.

### Architecture / trust beat: animated diagram (Keynote, 10 s + 8 s)

Slide A (1:32–1:42), white background, one accent colour, builds left to right, one box per beat of the VO:
1. Microphone icon → box **"Gisela's voice"**
2. Arrow → box **"Wanda (Claude)"**, small line under it: *"picks a tool, phrases the answer"*
3. Arrow → stack of three small boxes **"route · round · notes"**, label **"Deterministic tools (Python)"**
4. Arrow → box **"Building graph"**, sub-line: *"rooms, doors, stairs, lifts, devices"*
5. Return arrow back to Wanda, labelled **"facts"**; a tiny JSON flashes on it: `{"stops": [N], "total_m": [X]}` (numbers as on the panel)
6. Title builds last at the top: **"Facts from code. Language from the model."**

Card B (1:42–1:47): big **"145 benchmark answers. All computed by code. Reproducible."**

Slide C (1:47–1:55), Magic Move: the evacuation-plan photo (`demo/plans/urban-colab/photos/E05_ground_floor.jpeg`) shrinks to the left → arrow **"Level 4: plan reading"** → screenshot of the 2D map → 3D twin screenshot. Caption: **"Read from its evacuation plans."**

### Final QA checklist (watch the exported file, not the timeline)

- [ ] Length **≤ 2:00** (check the file's duration in Finder/QuickTime, not the editor).
- [ ] Product name spelled **"Wanda – the building that talks back"** on the title card and the end card; team names correct.
- [ ] Audio: VO peaks around −6 dB, no clipping; Wanda's voice understandable; music never louder than speech; no echo or wind.
- [ ] Captions legible on a phone held at arm's length; no typos in room names (English names only); source line under the 12.9 million number.
- [ ] Split screen in sync (her lips and the "Done" on the map within a few frames).
- [ ] Every number on screen matches the panel on shoot day and says which round it is (7 per room / 8 per device).
- [ ] No secrets, tunnel URLs, terminal with `.env`, personal tabs, notifications, battery warnings, email addresses.
- [ ] Watched once muted (the story still works) and once with eyes closed (the VO still works).
- [ ] Link plays in a private window; link pasted into the submission form.
