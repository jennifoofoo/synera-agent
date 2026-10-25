# Design tokens: Architectural white model

All values of the look live in `src/styles/tokens.css` (CSS custom properties). Component sheets only use those variables. The three.js scene cannot read CSS variables, so `src/model/palette.ts` (`COLOURS`, `GROUP_COLOURS`) mirrors the colours marked "scene" or "token". Change both together.

## Principles
- Depth from one layered shadow and frosted glass, not from borders: floating controls use `--glass` with `backdrop-filter: blur(var(--blur))` and `--shadow-float`. No hairline borders; only a 6 % rim (`--hairline`) where glass needs it on white, and 14 % dividers (`--hairline-strong`) inside segmented controls.
- Soft shapes: corners 10 / 14 / 18 px (`--radius-sm`, `--radius`, `--radius-lg`), pills (`--radius-pill`, 999px) for chips, round buttons and scene labels.
- One signal colour (Synera blue) for the route, primary buttons and selection. Green and red only for state (step-free, closed).
- The building is a near-white model. Slabs are very light greys, walls sit half way between slab and white, a thin light edge line (`COLOURS.edge`) and the light give the shape, not a dark colour. Colour only for the hue groups (spec: `docs/specs/room-colours.md`), the same five as before, now desaturated: kitchens and canteens, toilets and lockers, stairs and lifts, meeting rooms, and in factory halls the main walkways. Every other room type is a near-white grey that differs by lightness only. Colour never alone: each hue group has an icon and a row in the help legend (`LEGEND_GROUPS` in palette.ts), and the groups also differ in lightness so they stay apart with red-green colour blindness. No red or green room fills. Furniture takes the floor's own tone (machines a touch darker): show everything, but quietly. Important equipment shows as an icon.
- Same group colours in 2D and 3D. The 2D plan is north-up, turns neutral rooms near-white, keeps the hue groups and draws dark, crisp wall lines (`COLOURS.planEdge`).
- The route is the hero: a 6 px line (5.5 px in 3D) with a 2 px white casing, a 7 px halo of the signal colour at 16 %, thin white dashes travelling along it at walking pace, a pulsing start dot and a red destination pin that pops in (0.26 s). The red of the pin (`COLOURS.destination`) is used for nothing else.
- Closed is one quiet language, in `--danger` (never the safety red), 2D and 3D: a closed room is tinted red with an outline and carries a "Closed · name" badge, no big circles; a closed lift or stairs keeps its glyph with a red edge and a diagonal bar, its slab gets a pale red hatching and from the mid zoom tier a "Closed" tag; a closed door gets a red bar across its gap. The route card adds one line ("Avoids closed Office lift"), the help legend a "Closed" row. Reopening removes all of it at once (`model/closures.ts`).
- Motion: 150 ms ease-out (`--t-fast`) for state changes, 220 ms ease-out (`--t-base`) for things that appear, no springs. `prefers-reduced-motion` is respected: the store keeps a reduced-motion flag for the scene and a CSS media query switches transitions and animations off.

## Tokens
| Token | Value | Use |
|---|---|---|
| `--paper` | #f6f5f2 | app and scene background |
| `--paper-2` | #edebe6 | inset fields, hover, ground |
| `--surface` | #ffffff | solid cards, inputs |
| `--ink` | #1d2430 | text, selected label, chips |
| `--ink-2` | #5a626d | secondary text (5.9:1 on white) |
| `--hairline` | rgba(29,36,48,.06) | faint rim on glass |
| `--hairline-strong` | rgba(29,36,48,.14) | dividers inside segmented controls |
| `--glass` | rgba(255,255,255,.8) | floating controls |
| `--glass-strong` | rgba(255,255,255,.92) | text-heavy sheets, lists, labels |
| `--blur` | 16px | `backdrop-filter` radius of glass |
| `--shadow-float` | 0 1px 2px rgba(29,36,48,.06), 0 8px 24px rgba(29,36,48,.1) | floating controls and sheets |
| `--shadow-soft` | 0 1px 2px rgba(29,36,48,.05), 0 4px 12px rgba(29,36,48,.08) | small things (POI chips) |
| `--signal` | #004fab | route, primary button, selection (white on it 8.3:1) |
| `--signal-dark` / `--signal-soft` | #002478 / #ebf1ff | hover and pressed, selected fills (dark text on soft) |
| `--signal-ink` | #ffffff | text on signal |
| `--ok` / `--danger` / `--warn` / `--info` | #2f7d5b / #b3382c / #4a5260 / #004fab | state only; info = "you are here" |
| `--issue` | #a35f00 | open problem pins of place knowledge (amber, white "!" 5.0:1); notes are white pins with an ink speech bubble; never used for closures |
| `--room-food` | #efe6d4 | kitchen, canteen (sand) |
| `--room-sanitary` | #dce8ec | toilet, bathroom, locker room (pale aqua) |
| `--room-vertical` | #dcd6e6 | stairs and lifts, also the 3D shafts (muted violet) |
| `--room-meeting` | #dbe3d5 | meeting, seminar, lecture hall, library (pale sage) |
| `--room-walkway` | #f2edd3 | main aisles and traffic lanes in factory halls (pale lemon floor marking) |
| `--safety-red` / `--safety-green` | #a52019 / #237f52 | safety icons only (fire extinguisher; first aid, eyewash, defibrillator, exit) |
| `--radius-sm` / `--radius` / `--radius-lg` | 10 / 14 / 18 px | buttons and inputs, cards and panels, sheets |
| `--radius-pill` | 999px | chips, round buttons, scene labels |
| `--fs-12` .. `--fs-28` | 12 / 14 / 16 / 20 / 28 px | type scale, weights 400 / 500 / 600 |
| `--font` | Inter Variable, Inter, system sans | all text |
| `--label-tracking` | 0.08em | tiny uppercase section labels only |
| `--t-fast` | 150ms ease-out | state transitions |
| `--t-base` | 220ms cubic-bezier(.2,.7,.2,1) | things that appear (sheets, pins, badges) |

The aliases at the bottom of tokens.css (`--bg`, `--panel`, `--panel-solid`, `--navy`, `--line`, `--text`, `--muted`, `--accent`, `--gold`) keep older sheets working; new code should use the primary names.

Scene only (palette.ts `COLOURS`): wall top edges #9aa0a8 (ghost floors #c4c8ce), ground as a radial gradient from #f8f7f4 (under the building) to #eeedea with a faint dot lattice #cfd3d8 that fades with distance and pixel size, lights `sky` #ffffff, `groundLight` #dcd9d3 and `fill` #eef1f5, ambient occlusion tint #b4bcc6. 2D plan: wall lines #6b7079, zone lines #c9c8c3, furniture #dedcd6 (faint #e7e5e0), landmarks #8f8a80. Furniture #e4e3df, machines #d4d6d8, furniture outline #c3c6c9. Route casing #002478 in the plan palette, view cube white with #c9ccd2 strokes.

Lights and post-processing: `NoToneMapping` (so the near-white slabs keep their values), hemisphere light 1.6 (sky `#ffffff`, ground `#dcd9d3`), key light 1.3, fill light 0.5, and N8AO with radius 1.4, intensity 1.1 and the neutral tint above, so contact shadows stay soft and never turn into a grey wash.

Label contrast (ink #1d2430 on the slab, WCAG formula): corridors 14.2, outdoor 13.3, walkway 13.2, work 13.1, food 12.6, sanitary 12.5, logistics 12.4, production 12.3, meeting 11.8, technical 11.4 (the darkest slab, #dadde0), stairs and lifts 11.0. Every slab is above 10:1, far over the 4.5:1 AA limit. Secondary text (`--ink-2`) is still not used for room labels. Scene labels are `--glass-strong` pills with ink text.

## Typography
Inter Variable, self-hosted via `@fontsource-variable/inter` (imported in `src/main.tsx`), no external font request. Tabular numerals globally (`font-feature-settings: "tnum"`). Scale 12 / 14 / 16 / 20 / 28 px with weights 400, 500 and 600 only; the building name is 20 px / 600. Uppercase tracking only on tiny section labels (`.tiny-label`, planner headings).

## Second theme
Add `:root[data-theme="night"] { ... }` in tokens.css redefining the same names, and a matching second palette in palette.ts. The aliases keep older sheets working; new code should use the primary names.
