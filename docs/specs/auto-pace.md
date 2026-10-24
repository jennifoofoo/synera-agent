# Spec: Auto-Pace beim Begleiten

Status: Server gebaut (`building_agent/pace.py` Zustandsmaschine, `building_agent/pace_guide.py` Anbindung), Seitenteil gehört Leonie. Baut auf `docs/specs/position.md` (Begleiten-Modus) auf.

## Ziel
Wanda folgt dem Tempo der Person, ohne zu behaupten, sie wüsste, wo diese steht. Es gibt keine Ortung. Der Agent schätzt nur die Zeit pro Etappe und fragt danach kurz nach.

## Schalter und Modi
- "Auto-Pace" ist ein Schalter auf der Seite, Default **aus**. Aus: Begleiten wie in `position.md` (nur "next", "I'm at X").
- Zwei Stufen im Schalter: **Nachfragen** (Standard, wenn an) und **Weitersagen**.

## Ablauf
1. Beim Begleiten nennt der Agent mit jedem Schritt die erwartete Gehzeit der Etappe ("about twenty seconds"). Berechnung: Länge der Etappe in Metern geteilt durch 1,2 m/s, aufgerundet auf 5 Sekunden. Treppe und Aufzug bekommen einen Aufschlag (Treppe: Länge geteilt durch 0,8 m/s, Aufzug: Wartezeit 15 s wie im Routenmodell).
2. Die Seite startet nach der Sprachausgabe des Schritts einen Timer = erwartete Zeit plus 5 Sekunden.
3. Läuft der Timer ab und es kam keine Äußerung, schickt die Seite eine Nachricht mit Kontext `{guide_tick: true}` (nur als Kontextfeld, nie im Nachrichtentext). Der Server validiert: ein Begleiten-Zustand muss aktiv sein, und der Tick darf nur einmal pro Schritt zählen.
4. Der Agent antwortet je nach Stufe:
   - **Nachfragen:** "Ready for step three?" (ein Satz). Auf "yes", "next", "ja" folgt der Schritt.
   - **Weitersagen:** gibt den nächsten Schritt direkt aus, mit dem Satz "Say wait if you need a moment."
5. "Wait", "hold on", "moment", "warte" pausiert (Timer aus, Agent sagt nichts mehr bis "go", "ready", "weiter"). Jede Äußerung der Person setzt den Timer neu.
6. Ist der letzte Schritt gesprochen, endet der Timer. Nach der Ankunft kommt kein Tick mehr.

## Sicherheit und Ehrlichkeit
- Der Tick löst nie eine Änderung am Gebäude aus (Karte und klares Ja bleiben Pflicht).
- Maximal ein Tick pro Schritt, kein Dauer-Nachhaken, nach zwei unbeantworteten Ticks pausiert der Modus und sagt es einmal ("I'll wait here. Say go when you're ready.").
- Die Schätzung wird nie als Ortung dargestellt ("about twenty seconds", nicht "you should be at the lift now").
- Ist die Person laut Gespräch am falschen Ort ("I'm in the other corridor"), wird neu geroutet und der Timer neu gestartet.

## Vertrag für die Seite (gebaut)
**Schalter.** `POST /api/chat` bekommt das Top-Level-Feld `pace`: `"off"` (Default) | `"ask"` | `"say"`, wie `voice` bei jedem Chat-Aufruf mitschicken. Alles andere (fehlt, `"ASK"`, `true`, Zahl) zählt als `"off"`. Der Server merkt sich den Wert pro Sitzung am Guide-Zustand. Mit `"off"` ist alles wie bisher, kein Tick wird beantwortet.

**Pro Schritt.** `state.guide` (in jeder Chat-Antwort) hat additiv:
- `expected_seconds`: geschätzte Gehzeit der aktuellen Etappe (auf 5 s gerundet). Die Seite startet ihren Timer mit `expected_seconds + 5` Sekunden, nachdem die Sprachausgabe des Schritts zu Ende ist.
- `pace`: `"off" | "ask" | "say"`, wie der Server den Schalter gerade kennt.
- `pace_paused`: `true` nach "wait" oder nach der Pausenmeldung (Anzeige "wartet auf dich", Timer aus, bis die Person wieder etwas sagt).
Ist `guide` `null` (Überblick, Stopp, Ankunft), läuft kein Timer. Bei `pace != "off"` hängt der Server die Dauer ("That's about twenty seconds.") selbst an den gesprochenen Schritt.

**Tick.** Läuft der Timer ab und es kam keine Äußerung: `POST /api/chat {building, message: "", pace, context: {guide_tick: true, guide_step: <step_index aus state.guide>}}`. Nur ein echter Boolean `true` im `context` zählt (kein String, nie im Nachrichtentext, nicht auf Top-Level). `message` bleibt leer. Mit Text im `message` ist es eine normale Nachricht der Person. `guide_step` ist optional; passt er nicht zum aktuellen Schritt, wird der Tick verworfen (Timer und Wechsel haben sich überholt).

**Antwort auf einen Tick.** Normale Chat-Antwort mit `reply` und `state`. Der Server ruft dafür das Modell nicht auf (Ausnahme: Stufe Weitersagen auf Deutsch lässt den Schritt vom Modell formulieren).
- `reply` ist `""` und `tick_ignored: true`: nichts sagen, nichts anzeigen, keinen Timer starten. Gilt für: kein Begleiten aktiv, Schalter aus, Tick für einen anderen Schritt, zweiter Tick auf demselben Schritt, Pause, nach der Ankunft, offene Änderungs-Karte, Gebäude hat sich geändert.
- Stufe `ask`: "Ready for step 3?" (Deutsch: "Bereit für Schritt 3?"). Die Schritt-Nummer ist die des nächsten Schritts. Danach kommt von der Seite kein Timer mehr, bis die Person antwortet.
- Stufe `say`: der nächste Schritt, die Dauer und "Say wait if you need a moment." Der Zustand ist weitergerückt, `state.guide` zeigt den neuen Schritt, Timer neu starten.
- Nach dem dritten unbeantworteten Tick einmal "I'll wait here. Say go when you're ready." (`pace_paused: true`), danach nur noch `tick_ignored`.
Ein Tick ändert nie das Gebäude und taucht nie als Nachrichtentext im Gespräch auf.

**Äußerungen** (normale Chat-Nachrichten): "wait", "hold on", "moment", "warte" (höchstens 3 Wörter, sonst normale Frage) pausieren sofort, die Antwort kommt ohne Modell. "go", "ready", "weiter", "los" setzen fort, nach einer Pause oder Rückfrage ist das "nächster Schritt". Ein "yes", "ja" nach "Ready for step N?" geht zum nächsten Schritt. Jede Nachricht setzt den Zähler der unbeantworteten Ticks zurück. Nachrichten mit `Answer:` ignorieren Pace und Ticks. Ankunft beendet den Timer, Gebäudewechsel (`swap_building`) löscht den Pace-Zustand, eine Umleitung nach einer Sperrung startet den Timer für den neuen aktuellen Schritt.

**Abweichung zur Skizze in `pace.py`:** nach "Ready for step N?" wird kein zweiter Tick für denselben Schritt gezählt (maximal ein Tick pro Schritt, kein Nachhaken). Unbeantwortete Ticks summieren sich daher nur in Stufe `say`.

## Akzeptanzkriterien und Tests
1. Offline: Gehzeit-Berechnung (Gerade, Treppe, Aufzug, Randfälle: Länge 0, sehr lang).
2. Offline: Zustandsmaschine (Tick im aktiven Begleiten, Tick ohne Begleiten wird verworfen, doppelter Tick wird verworfen, nach "wait" kein Tick, nach Ankunft kein Tick, Pause nach zwei unbeantworteten Ticks).
3. Fälschen: `guide_tick` im Nachrichtentext oder als String setzt nichts.
4. Live (Harness): Route mit fünf Schritten, Stufe Nachfragen: Tick, "yes", nächster Schritt. Stufe Weitersagen: Tick liefert Schritt. "Wait" pausiert.
5. Handtest (HANDTEST Abschnitt H): mit Stoppuhr, gesprochene Zeit und Timer passen, Schalter aus bedeutet kein Tick.

## Aufteilung
| Teil | Wer | Zeit |
|---|---|---|
| Gehzeit, Tick-Validierung, Zustandsmaschine, Anbindung, Prompt-Zeilen, Tests (`tests/test_pace.py`, `tests/test_pace_wiring.py`, live `tests/live/test_pace.py`) | Jennifer (Agent) | ca. 1 h |
| Timer, Schalter, Kontextfeld `guide_tick`, Anzeige "wartet auf dich" | Leonie | ca. 1 h |
