# Spec: Wischen nach oben macht aus 2D 3D (wie Google Maps)

Stand: 25.10.2026, analysiert auf main 329f09e. Noch nicht bestätigt, nicht gebaut.

## Ziel
Zwei Finger parallel nach oben schieben kippt die Karte. Aus dem flachen Plan wird das 3D-Gebäude, ohne Knopf. Zwei Finger nach unten bis ganz flach führen zurück in den Plan. Der Blick bleibt dabei auf derselben Stelle, und der Maßstab springt nicht.

## Was heute im Code passiert (Analyse)
1. **2D und 3D sind zwei verschiedene Kameras.** `twin/src/scene/Scene.tsx` rendert in 2D eine `OrthographicCamera`, in 3D eine `PerspectiveCamera`. Beim Wechsel baut `CameraRig.tsx` die CameraControls neu auf (`key={flat ? "2d" : "3d"}`).
2. **Der Blick geht beim Wechsel verloren.** Die neue 3D-Kamera startet an ihrer Standardposition schräg neben dem Gebäude. Wer in 2D auf einen Raum gezoomt hat, landet nach dem Umschalten in der Gesamtansicht. Für eine Geste wäre das ein Sprung statt eines Kippens. Das ist der Kern der Arbeit.
3. **In 2D ist Kippen gesperrt.** `minPolarAngle = maxPolarAngle = PLAN_TILT` (0,004). Zwei Finger in 2D sind `touches.two = NONE`. `cameraMouse.ts` macht daraus Pinch-Zoom und Verschieben um den Mittelpunkt, niemals Kippen.
4. **In 3D kippen zwei Finger schon.** `TOUCH_DOLLY_ROTATE`: die Bewegung des Mittelpunkts dreht und kippt, der Abstand zoomt. Flachster Winkel `MAX_TILT` = 1,0 rad (etwa 57 Grad), steilster 0,08.
5. **Mac:** Option plus Wischen geht über `orbitDelta()` in `wheelInput.ts`. In 2D wird die senkrechte Komponente zum Drehen, nicht zum Kippen.
6. **Auch sonst hängt viel an `viewMode`:** Labels (Limit 80 statt 36), Things (`flat`), Hintergrundfarbe und Nebel, Etagenregeln (`floorRoles`), Routenlinie, Recenter, Kompass, FloorRail, CampusSite. Ein stufenloser Übergang wie bei Google würde all das betreffen. Deshalb bauen wir einen Schwellwert-Wechsel, der sich stufenlos anfühlt.
7. **Ein veralteter Kommentar** in `store.ts` sagt, Handys seien nur 2D. Die FloorRail erlaubt 3D am Handy längst (ohne AO). Kommentar beim Bauen korrigieren.

## Design
**Erkennen der Geste in 2D** (`cameraMouse.ts`, neben dem bestehenden Pinch):
- Zwei Finger liegen auf. Beide bewegen sich nach oben, jeweils mindestens 10 px.
- Der Fingerabstand ändert sich um weniger als 12 Prozent (sonst ist es Pinch).
- Die Bewegung ist überwiegend senkrecht (|dy| > 2 mal |dx| für den Mittelpunkt).
- Erst nach 24 px Mittelpunkt-Weg gilt die Geste als Kippen. Bis dahin läuft Pinch wie heute weiter, danach wird Pinch für diese Berührung abgeschaltet.
- Eine Richtung pro Berührung: ist entschieden "Kippen", zoomt diese Berührung nicht mehr, und umgekehrt.

**Übergabe 2D zu 3D** (neue Store-Aktion `tiltTo3d(handover)`):
- Vor dem Wechsel aus den 2D-Controls lesen: Ziel (target), Zoom, Azimut.
- Abstand für die 3D-Kamera aus dem Ortho-Zoom: sichtbare Höhe in Metern `hM = viewportHeight / zoom`, Abstand `d = (hM / 2) / tan(fov / 2)` mit fov 38 Grad. So bleibt der Maßstab in der Bildmitte gleich.
- `handover = { target, distance: d, azimuth, polar: 0.1 }` in den Store, dann `setViewMode("3d")`.
- `CameraRig.tsx`: wenn die 3D-Controls neu da sind und ein handover vorliegt, sofort ohne Animation `setLookAt` auf genau diese Werte, handover löschen. Ohne handover (Knopf, Taste T) bleibt alles wie heute.

**Weiter kippen mit dem Finger:**
- Nach dem Wechsel bekommt camera-controls die laufende Berührung nicht mit (Controls wurden neu gebaut). Deshalb steuert `cameraMouse.ts` den Kippwinkel selbst, bis die Finger loslassen: `polar = 0.1 + Mittelpunkt-dy * 0.006 rad/px`, begrenzt auf `MAX_TILT`, mit `rotatePolarTo(..., false)`.
- Ab der nächsten Berührung ist wieder camera-controls dran, wie heute.

**Zurück 3D zu 2D:**
- Nach dem Loslassen in 3D: Ist der Kippwinkel unter 0,12 rad (fast senkrecht) und kam die letzte Bewegung von einer Zwei-Finger-Geste nach unten, dann `tiltTo2d(handover)`.
- Abstand zurück in Zoom: `zoom = viewportHeight / (2 * d * tan(fov / 2))`, gleiches Ziel. Der bestehende Effekt "Entering 2D frames the focused floor" darf dann nicht neu einpassen, wenn ein handover vorliegt. Sonst springt es wieder.
- Kein Zurückspringen mitten in einer Geste, erst beim Loslassen. Sonst flackert es an der Grenze.

**Mac (Trackpad):**
- In 2D: Option plus Wischen nach oben (senkrecht überwiegt) ruft dieselbe Übergabe auf, danach kippt das Wischen wie heute in 3D.
- In 3D: Option plus Wischen bis fast senkrecht, dann 300 ms Pause in der Bewegung, dann zurück auf 2D.

**Was gleich bleibt:**
- 2D/3D-Knopf in der FloorRail und Taste T bleiben unverändert.
- Ein Finger verschiebt, Pinch zoomt, Drehen bleibt wie es ist.
- Reduced motion: kein Unterschied nötig, die Geste ist direkt.
- Kein neuer Look: keine neuen Farben, Schriften, Animationen. Die vorhandene Etagen-Animation (FloorRise) übernimmt das Aufstehen.

## Akzeptanzkriterien
1. Handy (pixel7), 2D, auf einen Raum gezoomt: zwei Finger 120 px nach oben. Danach ist `viewMode` "3d", der Raum ist weiter in der Bildmitte (Abweichung höchstens 10 Prozent der Bildbreite), der Kippwinkel ist größer als 0,3 rad.
2. Pinch in 2D (Finger auseinander, auch leicht schräg nach oben) schaltet nie auf 3D. Der Zoom ändert sich wie heute.
3. Zwei Finger parallel seitlich in 2D schalten nie auf 3D.
4. 3D, zwei Finger nach unten bis fast senkrecht, loslassen: `viewMode` ist "2d", Ziel und Maßstab bleiben (höchstens 10 Prozent Abweichung).
5. Knopf und Taste T verhalten sich genau wie vorher (Gesamtansicht in 3D, Etage einpassen in 2D).
6. Mac: Option plus Wischen nach oben in 2D schaltet auf 3D und kippt weiter.
7. Alle bestehenden Tests bleiben grün, vor allem `test_mobile.py`, `test_twin_controls.py`, `test_twin_trackpad.py`, `test_here_ui.py`, `test_semantic_zoom.py`, `test_no_overlap.py`.

## Testfälle
- **Unit (vitest):** neue reine Funktion `classifyTwoFinger(start, now)` gibt "pinch", "tilt-up", "tilt-down", "pan" oder "undecided" zurück. Fälle: reiner Pinch, Pinch mit leichtem Hochschieben, paralleles Hoch, paralleles Seitlich, Drehen, zu kurzer Weg. Dazu `orthoZoomToDistance` und `distanceToOrthoZoom`, Hin und Zurück ergibt denselben Wert.
- **E2E neu `tests/e2e/test_swipe_tilt.py`** (Playwright, pixel7, AO aus wie in `test_here_ui.py`): Kriterien 1 bis 5 mit synthetischen Touch-Events über CDP (`Input.dispatchTouchEvent`, zwei Touch-Punkte). Lesen über `window.__twinStore` und `window.__twinCamera`.
- **E2E Desktop:** Kriterium 6 mit `page.mouse.wheel` plus gedrückter Alt-Taste, analog `test_twin_trackpad.py`.

## Dateien
- `twin/src/scene/cameraMouse.ts`: Geste erkennen, Kippen steuern bis zum Loslassen
- `twin/src/scene/twoFinger.ts` (neu): `classifyTwoFinger`, Umrechnung Zoom und Abstand, plus `twoFinger.test.ts`
- `twin/src/scene/CameraRig.tsx`: handover anwenden, Einpassen beim Wechsel überspringen, Rückweg nach dem Loslassen
- `twin/src/scene/wheelInput.ts`: Option plus Wischen nach oben in 2D
- `twin/src/store.ts`: `viewHandover`, `tiltTo3d`, `tiltTo2d`, Kommentar korrigieren
- `tests/e2e/test_swipe_tilt.py` (neu)

## Aufwand und Reihenfolge
1. Übergabe ohne Geste (Knopf mit handover testen, der Blick bleibt stehen): 40 min. Lohnt sich allein schon, weil der Knopf heute den Blick verliert.
2. Geste am Handy erkennen und umschalten: 40 min
3. Weiter kippen bis zum Loslassen, Rückweg: 30 min
4. Mac-Variante: 20 min
5. E2E und volle Browser-Suite: 30 min (bei hoher Last länger)

Gesamt etwa 2,5 Stunden. Schritt 1 und 2 sind der Kern. 3 und 4 können wegfallen, wenn die Zeit knapp wird.

## Risiken
- **Falsches Kippen beim Zoomen:** wäre schlimmer als heute. Gegenmittel: strenge Schwellen, Unit-Tests, im Zweifel "pinch".
- **Merge-Konflikte:** gering. Geprüft gegen `integ/wow` 0af64c2: der Design-Branch ändert `CameraRig.tsx`, `cameraMouse.ts`, `wheelInput.ts` und `store.ts` nicht, nur 2 Zeilen in `Scene.tsx`. Der Bau kann also schon jetzt parallel von main abzweigen, in einem eigenen Worktree auf `feat/twin-swipe-tilt`. Vor dem Merge einmal main einmergen und die volle Browser-Suite laufen lassen.
- **Headless-Touch:** Zwei-Finger-Gesten über CDP sind in Playwright fummelig. Falls sie nicht zuverlässig laufen, testet E2E nur die Übergabe-Funktion direkt, die Geste prüft Jennifer am Handy.
- **Echtes Handy:** iOS Safari schickt bei zwei Fingern eigene Gesture-Events. `touchAction: none` ist auf dem Canvas gesetzt, trotzdem am iPhone prüfen.

## Offene Entscheidung für Jennifer
- Bauen ja oder nein, und wenn ja, nur Schritt 1 und 2 oder alles.
- Wer baut: die Haupt-Sitzung, über einen Agenten in einem eigenen Worktree auf `feat/twin-swipe-tilt`. Das ist Funktion, kein Look, also nicht die Design-Sitzung. Kann sofort starten, weil der Design-Branch die Kamera-Dateien nicht anfasst.
