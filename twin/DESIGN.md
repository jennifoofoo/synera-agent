# Design tokens: Blueprint minimal

All values of the look live in `src/styles/tokens.css` (CSS custom properties). Component sheets only use those variables. The three.js scene cannot read CSS variables, so `src/model/palette.ts` (`COLOURS`, `GROUP_COLOURS`) mirrors the colours marked "scene" or "token". Change both together.

## Principles
- Edges instead of shadows: 1 px hairline borders, one soft shadow (`--shadow-float`) for floating sheets, no blur, no gradients.
- Small square shapes: radii 4 to 6 px, no pills, icon buttons are 4 px squares.
- One signal colour (orange) for the route, primary buttons and selection. Green and red only for state (step-free, closed).
- Buildings are flat greys, room types differ by lightness, not hue.
- Motion is 150 ms ease-out, no springs.

## Tokens
| Token | Value | Use |
|---|---|---|
| `--paper` | #f4f2ee | app and scene background |
| `--paper-2` | #eae7e1 | inset fields, hover, ground |
| `--surface` | #fbfaf8 | cards, sheets, inputs |
| `--ink` | #1d2430 | text, active floor, chips |
| `--ink-2` | #5a626d | secondary text (5.9:1 on surface) |
| `--hairline` | rgba(29,36,48,.2) | borders |
| `--signal` | #c8460f | route, primary button, selection (white on it 4.8:1) |
| `--ok` / `--danger` / `--warn` / `--info` | #2f7d5b / #b3382c / #9a6a12 / #3a5f8a | state only; info = "you are here" |
| `--radius`, `-sm`, `-lg` | 5 / 4 / 6 px | cards and sheets, buttons and inputs, bottom sheets |
| `--shadow-float` | 0 4px 14px rgba(29,36,48,.1) | floating sheets only |
| `--t-fast` | 150ms ease-out | transitions |
| `--label-tracking` | 0.08em | tiny uppercase section labels only |

Scene only (palette.ts): stairs shafts #b7791f (muted amber), lift shafts #7a6a9a (muted violet), wall edges #2b323d, route casing #8f3209.

## Typography
System sans (Inter if installed). Tabular numerals on floor numbers, route facts, labels and chips. Uppercase tracking only on tiny section labels (`.tiny-label`, planner headings).

## Second theme
Add `:root[data-theme="night"] { ... }` in tokens.css redefining the same names, and a matching second palette in palette.ts. The aliases at the bottom of tokens.css (`--bg`, `--panel`, `--navy`, `--line`, `--gold`, ...) keep older sheets working; new code should use the primary names.
