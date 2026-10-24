# Spec: Auto-Pace beim Begleiten

Status: ENTWURF, baut auf `docs/specs/position.md` (Begleiten-Modus) auf und startet erst, wenn dieser gemergt und im Handtest sauber ist. Seitenteil gehört Leonie.

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

## Akzeptanzkriterien und Tests
1. Offline: Gehzeit-Berechnung (Gerade, Treppe, Aufzug, Randfälle: Länge 0, sehr lang).
2. Offline: Zustandsmaschine (Tick im aktiven Begleiten, Tick ohne Begleiten wird verworfen, doppelter Tick wird verworfen, nach "wait" kein Tick, nach Ankunft kein Tick, Pause nach zwei unbeantworteten Ticks).
3. Fälschen: `guide_tick` im Nachrichtentext oder als String setzt nichts.
4. Live (Harness): Route mit fünf Schritten, Stufe Nachfragen: Tick, "yes", nächster Schritt. Stufe Weitersagen: Tick liefert Schritt. "Wait" pausiert.
5. Handtest (HANDTEST Abschnitt H): mit Stoppuhr, gesprochene Zeit und Timer passen, Schalter aus bedeutet kein Tick.

## Aufteilung
| Teil | Wer | Zeit |
|---|---|---|
| Gehzeit, Tick-Validierung, Zustandsmaschine, Prompt-Zeilen, Tests | Jennifer (Agent) | ca. 1 h |
| Timer, Schalter, Kontextfeld `guide_tick`, Anzeige "wartet auf dich" | Leonie | ca. 1 h |
