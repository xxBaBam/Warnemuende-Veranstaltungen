# Veranstaltungen Warnemünde

Ein Kalender-Abo (ICS) mit allen Veranstaltungen in Warnemünde – Feste, Märkte, Konzerte, Sport und mehr – mit
Zeit, Ort, Kategorie, kurzer Beschreibung und Link. Aktualisiert sich täglich von selbst.

**Seite zum Abonnieren (iPhone, Android, PC):** https://xxbabam.github.io/Warnemuende-Veranstaltungen/

Abo-Adresse: `https://xxbabam.github.io/Warnemuende-Veranstaltungen/veranstaltungen.ics`

## Einmalig: GitHub Pages einschalten

Settings → Pages → „Deploy from a branch“ → Branch `main`, Ordner `/docs` → Save.

## Wie es funktioniert

- Quelle: https://www.ostsee.de/warnemuende/veranstaltungen.php. Die Seite liefert jede Veranstaltung
  maschinenlesbar (schema.org „Event“) mit fester ID, Name, Start/Ende, Ort und Status; dazu werden die Felder
  „Termin“ und „Zeit“ gelesen und die Kategorien über den Filter der Seite ermittelt.
- Alle Veranstaltungen werden in `daten/veranstaltungen.json` gesammelt. **Vergangene werden nie gelöscht.**
  Neue kommen dazu, Änderungen werden übernommen, und verschwindet eine künftige Veranstaltung von der Seite, wird sie
  als abgesagt entfernt. Von ostsee.de als abgesagt markierte Termine erscheinen mit „ABGESAGT:“.
- Längere Veranstaltungen mit festen Wochentagen (z. B. „Jeden Samstag und Sonntag“) werden als einzelne Tage
  eingetragen, sonst als zusammenhängender Zeitraum (z. B. Warnemünder Woche, Hanse Sail). Ist nur eine Startzeit
  angegeben, wird der Termin mit 2 Stunden eingetragen.
- Öffnungszeiten, Termine und Zeitangaben aus der Beschreibung werden vollständig übernommen; vom beschreibenden
  Text nur ein kurzer Anriss (die Texte gehören ostsee.de), dazu der Link.
- Einmal im Monat ändert sich `daten/letzte-pruefung.txt`, damit GitHub den Zeitplan nicht nach 60 Tagen ohne
  Aktivität abschaltet.
- Scheitert der Abruf oder hat sich die Seite geändert, bleibt der alte Kalender erhalten und der Workflow schlägt
  fehl (GitHub schickt eine E-Mail).

## Kosten

Keine: Für öffentliche Repos sind GitHub Actions (Standard-Runner) und GitHub Pages kostenlos und zählen nicht gegen
das Freikontingent.

`debug/`, `scripts/explore.py` und der Workflow „Erkundung (manuell)“ dienen nur der Fehlersuche.
