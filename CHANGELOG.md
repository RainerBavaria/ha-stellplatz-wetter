# Änderungsprotokoll

Alle Änderungen an **Stellplatz-Wetter**, neueste zuerst.
Die Versionsnummer steht in `custom_components/stellplatz_wetter/manifest.json`.

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
