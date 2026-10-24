# Mobile (Worker-Ansicht): das Nötigste

Quellen: `docs/mobile-audit.md`, `docs/specs/mobile-first.md`, Leonies Design-Entscheidungen.

## Bildschirm
- Nur das Gebäude, oben schmale Kopfzeile (Zurück, Name, Suche). Keine Listen, Tabs, Panels, keine Minimap.
- Unten in Daumenreichweite: ein Feld "Ask or search…" mit großem Mikrofon.
- Route, nächster Schritt, Funde nur bei Bedarf, als Bottom Sheet (nie über dem Plan). Karten nur beim Antippen, 2 bis 3 Zeilen.
- Touch-Ziele mindestens 44 px. Eingabefelder mindestens 16 px Schrift (sonst zoomt iOS). `touch-action: manipulation`.

## Sprache und Ton (Demo-Gerät: iPhone mit Safari)
- Push-to-talk: Mikrofon antippen, sprechen. Kein Hands-free im Video.
- https nötig: `scripts/tunnel.sh`.
- Ton freischalten beim ersten Tipp (stilles WAV abspielen, Audio-Element wiederverwenden).
- Bildschirm wach halten (Wake Lock) beim Zuhören und Begleiten.
- "Wanda is thinking" statt Stille. Bei Spracheingabe `voice: true` mitsenden.

## Standort und Begleiten
- Blauer Punkt "You are here", gesetzt mit "I'm here" (`context.here`).
- Nur die aktuelle Etappe zeigen, klein "Step 2 of 5" (`state.guide`).

## Leistung
- Leichtes Rendering am Handy: kein Ambient Occlusion, keine Nacheffekte, 3D erst bei Bedarf laden, Dinge nur in der Nähe.

## Look
- Bläulich, clean, wenig Gold als Akzent, Farbe nur für Information, `prefers-reduced-motion` beachten.

## Abnahme
- Am echten iPhone über den Tunnel: lädt ohne Querscrollen, Antippen wählt aus, Sprache per Tipp, Antwort wird gesprochen, Begleiten bleibt an.
