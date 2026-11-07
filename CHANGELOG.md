# Änderungsprotokoll

Alle Änderungen an **Stellplatz-Wetter**, neueste zuerst.
Die Versionsnummer steht in `custom_components/stellplatz_wetter/manifest.json`.

## 1.3.0 – 2026-11-07

### Neu – Zusatzfunktionen
Alle einzeln unter **Konfigurieren** einschaltbar, standardmäßig aus. Beim Ausschalten werden die Entitäten wieder entfernt.

- **Solar-Ertragsprognose**: erwarteter Ertrag heute, morgen und für den Rest des Tages (kWh) aus der Einstrahlung auf die
  Module. Einstellbar: Modulleistung, Neigung, Ausrichtung, Systemwirkungsgrad.
- **Regenwarnung**: „Regen in … Minuten“ und „Regen in der nächsten Stunde“ (15-Minuten-Niederschlag).
- **Gewitterwarnung** für die nächsten 6 Stunden.
- **Sonnenauf- und -untergang** am aktuellen Standort.
- **Lieblingsplätze**: Ort per Knopf speichern, am Dashboard auswählen, in den Optionen löschen.
- **Amtliche Unwetterwarnungen**: DWD in Deutschland (gemeindegenau), MeteoAlarm im europäischen Ausland (Beta, Zuordnung über Regionsnamen).

### Neu – Sonstiges
- **Diagnose-Download** für Fehlermeldungen (Koordinaten, Ortsnamen und Lieblingsplätze werden unkenntlich gemacht).
- Ort-Sensor hat das neue Attribut `land` (Ländercode).
- Tests laufen automatisch bei jeder Änderung auf GitHub.

### Behoben
- Wurde in den Optionen nur der Punkt auf der Karte verschoben, aktualisierte sich das Wetter erst beim nächsten Intervall.

## 1.2.0 – 2026-11-07

### Verbessert
- **Bessere Trefferliste**: Orte im eigenen Land (laut Home-Assistant-Einstellungen) stehen vorne. Bisher kamen bei „Neustadt“ z. B. Orte in Polen oder Kanada zuerst.
- **Region ohne Komma**: „Neustadt Bayern“ wird jetzt als Ort + Region verstanden. Es bleiben nur Treffer, in denen alle eingegebenen Wörter vorkommen (bisher tauchte z. B. „Hof“ auf).
- Ländercode am Ende (`, DE`) wird als echter Länderfilter an die Suche übergeben – auch bei der Freitext-Suche über OpenStreetMap.
- Tippfehler führen weiterhin zu Treffern (Filter greift nur, wenn er etwas übrig lässt).

### Dokumentation
- Screenshots in der README.

## 1.1.1 – 2026-11-07

### Verbessert
- Offene Trefferauswahl ist jetzt deutlich sichtbar: **Suchtreffer** zeigt „Bitte Treffer wählen“ (mit Finger-Symbol), bis ein Ort ausgewählt ist.
- Neues Attribut `auswahl_offen` an `select.<name>_suchtreffer` – z. B. für bedingte Karten.
- Wechsel auf GPS oder eine neue eindeutige Suche verwirft eine offene Auswahl.

## 1.1.0 – 2026-11-07

### Neu
- **PLZ-Suche** über OpenStreetMap: `84130`, `84130 DE`, `6020, AT`. Ohne Länderangabe wird zuerst im Land der Home-Assistant-Einstellungen gesucht.
- **Trefferauswahl**: Liefert die Suche mehrere Orte (z. B. „Neustadt“), stehen die besten 3 unter **Suchtreffer** zur Auswahl. Der Standort ändert sich erst nach der Auswahl. Ein eindeutiger Treffer wird wie bisher sofort übernommen.
- **Freitext-Suche als Rückfallebene**: Findet die Ortssuche nichts, wird frei bei OpenStreetMap gesucht (Campingplätze, Adressen).

### Behoben
- Suche nach Postleitzahlen lieferte keinen Treffer.

## 1.0.0 – 2026-11-07

Erste Version.

- Wetter-Entität mit aktuellem Wetter und Vorhersage (stündlich 72 h, täglich 7 Tage) – funktioniert mit allen Standard-Wetterkacheln.
- Standort automatisch von einem Tracker (neue Abfrage ab 1 km Bewegung) oder manuell (Ortssuche, Punkt auf der Karte).
- Umschalter **Standortquelle** (GPS-Tracker / Manueller Ort).
- Warnungen: Markise, Sturm, Frost – Grenzwerte einstellbar.
- Sensor **Ort** mit dem Namen des aktuellen Ortes.
- Bei Netzausfall bleiben die letzten Daten bis zu 6 Stunden sichtbar.
- Einrichtung und Optionen komplett über die Oberfläche.
