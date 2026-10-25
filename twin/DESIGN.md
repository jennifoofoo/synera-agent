# Design tokens: Blueprint minimal

All values of the look live in `src/styles/tokens.css` (CSS custom properties). Component sheets only use those variables. The three.js scene cannot read CSS variables, so `src/model/palette.ts` (`COLOURS`, `GROUP_COLOURS`) mirrors the colours marked "scene" or "token". Change both together.

## Principles
- Edges instead of shadows: 1 px hairline borders, one soft shadow (`--shadow-float`) for floating sheets, no blur, no gradients.
- Small square shapes: radii 4 to 6 px, no pills, icon buttons are 4 px squares.
- One signal colour (Synera blue) for the route, primary buttons and selection. Green and red only for state (step-free, closed).
- Buildings are flat greys. Hue only for sought-after groups (spec: `docs/specs/room-colours.md`): kitchens and canteens, toilets and lockers, stairs and lifts, meeting rooms, and in factory halls the main walkways get a very pale hue; every other room type is a neutral grey that differs by lightness only. Colour never alone: each hue group has an icon and a row in the help legend (`LEGEND_GROUPS` in palette.ts). The hue groups also differ in lightness so they stay apart with red-green colour blindness (checked with Chrome's deuteranopia emulation). No red or green room fills.
- Walls one step (8 %) darker than their slab, never near-black. Furniture neutral and light, machines a little darker; important equipment shows as an icon, not as a colour.
- Same group colours in 2D and 3D (the 2D plan turns neutral rooms near-white and keeps the hue groups).
- Motion is 150 ms ease-out, no springs.
- Closed is one language, in `--danger` (never the safety red), 2D and 3D: a closed lift or stairs keeps its square glyph but with a red edge and a diagonal bar (prohibition style), its slab gets a pale red hatching instead of the violet, and from the mid zoom tier on a "Closed" tag sits beside the glyph; a closed door gets a red bar across its gap; a closed room a red disc. The route card adds one quiet line ("Avoids closed Office lift"), the help legend a "Closed" row. Reopening removes all of it at once (`model/closures.ts`).

## Tokens
| Token | Value | Use |
|---|---|---|
| `--paper` | #f4f2ee | app and scene background |
| `--paper-2` | #eae7e1 | inset fields, hover, ground |
| `--surface` | #fbfaf8 | cards, sheets, inputs |
| `--ink` | #1d2430 | text, active floor, chips |
| `--ink-2` | #5a626d | secondary text (5.9:1 on surface) |
| `--hairline` | rgba(29,36,48,.2) | borders |
| `--signal` | #004fab | route, primary button, selection (white on it 8.3:1) |
| `--signal-dark` / `--signal-soft` | #002478 / #ebf1ff | hover and pressed, selected fills (use dark text on soft) |
| `--ok` / `--danger` / `--warn` / `--info` | #2f7d5b / #b3382c / #4a5260 / #004fab | state only; info = "you are here" |
| `--radius`, `-sm`, `-lg` | 5 / 4 / 6 px | cards and sheets, buttons and inputs, bottom sheets |
| `--room-food` | #e8d8b8 | kitchen, canteen (sand) |
| `--room-sanitary` | #cde2e8 | toilet, bathroom, locker room (pale aqua) |
| `--room-vertical` | #c5bcd8 | stairs and lifts, also the 3D shafts (muted violet) |
| `--room-meeting` | #c9d6c0 | meeting, seminar, lecture hall, library (pale sage) |
| `--room-walkway` | #eee7b8 | main aisles and traffic lanes in factory halls (pale lemon floor marking) |
| `--safety-red` / `--safety-green` | #a52019 / #237f52 | safety icons only (fire extinguisher; first aid, eyewash, defibrillator, exit) |
| `--shadow-float` | 0 4px 14px rgba(29,36,48,.1) | floating sheets only |
| `--t-fast` | 150ms ease-out | transitions |
| `--label-tracking` | 0.08em | tiny uppercase section labels only |

Scene only (palette.ts): neutral room greys in `GROUP_COLOURS` (corridors #efede8, work and living #dcdad4, production #c4c7cb, logistics #cbc9c3, technical #b4b8bd, outdoor #e2e3dc), stairs and lift shafts in the vertical wall colour #b5adc7, wall edges #48505b, furniture #d0d2d4, machines #aeb2b8, route casing #002478.

Label contrast (ink #1d2430 on the slab): walkway 12.4, corridors 13.3, food 11.1, toilets 11.6, meeting 10.3, stairs and lifts 8.6, work 11.2, production 9.2, logistics 9.4, technical 7.8, outdoor 12.1 (all above 4.5:1; labels also carry a paper halo). Secondary text (`--ink-2`) is not used for room labels: it drops below 4.5:1 on the darker greys.

## Typography
System sans (Inter if installed). Tabular numerals on floor numbers, route facts, labels and chips. Uppercase tracking only on tiny section labels (`.tiny-label`, planner headings).

## Second theme
Add `:root[data-theme="night"] { ... }` in tokens.css redefining the same names, and a matching second palette in palette.ts. The aliases at the bottom of tokens.css (`--bg`, `--panel`, `--navy`, `--line`, `--gold`, ...) keep older sheets working; new code should use the primary names.
