# Spec: Wanda als kleines Fee-Licht

Stand: 25.10.2026, analysiert auf `integ/wow` 0af64c2 (Design-Staging, noch nicht auf main). Noch nicht bestätigt, nicht gebaut.

## Ziel
Wanda bekommt eine kleine Gestalt: ein leuchtendes Licht mit zwei angedeuteten Flügeln, das zeigt, was Wanda gerade tut. Keine Figur mit Gesicht, kein Comic. Es soll zum Namen passen und in einer Fabrik trotzdem ernst wirken.

## Ausgangslage (Analyse)
1. **Auf main** ist Wanda nur ein Ring um den Mikrofon-Knopf (`twin/src/ui/Omnibox.css`, `.ob-mic.listening`, `.ob-talk.speaking`). Der Ring wächst mit `--wanda-level` (0 bis 1, gesetzt aus `audioLevel.ts`).
2. **Auf `integ/wow`** hat die Design-Sitzung schon eine **Wanda-Leiste** gebaut: eine Glas-Pille unten mit der **Wanda-Kugel** (`<span class="wanda-orb {mode}">`), einer Textzeile und den Knöpfen Ask, Talk, Stop.
   - Die Kugel ist ein CSS-Kreis mit Verlauf in `--signal`, 40 px (am Handy 44 px).
   - Die Zustände gibt es schon, in `Omnibox.tsx` als `mode`: `idle`, `listening`, `thinking`, `speaking`, `reply`.
   - Schon da: `idle` atmet langsam (`wb-breathe`), `listening`/`speaking` wachsen und leuchten mit `--wanda-level`, `thinking` hat einen Bogen, der um die Kugel läuft (`wb-spin`).
   - Reduced motion ist schon abgedeckt.
3. **Folgerung:** Die Fee ist kein neues Bauteil, sondern ein Umbau dieser Kugel. Logik, Zustände und Lautstärke sind fertig. Es geht nur um Markup und CSS an einer Stelle. Deshalb ist das Risiko klein.

## Design
**Aufbau** (in `Omnibox.tsx` ersetzt das leere `<span class="wanda-orb">` ein kleines Inline-SVG, Klassen und `ref` bleiben):
- **Kern:** der bestehende leuchtende Kreis, etwas kleiner (etwa 60 Prozent der Fläche), damit Platz für Flügel und Schein bleibt. Die Außengröße bleibt 40 px bzw. 44 px, das Layout der Leiste ändert sich also nicht.
- **Flügel:** zwei Paar halbtransparente Tropfenformen links und rechts vom Kern, Füllung `--signal` mit niedriger Deckkraft, feine Kontur in `--signal-ink`. Keine neue Farbe.
- **Schein:** der weiche Glow, den es schon gibt (`box-shadow` mit `--wanda-level`).
- **Funken:** drei kleine Punkte (je 2 px), nur in `thinking` sichtbar.

**Zustände (nur CSS, Klassen gibt es schon):**
| Zustand | Bewegung |
|---|---|
| `idle` | schwebt 2 px auf und ab (3 s), Flügel schlagen langsam (Skalierung 1 zu 0,85 in x, 1,6 s) |
| `listening` | Flügel schneller (0,35 s), Schein folgt `--wanda-level` wie heute |
| `thinking` | drei Funken kreisen um den Kern (1,4 s, ersetzt den laufenden Bogen), Flügel ruhig |
| `speaking` | Kern pulsiert mit `--wanda-level` wie heute, Flügel schlagen mittel (0,6 s) |
| `reply` | wie `idle`, einmaliges kurzes Aufleuchten beim Eintritt |

**Technik:**
- Nur `transform` und `opacity` animieren, kein Layout, kein `filter: blur` in der Animation. Das hält das Handy flüssig, auch neben der 3D-Szene.
- Die Flügel schlagen per `transform: scaleX()` mit `transform-origin` am Kern.
- `prefers-reduced-motion`: keine Bewegung, Flügel stehen still, Zustände nur über Schein und Deckkraft (wie heute).
- Alles bleibt `aria-hidden`, die Texte und aria-labels der Knöpfe ändern sich nicht.

**Nicht Teil davon:** Die Fee fliegt nicht über die Karte und nicht die Route entlang. Das wäre Variante 2 (3 bis 4 Stunden in der 3D-Szene) und ist nach dem Freeze dran.

## Akzeptanzkriterien
1. In jedem der fünf Zustände ist die Fee sichtbar und unterscheidbar: Kern, zwei Flügel, in `thinking` die Funken.
2. Die Außengröße der Kugel bleibt 40 px am Desktop und 44 px am Handy. Die Wanda-Leiste verschiebt sich um keinen Pixel.
3. Keine neuen Farben: nur `--signal`, `--signal-dark`, `--signal-ink`, `--signal`-Mischungen.
4. Reduced motion: keine laufende CSS-Animation an der Fee (`getAnimations()` ist leer).
5. Am Handy keine spürbare Ruckelei. Mess-Grenze: kein Layout-Shift, nur Compositor-Animationen.
6. Bestehende Tests bleiben grün: `test_mobile.py`, `test_voice_followup.py`, `test_no_overlap.py`, `test_here_ui.py`, dazu `npm test`, `typecheck`, `lint`, Build.

## Testfälle
- **E2E neu `tests/e2e/test_wanda_fairy.py`** (Playwright, Desktop und pixel7, Fake-Chat-Server wie die anderen):
  - Pro Zustand den Store setzen und prüfen, dass `.wanda-orb` die richtige Klasse hat, das SVG zwei Flügel enthält und die Funken nur in `thinking` sichtbar sind.
  - Größe von `.wanda-orb` mit `getBoundingClientRect` vor und nach dem Umbau gleich (40 bzw. 44 px).
  - Mit `emulateMedia({ reducedMotion: "reduce" })` ist `document.querySelector('.wanda-orb').getAnimations({ subtree: true }).length` gleich 0.
- **Screenshots** aller fünf Zustände in den Scratchpad, für Jennifer zum Ansehen vor dem Merge.

## Dateien
- `twin/src/ui/Omnibox.tsx`: SVG in die Kugel, sonst nichts
- `twin/src/ui/Omnibox.css`: Abschnitt `.wanda-orb` umbauen, Reduced-Motion-Block ergänzen
- `tests/e2e/test_wanda_fairy.py` (neu)

## Aufwand
- SVG und Zustände: 40 min
- Test und Screenshots: 20 min
- Volle Browser-Suite: 20 min (bei hoher Last länger)

Gesamt etwa 1,5 Stunden.

## Reihenfolge und Zuständigkeit
- Baut die **Design-Sitzung**, weil sie den Look verantwortet und die Wanda-Leiste selbst gebaut hat.
- Erst wenn `integ/wow` auf main ist, dann auf einem eigenen Branch `feat/wanda-fairy` von main.
- Merge erst nach Jennifers Okay zu den Screenshots.

## Risiken
- **Wirkt verspielt:** Gegenmittel ist eine dezente Form ohne Gesicht. Wenn es in den Screenshots zu niedlich wirkt, bleiben nur die Flügel im `listening` und der Rest ist die heutige Kugel.
- **Merge-Konflikt mit `integ/wow`:** keiner, wenn erst danach gebaut wird.
- **Leistung am Handy:** klein, weil nur `transform`/`opacity`.
