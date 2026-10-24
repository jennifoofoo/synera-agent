# Spec: Interaction-Skripte als Live-Tests

Status: ENTWURF (wartet auf Bestätigung von Jennifer).

## Ziel
Die 25 Interaction-Punkte kommen aus einem Skript-Gespräch mit schwierigen Nutzern. Wir bauen dieselben Szenarien als Tests, die ein echtes Gespräch mit dem Agenten führen und prüfen, ob er sich richtig verhält. Das schützt vor Rückschritten, wenn wir Prompt oder Tools ändern.

## Prinzip: prüfen, was der Agent tut, nicht wie er es sagt
- Harte Prüfungen laufen auf **Tool-Aufrufen und Zuständen** (deterministisch): welches Tool wurde in welcher Runde gerufen, was steht in `bm.closed`, wie viele Schritte kamen zurück, wurde ein Raum erfunden.
- Weiche Kriterien (zum Beispiel "Karte in einfachen Worten") prüft optional ein günstiger Haiku-Richter mit festem Kriterium. Ein Test besteht nie nur wegen des Richters.

## Harness (ich baue, vor den Skripten)
- `tests/live/harness.py`: `run_script(building, turns, ...)` führt Nutzerzeilen nacheinander durch **einen** `Agent`, zeichnet pro Runde Antwort und alle Tool-Aufrufe (Name, Argumente, Ergebnis) auf und gibt sie zurück.
- Modell für Live-Tests: Sonnet (per Monkeypatch von `starter_agent.agent.MODEL`), Antworten gecacht in `agent_output/live_cache/`, damit Wiederholungen nichts kosten.
- Marker `@pytest.mark.live`. `scripts/check.sh` lässt sie aus (kein Key nötig). Aufruf: `uv run --env-file .env pytest -m live`.
- Gebäude: ein festes procedural Dev-Gebäude und ein OSM-Gebäude, Räume werden aus den Daten gesucht, nichts auf Namen hartcodiert.

## Die sechs Skripte (Nutzerzeilen sind Beispiele, der Test sucht passende Räume aus den Daten)
1. **Vage:** "Wo gibt's Kaffee?" Erwartet: Suche läuft, bei einem klaren Treffer direkt Antwort, nur bei mehreren eine kurze Rückfrage mit Optionen. Nie ein erfundener Raum.
2. **Falscher Raum:** Raum, den es nicht gibt ("Raum 9.99"). Erwartet: kein Route-Aufruf auf einen geratenen Raum, ähnliche Treffer werden angeboten.
3. **Meinungsänderung:** erst Ziel A, dann "doch lieber Ziel B". Erwartet: Start bleibt, neue Route zu B, kein erneutes Nachfragen nach dem Start.
4. **Barrierefrei:** "Ich sitze im Rollstuhl, wo ist ...". Erwartet: `step_free=true` schon im ersten Route-Aufruf, Antwort nennt Umweg oder fehlende Route ehrlich.
5. **Hände voll:** "Ich trage Kisten, sag es kurz." Erwartet: höchstens 3 Schritte je Antwort, Landmarken, "weiter" liefert den nächsten Block, "nochmal" wiederholt den letzten.
6. **Facility Manager:** "Sperr Aufzug 1" oder "Tür zwischen A und B". Erwartet: Runde 1 `propose_change` und Karte, **kein** `confirm_change`, `bm` unverändert. Antwort "ja": Änderung greift, Folge für die Route wird genannt. Variante mit "nein": nichts ändert sich.

## Gegner-Varianten (der Verifier-Agent baut sie nach)
Je Skript mindestens eine Störung: knappe Antwort ("mach einfach"), Rechtschreibfehler, Themenwechsel zwischen Vorschlag und Ja, doppeltes Ja, Widerspruch ("ja, aber nicht Aufzug 1"). Der Test muss zeigen, dass eine Änderung nie ohne klares Ja passiert.

## Aufteilung
- Ich: Harness, Marker, `check.sh`-Anpassung (`-m "not live"`), Review.
- Builder A (Worktree): Skripte 1, 2, 3 in `tests/live/test_script_1_3.py`.
- Builder B (Worktree): Skripte 4, 5, 6 in `tests/live/test_script_4_6.py`.
- Verifier (frischer Agent, nach den Buildern): liest nur diese Spec, versucht die Skripte mit den Gegner-Varianten zu brechen, meldet Lücken. Er ändert nichts außer `tests/live/test_adversarial.py`.
- Kostenrahmen: höchstens $5 für den ersten Gesamtlauf (Sonnet, gecacht). Bei Limit-Fehler abbrechen.

## Fertig, wenn
- Alle sechs Skripte bestehen live, die Gegner-Varianten schlagen nicht durch (oder die Lücke ist als Bug in `STATUS.md` eingetragen).
- `scripts/check.sh` bleibt grün und läuft ohne Key.
- Ergebnis und Kosten stehen in `docs/eval-log.md`.
