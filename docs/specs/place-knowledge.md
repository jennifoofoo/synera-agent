# Spec: Ortswissen mit Zeit ("Wanda merkt sich, was im Gebäude gerade gilt")

Status: Entwurf, wartet auf Okay von Jennifer und Leonie. Ziel: Wow-Effekt bis Code-Freeze 13:00.
Es gibt kein "nach dem Freeze": alles hier wird bis 13:00 gebaut oder gestrichen.
Hintergrund: Leonies Servicetechniker-Story (Schichtübergabe, Wissen des Erfahrenen), Recherche Knowledge Graph (Graphiti-Zeitmodell, Brick/RealEstateCore), Jennifers Idee "Sperrungen mit Zeitraum".

## Ziel in einem Satz
Jeder Techniker kann per Sprache oder Tippen Wissen an einen Ort oder ein Gerät hängen ("Ventil an Presse 2 tropft", "Aufzug 1 bis morgen kaputt"), mit **gültig ab / gültig bis**; Wanda nutzt es beim Routen und liest es dem Nächsten genau dort vor. Nichts wird gelöscht, Fakten werden abgelöst, der Verlauf bleibt.

## Was es heute gibt und was fehlt
| Baustein | Heute | Fehlt |
|---|---|---|
| Gebäudegraph (Räume, Türen, Treppen, Aufzüge, Geräte mit IDs) | ja, `BuildingMap` | nichts |
| Sperren (Tür, Aufzug, Treppe) mit Karte und "Ja", Routing weicht aus, Sperrung sichtbar | ja | **Zeitraum** (bis wann), **Grund**, **wer**, automatisches Wiederöffnen |
| Standort ("I'm here", Tippen, Punkt) | ja | nichts |
| Freihändige Befehle lokal ("next", "repeat") | ja (`handsFree.ts`) | "merk dir …", "erledigt/repariert" |
| Notizen am Ort | nein (halbe Server-API auf gestopptem Branch, wiederverwendbar) | Speicher, API, Werkzeug, Anzeige |
| Verlauf ("was war letzte Woche kaputt?") | nein | Faktenspeicher mit Gültigkeit |

## Datenmodell: ein Fakt (Graphiti-Zeitmodell, eigener kleiner Speicher, keine Graph-DB)
```json
{
  "id": "f-…", "building": "<key>",
  "kind": "note | issue | closure",
  "anchor": {"space_id": "…", "asset_id": "… | null", "element_id": "Tür/Aufzug/Treppe-ID | null", "point": [x, y] | null, "floor_id": "…"},
  "text": "Ventil tropft",
  "valid_from": "ISO-Zeit", "valid_to": "ISO-Zeit | null",
  "status": "open | resolved | expired",
  "resolved_by": "<fact id> | null",
  "author": "Techniker A | null", "person_id": "techniker-a | null", "related": [], "source": "voice | text | tap", "utterance": "Originalsatz", "photo": "url | null",
  "created_at": "ISO-Zeit"
}
```
- `note`: Hinweis/Wissen ("hier immer erst den Hebel links"), kein Einfluss aufs Routing.
- `issue`: Problem an Gerät/Ort ("tropft"), bleibt offen bis "repariert"/"erledigt" → neuer Fakt `resolved`, alter bekommt `valid_to` und `resolved_by`.
- `closure`: gesperrtes Element mit Zeitraum ("Aufzug 1 bis morgen kaputt"): wirkt aufs Routing, solange `valid_from <= jetzt < valid_to`; danach automatisch wieder offen.
- "Jetzt gültig" = `valid_from <= jetzt` und (`valid_to` leer oder `> jetzt`) und Status nicht `resolved`. Nichts wird gelöscht (außer Tippfehler direkt nach dem Anlegen, "undo").
- Speicher: `agent_output/knowledge/<building>/facts.json` plus Fotos, atomar geschrieben, pro Gebäude. Schema-Mapping auf Brick/RealEstateCore (Raum- und Gerätetypen) als Export später, nicht für den Freeze.

## Was Wanda können soll (Sätze für Demo und Tests)
| Sagen | Was passiert |
|---|---|
| "Hey Wanda, merk dir hier: Ventil an Presse 2 tropft." | Karte "Notiz an Presse 2 (Halle A2): Ventil tropft, ab jetzt, offen" → "Ja" → Fakt `issue`, Pin auf der Karte |
| "Aufzug 1 ist bis morgen kaputt." | Karte mit Wirkung auf Wege ("3 Routen länger") und Zeitraum "bis morgen 18:00" (Zeitwort wird aufgelöst, unklar → nachfragen) → "Ja" → Sperrung mit Ablauf, Routing weicht aus, Karte zeigt "Closed until tomorrow 18:00" |
| "Ventil repariert." / "Erledigt." am Ort | löst den offenen Fakt dort ab (Karte, "Ja") |
| "Was gibt's hier?" / "Gibt es Hinweise zu Presse 2?" | liest die jetzt gültigen Fakten vor, kurz |
| "Was war diese Woche an Presse 2?" | Verlauf inkl. erledigter Fakten mit Datum |
| beim Begleiten in einen Raum mit Notiz | Wanda liest den Hinweis beim Betreten vor (einmal pro Gang) |
| "Was ist gerade gesperrt?" | aktive Sperrungen mit "bis wann" |
Regeln: Fakten nur nach Karte und klarem "Ja" (wie jede Änderung). Zeitwörter ("bis morgen", "bis 14 Uhr", "für zwei Stunden", "bis Freitag") deterministisch auflösen, Unklares nachfragen. Wanda erfindet nichts; sie nennt Alter und Autor ("seit heute 8:10, von Techniker A").

## Entscheidungen (Jennifer, 25.10. nachts)
- **So wenig Klicken wie möglich, Sprache zuerst:** "Zeig mir das Foto", "Was gibt's hier?", "Zeig alle Notizen in Halle A" öffnen das Foto bzw. heben die Stellen auf der Karte hervor (Agent liefert `facts`-Treffer wie heute `located`).
- **Ebene "Notes & photos"** (Laptop und Handy), Standard **aus**: eingeschaltet Pins für alle jetzt gültigen Notizen, Probleme, Fotos. Schalter neben der Etagenleiste bzw. in der Legende. Antippen eines Pins: Text, Alter, Autor, kleines Foto, sonst nichts.
- **Immer sichtbar, auch bei ausgeschalteter Ebene:** Sperrungen (ändern Wege, Sicherheit) mit "Closed until …"; beim Begleiten die Fakten der Räume auf der eigenen Route (und Wanda liest sie beim Betreten vor).
- **"bis morgen"** = morgen 18:00 (Schichtende), "bis Freitag" = Freitag 18:00, Zeitzone Europe/Berlin; Unklares fragt Wanda nach.
- **Autor:** Name einmal auf der Seite eingeben ("Techniker A"), im Browser gemerkt, sonst "Technician". Kein Login.
- **Erledigt melden:** jeder, der Verlauf zeigt wer.
- **Löschen:** nur "undo" direkt nach dem Anlegen; sonst nur ablösen.
- **Fotos:** optional, Handy-Kamera, verkleinert, EXIF und Ortsdaten entfernt.
- **Speicher:** pro Gebäude in einer Datei, bleibt nach Neustart erhalten.
- **Bestätigung:** Notizen und Probleme per Sprache/Chat: kurze Karte, dann "Ja". Sperrungen: Karte mit Wirkung auf die Wege wie heute. Knopf "Notiz hier" in der Seite: Absenden gilt als Bestätigung.

## Wissensgraph (mit Jennifer abgestimmt)
Mit dieser Spec ist es ein zeitlicher Wissensgraph über das Gebäude, ohne Graph-Datenbank:
- **Knoten:** Räume, Türen, Aufzüge, Treppen, Geräte (gibt es), Fakten (neu), **Personen** (neu: `person_id` aus dem Autornamen, normalisiert; Abfrage "Was hat Techniker A diese Woche gemeldet?").
- **Kanten:** Fakt `hängt an` Raum/Gerät/Element; Fakt `löst ab` älteren Fakt; Fakt `gemeldet von` Person; vorhanden: Tür `verbindet` Räume, Gerät `steht in` Raum, Raum `liegt auf` Etage. Jede Fakt-Kante gilt **von bis**.
- **Abfragen über Beziehungen** (vor dem Freeze): `facts_here` bzw. `GET /api/facts` filtern nach Status (offen/erledigt/abgelaufen), Gerätetyp oder Kategorie, Bereich/Zone/Etage/Raum, Person und Zeitraum. Beispiel: "alle offenen Probleme an Pumpen in Halle A diese Woche".
- **Export** `GET /api/graph?key=…` als **JSON-LD** mit Typen aus **Brick Schema** und **RealEstateCore** (Zuordnungstabelle unserer `room_type`/Gerätetypen, z. B. `kitchen` → `rec:Kitchen`, `fire_extinguisher` → `brick:Fire_Extinguisher`, Unbekanntes als `rec:Room` bzw. `brick:Equipment`), Fakten mit `validFrom`/`validTo`, `resolves`, `reportedBy`. Für Video und Technik-Text: "Gebäude plus Menschenwissen, mit Zeit, im Gebäude-Standard."
- **Fakt an mehreren Knoten** (`related: [ids]`): Wanda schlägt weitere betroffene Orte/Geräte vor ("betrifft auch Halle A2?"), die Karte listet alle Anker, gespeichert wird erst nach "Ja"; Pin am Hauptanker, die anderen Orte zeigen einen Verweis; "erledigt" an einem Ort löst den ganzen Fakt ab.
- **Asset Administration Shell (Export):** pro Maschine ein AAS-Teilmodell "Nameplate" (Name, Typ, Kategorie, Ort: Raum, Etage, Gebäude) plus "OpenIssues" (jetzt gültige Probleme) im Graph-Export (`GET /api/graph?key=…&format=aas` oder als Teil des JSON-LD). Nur Daten, die wir haben, nichts erfunden.
- **Kein Graphiti / keine Graph-DB:** das eigene Zeitmodell deckt "gültig von bis", Ablösen und Verlauf ab; eine Graph-Datenbank brächte nur Infrastruktur, keine Funktion.

## Aufteilung
| Teil | Wer | Dateien |
|---|---|---|
| Faktenspeicher, Zeitlogik ("jetzt gültig", Ablösen, Ablauf), Zeitwörter-Parser, Sperrung mit `valid_to` im Routing (Tick beim Abfragen, kein Hintergrundjob) | Jennifer (Agent K1) | neu `building_agent/knowledge.py`, `building_agent/time_words.py` (gibt es? sonst neu), kleine Anbindung in `guide_tools.py` (Aktion `close` bekommt `until`) |
| API: `GET /api/facts?key=&space_id=&asset_id=&at=` (jetzt gültig / Verlauf), `POST /api/facts` (nur über bestätigte Karte bzw. lokal nach Bestätigung), Foto-Upload (verkleinert, EXIF weg), `state_view.facts` (aktive Fakten pro Etage) | Jennifer (Agent K1, nutzt den halben Notizen-Branch) | neu `web/knowledge_api.py`, `web/server.py` (Routen), `web/api.py` (state_view) |
| Agent-Werkzeuge: `remember_here(text, kind, until?)` (schlägt Karte vor), `resolve_here(…)`, `facts_here(scope, when=now|history)`, Hinweis beim Begleiten in `walk.py` (Raum mit aktiven Fakten) | Jennifer (Agent K2, Prompt-Änderung → Live-Suite) | `building_agent/knowledge_tools.py`, eine Prompt-Zeile in `agent.py`, Registrierung in `tools.py` |
| Seite: Ebene "Notes & photos" (Standard aus) mit Pins für aktive Fakten (Notiz-Symbol, Problem-Symbol), Sperrung "until …" immer sichtbar, Antippen zeigt Text/Alter/Autor/Foto, Foto per Sprache öffnen, "Notiz hier"-Knopf in der Raumkarte (Text, Foto), Verlauf aufklappbar, "Closed until …" am Sperr-Symbol, freihändig "merk dir …" an den Chat geben | **Leonie** | neu `ui/Facts.tsx`, `scene/FactPins.tsx`, kleine Einhängepunkte in `Card.tsx`, `poiIcons`, `handsFree.ts` |

## Vertrag für die Seite (Leonie)
- `state.facts`: `[{id, kind, anchor: {space_id, asset_id, element_id, point, floor_id}, related, text, valid_from, valid_to, status, author, person_id, source, photo, created_at, …}]` nur jetzt gültige (alle Etagen), in jeder Antwort mit `state`. `photo` ist eine URL (`/api/facts/photo?key=…&id=…`) oder `null`.
- `GET /api/facts?key=…&space_id=…` → `{facts: [...], persons: [{person_id, name, count}]}` jetzt gültig; `&history=1` inkl. erledigt/abgelaufen, neueste zuerst. Weitere Filter: `asset_id, element_id, floor_id, area` ("Halle A"), `asset_type, category, person, since, until, at, status=open|resolved|expired|all`.
- `POST /api/facts` `{building, kind: note|issue, anchor, text, valid_to?, author?, related?, photo_base64?}` (statt `building` geht auch `key`) → `{fact, state}`; Sperrungen nur über den Chat (Karte und "Ja"), weil sie Routen ändern. Wie alle schreibenden Endpunkte nur von der eigenen Seite (Origin-Prüfung), JSON bis 12 MB.
- `GET /api/facts/photo?key=…&id=…` → JPEG (verkleinert, ohne EXIF). `POST /api/facts/undo {building}` → `{undone, state}` (nur jüngster Fakt, jünger als 2 Minuten). `GET /api/graph?key=…[&format=aas]` → JSON-LD bzw. AAS.
- Sperrung mit Zeit: `state.closed` bleibt wie heute (enthält auch Sperrungen aus Fakten, solange sie gelten); neu `state.closed_until: {element_id: ISO-Zeit}` nur für Sperrungen mit Ende. Öffnen auf der Seite (`POST /api/close` mit `closed: false`) beendet die Sperr-Fakten dieses Elements.
- Speicher: `agent_output/knowledge/<building id>/facts.json` plus `photos/`.

## Tests
- Zeitlogik: gültig/abgelaufen/abgelöst, Grenzfälle (genau `valid_to`), Ablauf öffnet Sperrung, Verlauf vollständig.
- Zeitwörter: "bis morgen", "bis 14 Uhr", "für 2 Stunden", "bis Freitag", Unklares → Rückfrage.
- Routing: Sperrung mit Ablauf wirkt nur im Zeitraum (Zeit wird im Test gesetzt).
- API: Validierung (IDs existieren, Text 1..500, Foto Typ/Größe, EXIF weg, kein Pfad-Trick), nur Gebäude des Schlüssels.
- Live: "merk dir hier …" → Karte → "Ja" → Fakt; "Aufzug 1 bis morgen kaputt" → Karte mit Zeit; "was gibt's hier?"; Sicherheitsregel bleibt (nichts ohne "Ja").
- e2e (Leonie): Pin erscheint, Antippen zeigt Notiz, "Closed until" sichtbar.
- Antworten der Testfragen bleiben byte-gleich (`SUBMISSION/answers.json` neu erzeugen und vergleichen).

## Zeitplan (Freeze 13:00)
1. Okay zur Spec (Jennifer, Leonie).
2. Server (K1) und Agent (K2) parallel, je etwa 2 Stunden; Leonie die Seite parallel gegen den Vertrag.
3. Bis etwa 10:30 mergen, Live-Suite und Browser-Tests, Antworten vergleichen.
4. Danach nur Bugfixes, Video mit der Szene "morgens Notiz, mittags repariert, nächste Schicht hört den Verlauf".

## Demo-Szene (für das Video)
Morgens: "Hey Wanda, merk dir: Ventil an Presse 2 tropft." → Pin. "Aufzug 1 ist bis morgen kaputt." → Aufzug rot, "Closed until tomorrow", Route biegt ab. Mittags: "Ventil repariert." Nächste Schicht beim Vorbeilaufen: kein Hinweis mehr zum Ventil, auf Nachfrage "Hat diese Woche einmal getropft, repariert heute 12:40."
