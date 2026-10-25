# Spec: Chat als Seitenleiste links am Laptop

Stand: 25.10.2026, analysiert auf main a943624 und integ/wow 40da997. Noch nicht bestätigt, nicht gebaut.

## Vorgeschichte
In `docs/WORK_IN_PROGRESS.md` (Commit 05060db, Sonntag 03:45) ist `feat/twin-desktop-flow` belegt, zusammen mit dem weichen Wechsel 2D/3D. Der Branch existiert weder lokal noch auf origin, es gibt keinen Code. Der 2D/3D-Teil steht jetzt ausführlicher in `docs/specs/swipe-tilt.md`, diese Spec deckt nur die Seitenleiste ab.

## Ziel
Am Laptop (Profil `planner`) sitzt der Chat als feste Spalte links: Eingabe oben, Verlauf immer sichtbar, darunter Antwort, Routenkarte und Begleiten in derselben Spalte. Die Karte nutzt den Rest des Bildschirms, und die Kamera rahmt im freien Bereich. Handy (`worker`) bleibt genau wie heute.

## Ausgangslage (Analyse)
1. **Layout heute** (`twin/src/App.tsx` auf integ/wow): Unten liegt ein `.dock` mit `CampusCard`, `NotesDock`, `Walk` oder `Card` und `Omnibox` (auf integ/wow die neue Wanda-Leiste). Rechts öffnet sich der `Planner` als Seitenblatt.
2. **Kamera kennt nur unten, oben und rechts:** `CameraRig.tsx` `applyFrame()` baut einen größeren virtuellen Rahmen aus `bottomInset`, `topInset`, `rightInset` und rendert per `setViewOffset(fullW, fullH, 0, bottom, w, h)`. Der x-Versatz ist fest 0, ein linker Rand fehlt.
3. **Vorbild für die Messung:** `Planner.tsx` misst sein Blatt per `ResizeObserver` und setzt `setRightInset`. Die Seitenleiste macht dasselbe für links.
4. **Der Verlauf** (`.ob-history`) ist heute ein Aufklapp-Feld mit `max-height: 46vh` und zeigt nur die letzten Antworten gekürzt (4 Zeilen).
5. **Konfliktlage:** `Omnibox.tsx/.css` sind auf integ/wow stark umgebaut (Wanda-Leiste, +213 Zeilen). Deshalb erst nach dem Merge von integ/wow bauen, sonst gibt es doppelte Arbeit und Konflikte.

## Design
**Layout (nur `planner` und Breite ab 1024 px):**
- `.app.planner` wird ein Raster: Spalte links fest 380 px (ab 1440 px 420 px), rechts die Karte.
- Die linke Spalte `.sidebar` enthält von oben nach unten: Gebäude-Titel und Etage (heute `TopBar`, nur verschoben), die Eingabe mit der Wanda-Kugel, den Verlauf (scrollt, volle Antworten, kein Abschneiden), und unten angedockt `Card` oder `Walk`, `NotesDock`, `CampusCard`.
- Die Karte (`Scene`), `FloorRail`, `Recenter`, Kompass bleiben im rechten Bereich.
- Der `Planner` rechts bleibt, wo er ist.
- Unter 1024 px oder bei `worker`: alles wie heute.

**Kamera:**
- Neuer Wert `leftInset` im Store, analog zu `rightInset`, gesetzt per `ResizeObserver` auf `.sidebar`.
- `applyFrame()`: `fullW = w + left + right`, `setViewOffset(fullW, fullH, left, bottom, w, h)`.
- Einfacher und robuster: Ist das Canvas selbst nur so breit wie die Karte (CSS-Raster), braucht die Kamera gar keinen linken Rand. Das zuerst ausprobieren, `leftInset` nur, falls das Canvas bildschirmbreit bleiben muss (Übergänge, Glas-Effekt der Leiste über der Karte).

**Verhalten:**
- Der Verlauf ist immer sichtbar und scrollt automatisch zur neuesten Antwort.
- Gesprochene Antworten erscheinen genauso im Verlauf.
- Funde aus dem Chat, also Raum anklicken, Foto öffnen oder Route zeigen, wirken wie heute auf die Karte.
- Leiste einklappen: ein Knopf oben in der Leiste. Eingeklappt bleibt nur die Wanda-Kugel links oben, die Karte wird voll breit. Der Zustand bleibt in `localStorage` (mit try/catch).

**Was gleich bleibt:**
- Keine neuen Farben, Schriften oder Abstände außerhalb der bestehenden Tokens. Den Look macht die Design-Sitzung.
- Alle aria-labels, Tastatur-Kürzel und die Funktion von Ask, Talk und Stop.

## Akzeptanzkriterien
1. Laptop (1440 x 900, `planner`): Die Leiste ist links 420 px breit. Die Eingabe ist oben, und der Verlauf zeigt alle Antworten vollständig.
2. Die Karte überdeckt die Leiste nie. Gebäude und Route sind nach "Home" vollständig im rechten Bereich zu sehen (Rahmen-Prüfung über `getBoundingClientRect` der Labels).
3. Route anfragen: Die Routenkarte erscheint in der Leiste, nicht über der Karte. Begleiten zeigt seine Schritte ebenfalls in der Leiste.
4. Einklappen und Ausklappen funktioniert, und die Karte wird voll breit. Nach einem Neuladen ist der Zustand gleich.
5. Handy (pixel7) und Fenster unter 1024 px: Das Layout ist pixelgleich zu vorher, `test_mobile.py` ist unverändert grün.
6. Keine Überlappungen: `test_no_overlap.py` ist grün, mit zusätzlichem Fall "Laptop mit Seitenleiste".
7. Bestehende Tests grün: `test_here_ui`, `test_walk_with_me`, `test_voice_followup`, `test_round_and_notes`, `test_twin_controls`, dazu `npm test`, `typecheck`, `lint` und der Build.

## Testfälle
- **E2E neu `tests/e2e/test_chat_sidebar.py`** (Playwright, Desktop 1440 x 900 und 1024 x 768, Fake-Chat-Server):
  - Leiste sichtbar, Breite stimmt, Eingabe oberhalb des Verlaufs.
  - Drei Fragen stellen: Alle drei Antworten stehen ungekürzt im Verlauf, und der Verlauf ist nach unten gescrollt.
  - Route anfragen: `.card` liegt innerhalb von `.sidebar`, und kein Label der Karte liegt links von der Leistenkante.
  - Einklappen: Die Leiste ist weg, das Canvas ist voll breit. Nach einem Neuladen ist sie weiterhin eingeklappt.
  - Profil `worker` bzw. 800 px Breite: Es gibt kein `.sidebar`.
- **Fall in `test_no_overlap.py`:** Desktop mit Leiste, Route und angetipptem Raum.

## Dateien
- `twin/src/App.tsx`: `.sidebar`-Spalte für `planner`, Komponenten umhängen
- `twin/src/styles.css` (bzw. die Layout-Datei der Design-Sitzung): Raster, Breiten, Einklappen
- `twin/src/ui/Omnibox.tsx/.css`: Verlauf als feste, scrollende Liste im Leisten-Modus
- `twin/src/store.ts`: `sidebarCollapsed`, nur falls nötig `leftInset`
- `twin/src/scene/CameraRig.tsx`: nur falls nötig der linke Rand in `applyFrame()`
- `tests/e2e/test_chat_sidebar.py` (neu), ein Fall in `tests/e2e/test_no_overlap.py`

## Aufwand
- Raster und Umhängen: 45 min
- Verlauf als Liste, Einklappen: 30 min
- Kamera-Rahmen, falls nötig: 20 min
- Tests und volle Browser-Suite: 40 min

Gesamt etwa 2 bis 2,5 Stunden.

## Reihenfolge und Zuständigkeit
- Erst nach dem Merge von integ/wow auf main, dann eigener Branch `feat/twin-desktop-flow` von main (Name aus der bestehenden Belegung).
- Bauen sollte die **Design-Sitzung**: Das ist Layout und Look, und Omnibox sowie Wanda-Leiste sind ihre Dateien.
- Nicht parallel zur Fee (`docs/specs/wanda-fairy.md`) bauen, beide ändern `Omnibox.*`. Erst die Seitenleiste, dann die Fee, oder beides in einer Sitzung nacheinander.
- Die Belegung in `docs/WORK_IN_PROGRESS.md` aktualisieren: 2D/3D-Teil verweist auf `docs/specs/swipe-tilt.md`.

## Risiken
- **Zeit bis zum Freeze:** 2 bis 2,5 Stunden plus Merge. Wenn es knapp wird, ist der Laptop-Chat unten in der Wanda-Leiste ein akzeptabler Stand, für das Video reicht er.
- **Konflikte mit Card.tsx und Walk.tsx:** Leonies Runde hängt daran. Deshalb dort nur umhängen und CSS, keine Logik ändern.
- **Demo-Gerät:** Wird die Demo am Handy gezeigt, sieht die Jury die Leiste gar nicht. Dann ist die Geste 2D zu 3D wichtiger.
