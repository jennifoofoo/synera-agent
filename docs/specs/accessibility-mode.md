# Spec: Accessibility-Modus (Profil im Gespräch, Türbreite, ehrliche Grenzen)

Status: ENTWURF, wartet auf Bestätigung von Jennifer (und Leonie für die Oberfläche).
Grundlage: Synera-Präsentation, Persona "Wheelchair user: needs step-free routes and wide doors, every time, without asking twice"; README Level 5 "Accessibility: wider doors, step-free and quiet routes"; Idee 1 in `docs/IDEAS.md`.

## Ziel
Eine Person nennt ihre Bedürfnisse einmal ("ich sitze im Rollstuhl, 0,85 m breit"). Danach halten **alle** Antworten sie ein, ohne dass sie noch einmal fragen muss: Routen, Wegbeschreibungen, Zielvorschläge, "What changes?" und die Anzeige. Ist etwas nicht möglich, sagt der Agent es ehrlich ("es gibt keinen Weg ohne Stufen") und nennt, was fehlt.

## Nicht-Ziele
Medizinische Aussagen oder Garantien. Keine Messwerte für Lärm, Licht oder Menschenmengen (die Daten haben sie nicht). Wendekreise und Rampenneigung sind nicht modelliert. Gesundheitsangaben werden nicht gespeichert oder geloggt.

## Profile (Phase 1 zuerst)
| Profil | Wirkung | Phase |
|---|---|---|
| `wheelchair` | nur stufenfreie Verbindungen, Türen mindestens `door_width_m` (Standard 0,9, wählbar bis 1,2), Aufzüge erlaubt, Treppen nie, Eingänge nur stufenfrei, Ziele nur erreichbare Räume | 1 |
| `limited_walking` (Krücken, Rollator, Erschöpfung) | Aufzug vor Treppe (Treppe nur mit Warnung), kurze Strecken bevorzugt, Pausenpunkte (Bank, Sofa, Stuhl) alle `rest_every_m` Meter | 2 |
| `quiet` (Reizempfindlichkeit) | laute Räume meiden (Kantine, Halle, Produktionszone, Räume mit Maschinen) per Zuschlag, Vorwarnung bei Durchgang, wenige Wendungen. **Näherung nach Raumtyp, keine Messung.** | 2 |
| `low_vision` / `voice_first` | Sprache zuerst, Abstände in Schritten und Metern, Tastorientierung, keine Farbwörter, hoher Kontrast | 2 |
| `simple` (kognitiv) | sehr kurze Sätze, ein Schritt nach dem anderen, bestätigen ("Bist du angekommen?") | 2 |
| `reduced_motion` (Epilepsie, Photosensitivität) | Oberfläche: keine Animation, statische Route, nichts blinkt. Routing unverändert. | 2 |
Profile lassen sich kombinieren (`wheelchair` und `quiet`).

## Datenmodell
- `AccessProfile` (Datenklasse, `building_agent/access.py`): `step_free: bool`, `min_door_width_m: float | None`, `avoid_room_types: set[str]`, `avoid_machines: bool`, `prefer_lift: bool`, `rest_every_m: float | None`, `short_sentences: bool`, `voice_first: bool`, `reduced_motion: bool`, `labels: list[str]` (welche Profile aktiv sind), `notes: list[str]` (Annahmen, die genannt wurden).
- Wohnort: `GuideState.access` (nur im Gespräch, nie auf Platte oder in Logs).
- Setzen und ändern: Werkzeug `set_access_profile(profile, door_width_m=None, ...)`, mit Karte und klarem Ja wie bei anderen Änderungen? **Entscheidung:** Ohne Karte, weil es nichts am Gebäude ändert. Der Agent bestätigt in einem Satz ("Ich plane ab jetzt stufenfrei mit Türen ab 0,9 m. Sag, wenn sich das ändert."). Löschen mit `clear_access_profile`.

## Routing
- `routing.route(..., min_door_width_m=None, avoid=None)`: Öffnungen mit `width_m < min` fallen weg (Aufzüge und Treppenhaus-Türen nach der Regel von `wide_delivery_count`: Aufzüge zählen als passierbar), `avoid` bekommt einen Zuschlag (nicht gesperrt), so dass ein Weg durch laute Räume nur genutzt wird, wenn es keinen anderen gibt. Standardverhalten ohne Profil bleibt exakt wie heute (Regressionstest 300 Routen).
- Ergebnis nennt die Gründe: `profile_notes` ("Tür 0.12 zu schmal, Umweg 42 m", "kein stufenfreier Weg: Aufzug 1 gesperrt").
- Alle Werkzeuge nehmen das Profil automatisch: `find_route`, `give_directions`, `campus_route`, `find_forklift_route` nicht (Gabelstapler hat eigene Regeln), `find_asset`, `find_connector` (nennt "stufenfrei erreichbar"), `what_changes` (rechnet mit dem Profil: "für dich"), `step_free_reachable_count`-Logik für "welche Räume kann ich erreichen" (`reachable_for_me`).
- Neues Werkzeug `reachable_for_me(floor_level=None, room_type=None)`: Liste erreichbarer Räume und Anzahl, mit den Gründen für Ausgeschlossene (kurz).

## Wegbeschreibung und Antworten
- `directions.py`: Pausenpunkte (nächste Bank oder Sitzgelegenheit am Weg), kürzere Schritte, Vorwarnung vor lauten Bereichen, bei `simple` ein Schritt pro Antwort, bei `low_vision` Tastorientierung (Wand links oder rechts nach dem Abbiegewort, Abstände in Metern).
- Der Prompt: "Wenn ein Profil aktiv ist, nutze es für jede Route ohne nachzufragen. Frage nur einmal nach fehlenden Angaben (Türbreite)."
- Ausdrücklicher Satz in Antworten, wenn das Profil etwas verändert hat: "Ich habe einen Umweg über den Aufzug genommen, weil Treppen für dich nicht gehen."

## Oberfläche (Leonie, Phase 2)
Profilwähler (Chips), Anzeige "Profil aktiv: Rollstuhl, Türen ab 0,9 m", `prefers-reduced-motion` und ein eigener Schalter (keine Animation, statische Route), Kontrast, Schriftgröße, nicht erreichbare Räume ausgrauen. Der Server liefert `state.access` (Labels, ohne Details) für die Anzeige. Profil nicht in der URL oder im Speicher des Browsers ablegen.

## Akzeptanzkriterien
1. Ohne Profil ändert sich nichts (alle bestehenden Tests, 300 Routen identisch).
2. `wheelchair` mit 0,9 und 1,1 m: Auf mindestens 100 Dev-Routen (alle Quellen) enthält keine Route eine Stufe und keine Tür unter der Grenze (Prüfung in einem Test mit unabhängiger Kontrolle auf den Öffnungen), sie ist höchstens so lang wie der beste Weg mit denselben Regeln (Vergleich mit einer einfachen Referenz-Dijkstra), und eine Route ohne Möglichkeit endet in einer ehrlichen Meldung mit Grund.
3. `reachable_for_me` stimmt mit `step_free_reachable_count` und `wide_delivery_count` auf den gelabelten Fragen überein (gleiche Regeln, gleiche Zahlen).
4. Profil wird vom Agenten für alle Routen eines Gesprächs genutzt, ohne dass die Person es wiederholt (Live-Skript: "Ich sitze im Rollstuhl" gefolgt von zwei Routenfragen, dritte Frage nach einem Raum, der nur über eine Treppe erreichbar ist: ehrliche Antwort), auch nach einem Themenwechsel und nach Sperrung eines Aufzugs.
5. Der Agent erfindet keine Garantien: Keine Aussagen wie "reizarm" oder "sicher bei Epilepsie", nur "ruhigere Route nach Raumtyp, keine Messung" (Test auf Formulierung im Prompt und in Live-Antworten).
6. Gesundheitsangaben werden nicht auf Platte geschrieben und nicht geloggt (Test: nach einem Gespräch enthalten `building_edited.json`, Cache und Logs keine Profilfelder).
7. `scripts/check.sh` bleibt ohne Key grün, Sweep über alle 280 Gebäude für `reachable_for_me` und Profil-Routing ohne Absturz.

## Schritte
| Schritt | Inhalt | Besitzer | Stunden |
|---|---|---|---|
| 1 Kern | `access.py`, `set_access_profile`, `routing.route(min_door_width_m)`, `reachable_for_me`, Prompt, Tests inklusive Referenz-Dijkstra und Sweep | Jennifer (Agent) | 3 |
| 2 Wegbeschreibung und Antworten | Pausenpunkte, Vorwarnungen, `simple` und `low_vision`, Live-Skripte inklusive Gegner | Jennifer (Agent) | 2 |
| 3 Oberfläche | Profilwähler, reduzierte Bewegung, Kontrast, ausgegraute Räume | Leonie | 3 |
Phase 1 (Rollstuhl mit Türbreite, Profil merken, `reachable_for_me`) allein ist in etwa 3 Stunden lieferbar und deckt den Rubrik-Satz ab.

## Offene Fragen und Risiken
- Synera könnte "wide doors" anders rechnen (Türbreite des Rollstuhls plus Rand). Wir nennen die Annahme (0,9 m ohne Angabe) und fragen bei Gelegenheit.
- Türbreiten in den Daten sind teils Modellwerte (Procedural: 0,9 bis 1,6 m), Aufzugtüren 1,1 m. Wir sagen, wenn Aufzugsbreiten fehlen.
- "Leise" ist nur ein Näherungswert aus Raumtyp und Maschinen.
- Überschneidung mit den anderen Extras: höchstens zwei Level-5-Ideen bauen (Accessibility und 3D mit Agentensteuerung sind meine Empfehlung).
