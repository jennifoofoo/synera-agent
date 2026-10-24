# Leonie: alles auf einer Seite (Stand 24.10.2026, abends)

Eine Liste statt sechs Specs. Reihenfolge ist die Priorität für Demo und Video. Server und Verträge sind bei Jennifer, die Seite ist deine. Neue Server-Felder sind additiv, bestehende Aufrufe ändern sich nicht.

Branches, die der Server dafür braucht (kommen nach `main`, sobald die Kit-Anpassung fertig ist): `feat/position`, `feat/voice-rules`. Lies die Specs erst, wenn du an dem Punkt bist.

## 1. Handy (mobile first), Audit mit Screenshots: `docs/mobile-audit.md`
Must fix vor einer Handy-Demo (Details und Code-Vorschläge im Audit):
1. Chat-Eingabe zoomt auf iOS (Schrift unter 16 px): `input,select,textarea{font-size:16px}` unter 820 px.
2. Audio erst nach Berührung freischalten (leeres WAV im Mikrofon- und Senden-Klick abspielen, dann dasselbe Audio-Element weiterverwenden) und Wake Lock (`navigator.wakeLock`) beim Zuhören und Begleiten.
3. Raum-Popover deckt 60 % des Plans: auf kleinen Bildschirmen als Bottom Sheet unten andocken.
4. Plan ist klein (Topbar 107 px in drei Zeilen): Marke, Gebäudewahl und "+ New building" in eine Zeile.
Dann: Touch-Ziele 44 px (`@media (pointer:coarse)`), "Voice input needs Chrome"-Text für iPhone, Ladezeit (three.js erst beim ersten 3D-Tipp laden, gzip kommt vom Server).
Handy-Demo: `scripts/tunnel.sh` startet die Seite mit https-Tunnel (Mikrofon geht nur mit https). Android und Chrome sind sicher, iPhone eingeschränkt.

## 2. Standort und Begleiten (Spec `docs/specs/position.md`)
- `state_view.position = {space_id, floor_id, point, source} | null`: blauer Punkt "You are here" in Plan und 3D, Chip "You are here: Kitchen 1.30" mit Löschen-Knopf. Kamera der 3D-Ansicht folgt über die Steuer-API.
- Knopf "I'm here" neben der Klick-Auswahl: sendet im nächsten Chat-Aufruf `context.here = {space_id, point?, floor_id?}`. Löschen: `context.here = {clear: true}`. Server prüft alles (unbekannte IDs werden verworfen).
- `state_view.guide = {active, step_index, step_count, leg: {from_space_id, to_space_id, points}, target_space_id} | null`: nur die aktuelle Etappe auf dem Plan hervorheben (Plan und 3D), Punkt am Ende der abgeschlossenen Etappe. Bei `null` (Überblick, Stop, Ankunft) nur Ziel markieren.
- Seite aktualisiert sich nach Chat-Änderungen (Position, Guide, Sperrungen, Geräte) ohne Neuladen.

## 3. Sprache (Spec `docs/specs/voice-handsfree.md`)
- Beim Spracheingang im Chat-Aufruf `voice: true` mitsenden (Top-Level-Feld neben `message`, nur echter Boolean zählt).
- Aktivierungswort "Hey Wanda" (Teil B der Spec): `continuous`-Erkennung, Ähnlichkeitsliste (wonda, wander), nur Sätze mit dem Wort am Anfang lösen aus, nur das Wort: Ton und "I'm here.", Barge-in (Ausgabe stoppen), Neustart nach Stille, Schalter "Hands-free" Default aus, sichtbares Mikrofon-Symbol und Mute. Erst bauen, wenn der Handtest zeigt, dass die normale Erkennung mit Raumnummern brauchbar ist.
- Antworten kommen mit Pausen (0,8 s) und Tempo 0,85 aus `/api/speak`, kein Seitenwechsel nötig.

## 4. Auto-Pace (Spec `docs/specs/auto-pace.md`, nach Position)
Schalter "Auto-Pace" (Default aus), Timer nach jedem gesprochenen Schritt (erwartete Gehzeit plus 5 s, kommt vom Server), danach Chat-Aufruf mit Kontext `{guide_tick: true}`. Anzeige "wartet auf dich". Der Server-Teil (`building_agent/pace.py`) liegt bereit, die Anbindung kommt nach dem Merge von Position.

## 5. Level 3 in der Seite (Gebäudewahl, Route über Gebäude)
Es gibt noch keine Campus-Endpunkte auf der Seite. Jennifer baut `/api/campus/*` (Campus laden, Gebäudeliste, Route über Gebäude). Danach: Gebäudewahl und Route über Gebäude zeichnen (W-L3d).

## 6. Kleinigkeiten
"Wanda is thinking" statt Stille bei langen Antworten, `touch-action: manipulation` auf `html`, 3D-Steuerelemente größer und mit Abstand.

## Handtest
`docs/HANDTEST.md`, Abschnitte A bis I. Schreibt jedes FAIL mit den genauen Worten auf, dann kommt es als Bug an Jennifer.
