# Plan: Seite fürs Ortswissen (Leonies Teil, gebaut während sie schläft)

Gehört zu `docs/specs/place-knowledge.md` (Abschnitte "Entscheidungen", "Wissensgraph", "Vertrag für die Seite"). Server (K1) ist auf `main`: `/api/facts`, `/api/facts/photo`, `/api/facts/undo`, `/api/graph`, `state.facts`, `state.closed_until`. Wanda-Werkzeuge (K2) kommen auf `feat/knowledge-agent`.

## Ziel
Wissen an Orten sichtbar und erreichbar machen, ohne die Karte zu überladen: Sprache zuerst, Ebene "Notes & photos" standardmäßig aus, Sperrungen immer sichtbar.

## Bauen
1. **Ebene "Notes & photos"** (Schalter neben der Etagenleiste bzw. in der Legende, Laptop und Handy, Standard aus, Zustand im Browser gemerkt): Pins für alle Fakten aus `state.facts` der sichtbaren Etage. Symbole: Notiz (Sprechblase), Problem (Ausrufezeichen, Warnfarbe), Foto-Ecke wenn `photo`. Durch Leonies kollisionsfreies Etiketten-Layout (`Labels.tsx`), Rang unter POIs.
2. **Antippen eines Pins:** kleine Karte mit Text, Alter ("seit 8:10"), Autor, Foto-Vorschau (`/api/facts/photo`), bei offenen Problemen ein Knopf "Resolved" (→ Chat "fixed" mit Kontext, damit Karte und Ja über Wanda laufen) und Verlauf aufklappbar (`GET /api/facts?history=1&space_id=…`).
3. **Sperrungen mit Zeit:** am vorhandenen Sperr-Symbol und in "Avoids closed …" die Zeit aus `state.closed_until` ("until tomorrow 18:00"), immer sichtbar.
4. **Notiz hier** in der Raumkarte (`Card.tsx`): Textfeld (eine Zeile), optional Foto (Handy: Kamera über `accept="image/*" capture`), Senden → `POST /api/facts` (kind note, Problem-Schalter → issue), Absenden gilt als Bestätigung; danach erscheint der Pin; "Undo" 2 Minuten lang (`POST /api/facts/undo`).
5. **Autorname:** einmal abfragen, wenn der erste Fakt angelegt wird ("Your name for notes"), im Browser gemerkt, sonst "Technician".
6. **Sprache:** Antworten von Wanda mit Fakten-Treffern heben die Orte hervor (wie `located`); "show me the photo" öffnet die Foto-Vorschau, wenn die Antwort eine Foto-URL enthält.
7. **Beim Begleiten:** Fakten der Räume auf der Route als dezente Zeile im Begleit-Sheet, wenn der Schritt den Raum betritt (Wanda liest sie vor).

## Nicht anfassen
`handsFree.ts`, `voice.ts` (Sprache), Kamera (`CameraRig.tsx`, `cameraMouse.ts`, Trackpad-Fix läuft), 3D-Look-Dateien (eigener Agent), Server.

## Tests
e2e mit echtem Server ohne Key (Fakten per `POST /api/facts` anlegen): Ebene aus → keine Pins; Ebene an → Pin; Antippen zeigt Text/Autor/Foto; "Notiz hier" legt an, Undo entfernt; Sperrung mit Zeit zeigt "until"; Handy und Desktop. Bestehende e2e bleiben grün.

## Hinweis für Leonie
Deine lokalen Branches `feat/twin-notes` (Notizen im Browser) überschneiden sich hiermit: Notizen liegen jetzt auf dem Server (bleiben, für alle sichtbar, mit Zeit). Foto-Knopf, Einsatzprotokoll und Prüfrunde kannst du darauf aufsetzen.
