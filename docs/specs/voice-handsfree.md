# Spec: Hands-free Voice und kurze gesprochene Rückfragen

Status: bestätigt von Jennifer (Umfang), Seitenteil (Teil B) gehört Leonie und wartet auf ihre Zusage.

## Ziel
Techniker mit vollen Händen fragen, ohne einen Knopf zu drücken, und der Agent fragt kurz zurück, wenn etwas fehlt. Passt zur Persona "Service technician: hands full, phone in pocket, wants voice".

## Teil A: kurze gesprochene Rückfragen (Server, Jennifer)
- Die Seite sendet bei Spracheingabe das Flag `voice: true` im Chat-Aufruf. Nur dann gelten die Sprachregeln, im Textchat ändert sich nichts. Das Flag kommt vom Server-Kontext, nie aus dem Nachrichtentext (kein Fälschen).
- Sprachregeln (eigene Konstante `VOICE_RULES`, nur bei `voice: true` an den Prompt gehängt):
  - Höchstens eine Rückfrage pro Antwort, ein Satz, am Ende.
  - Höchstens zwei Optionen, mit Namen ("Kitchen zero point two eight, or the one upstairs?"). Mehr Treffer: die zwei nächsten nennen, sagen dass es weitere gibt.
  - Beginnt mit der Annahme, wenn eine sinnvolle existiert ("I'll start from your last spot, Kitchen zero point two eight.").
  - Keine Tabellen, Listen, Markdown, IDs. Kurze Sätze. Zahlen und Räume so, dass sie sprechbar sind.
  - Zusammenspiel mit dem Begleiten-Modus (docs/specs/position.md): Überblick mit Angebot, dann Schritt für Schritt.
- Anfragevertrag (für `voice.js`, Leonie): `POST /api/chat` bekommt ein optionales Feld `voice` auf der obersten Ebene des JSON-Bodys, neben `message` und `context`, Typ Boolean. Nur ein echtes `true` schaltet die Sprachregeln für genau diese Antwort ein. Fehlt das Feld, oder ist es `false`, ein String (`"true"`), eine Zahl oder etwas anderes, gilt Textchat. Beispiel: `{"building": "...", "message": "where is the coffee machine?", "voice": true}`. Bei Spracheingabe immer senden, bei getipptem Text weglassen. Im `context` oder im Nachrichtentext hat das Flag keine Wirkung. Umsetzung: `building_agent/voice_rules.py`.
- Benchmark-Modus (Nachrichten mit `Answer:`) bleibt unverändert: nie Rückfragen.
- Das Sprech-Modul setzt vor der Schlussfrage eine Pause von 1,2 s (Arbeit des Sprech-Agenten, `web/speech.py`).

## Teil B: Aktivierungswort (Seite, Leonie)
- Name (Konstante, ein Wort ändern): **Wanda** (die Stimme ist weiblich). Aktivierung "Hey Wanda". Antwort beim reinen Aufruf: kurzer Ton und gesprochen "I'm here.". Danach ist die nächste Äußerung die Frage.
- Web Speech API dauerhaft (`continuous`, `interimResults`). Erkennungstext wird auf das Wort geprüft: Satz beginnt mit "hey wanda" (auch "hi wanda", "okay wanda", Schreibvarianten "wonda", "wander" per kleiner Ähnlichkeitsliste). Rest des Satzes wird als Frage gesendet. Nur das Wort: Ton plus "I'm here.", dann die nächste Äußerung.
- Barge-in: wird das Wort während der Sprachausgabe erkannt, stoppt die Ausgabe sofort.
- Neustart: Chrome beendet die Dauererkennung nach Stille, die Seite startet sie sauber neu, ohne doppelte Instanzen.
- Schalter "Hands-free" (Default aus, Push-to-talk bleibt), sichtbares Mikrofon-Symbol und "mute"-Knopf. Zustand nie versteckt: man sieht, wann zugehört wird.
- Nur Chrome, Seite im Vordergrund, localhost oder https. Nicht unterstütztes Gerät: Schalter deaktiviert mit Hinweis.
- Keine Aktion bei Hintergrundgeräuschen: nur Sätze mit dem Aktivierungswort am Anfang lösen aus.
- Änderungen am Gebäude laufen weiter über Karte und klares Ja (gesprochen).

## Akzeptanzkriterien und Tests
Teil A (offline und live):
1. Mit `voice: true` enden Rückfragen nach höchstens einem Satz mit höchstens zwei Optionen (Live-Test mit zwei Küchen, mehreren Kaffeemaschinen).
2. Ohne Flag unverändert (Prompt-Vergleich, bestehende Live-Skripte 1 bis 6 grün).
3. Flag im Nachrichtentext ("voice: true") schaltet nichts ein, ein unbekanntes Kontextfeld wird verworfen.
4. Benchmark-Modus: nie Rückfragen, auch mit Flag.
5. Antworten im Sprachmodus enthalten kein Markdown und keine IDs (Check auf Zeichen und Muster).
Teil B (manuell, Handtest in `docs/HANDTEST.md` Abschnitt G):
6. "Hey Wanda, where is the coffee machine?" löst eine Frage aus. Ohne das Wort passiert nichts.
7. "Hey Wanda" allein: Ton und "I'm here.", dann Frage.
8. Aktivierungswort während der Ausgabe stoppt sie.
9. Nach 2 Minuten Stille hört die Seite weiter zu (Neustart).
10. Schalter aus: kein Dauer-Mikrofon.

## Reihenfolge
Teil A zuerst (Server, ca. 45 Minuten, nach `feat/position` mergebar). Teil B nach dem Handtest, wenn die normale Spracherkennung mit Raumnummern brauchbar ist.
