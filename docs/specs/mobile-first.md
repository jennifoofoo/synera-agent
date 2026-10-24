# Spec: Mobile first (Handy-Version)

Status: ENTWURF. Seite und Layout gehören Leonie. Dieses Dokument sammelt, was für ein Handy anders ist als am Laptop, damit wir es vor der Demo prüfen und nichts erst am Gerät merken.

## Ziel
Die Seite ist auf einem Handy im Hochformat benutzbar: Plan, Chat, Sprache, Begleiten. Die Demo kann mit dem Handy in der Hand gedreht werden.

## Anforderungen
1. **Layout:** Hochformat. Plan oben oder umschaltbar, Chat unten. Große Touch-Ziele (mindestens 44 px), keine horizontale Scrollbar, Chips und Knöpfe erreichbar mit dem Daumen. 2D/3D-Umschalter und Etagenwahl auf kleiner Breite lesbar.
2. **Plan bedienen:** Antippen statt Klicken (Auswahl, "I'm here"), Zoomen und Verschieben mit Fingern, Doppeltipp zoomt nicht die Seite. Die Auswahl-Chips dürfen den Plan nicht verdecken.
3. **Mikrofon:** Browser verlangt auf dem Handy eine sichere Verbindung (https, localhost zählt nur auf dem Gerät selbst). Für die Demo brauchen wir daher einen Tunnel oder ein Deployment (z. B. ein temporärer https-Tunnel auf den lokalen Server). Berechtigung wird beim ersten Tippen auf den Mikrofonknopf abgefragt, nicht beim Laden.
4. **Browser-Unterschiede:** Chrome auf Android unterstützt die Web Speech API gut. iOS Safari hat nur eingeschränkte Spracherkennung (kein verlässliches `continuous`), also ist das Aktivierungswort auf iPhones nicht zuverlässig. Auf nicht unterstützten Geräten Push-to-talk plus Tippen anzeigen, den Hands-free-Schalter deaktivieren mit Hinweis.
5. **Audio:** Browser spielen Ton erst nach einer Berührung der Seite ab. Der erste Tipp (Mikrofon oder "Start") schaltet die Ausgabe frei. Danach spielt Wanda auch ohne neue Berührung. Stumm-Schalter am Handy beachten (Hinweis, wenn kein Ton).
6. **Bildschirm an:** Beim Begleiten und bei Hands-free soll der Bildschirm nicht ausgehen (Screen Wake Lock API, wo verfügbar), sonst stoppt die Erkennung.
7. **Latenz:** Spracheingabe bis Antwort unter etwa 4 Sekunden, sonst wirkt es kaputt. Antwort des Modells läuft ohnehin über den Server, das Sprech-Modul streamt nicht, also Fortschritt anzeigen ("Wanda is thinking") statt Stille.
8. **Dateien:** Plan-Upload vom Handy (Kamera oder Galerie): `accept="image/*"`, Größenlimit wie am Laptop (10 MB), Hinweis bei zu großen Fotos. Foto vom Plan ist die Level-4-Demo auf dem Handy.
9. **Datenschutz:** Dauer-Mikrofon nur mit sichtbarem Zustand. Wake-Lock und Mikrofon enden, wenn die Seite in den Hintergrund geht.

## Akzeptanzkriterien (manueller Handtest, `docs/HANDTEST.md` Abschnitt I)
1. Seite lädt auf einem Android-Handy (Chrome) über https, Layout ohne horizontales Scrollen.
2. Plan antippen setzt die Auswahl, "I'm here" setzt den Standort.
3. Mikrofonknopf fragt einmal nach Berechtigung, danach funktioniert Sprache.
4. Antwort wird gesprochen (nach dem ersten Tippen), Pausen und Tempo wie am Laptop.
5. Begleiten läuft mit ausgeschaltetem Bildschirm-Timeout (Wake Lock) mindestens 5 Minuten.
6. iPhone (falls getestet): Push-to-talk und Textchat funktionieren, Hands-free ist deaktiviert mit Hinweis.
7. Foto-Upload vom Handy startet den Level-4-Ablauf.

## Offene Fragen
- Welche Geräte nutzen wir in der Demo (Android oder iPhone)? Das entscheidet, ob Hands-free im Video zu sehen ist.
- Wie bekommen wir https für die Demo (Tunnel, Deployment)? Muss vor dem Videodreh stehen.
- Wer testet, wann (Leonie hat die Seite).
