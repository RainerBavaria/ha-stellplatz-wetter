# Stellplatz-Wetter

Wetter **mit Vorhersage** für den aktuellen Standort von Wohnwagen oder Wohnmobil – als ganz normale
Home-Assistant-Wetter-Entität. Funktioniert mit allen Standard-Wetterkacheln (Wettervorhersage-Karte,
Clock Weather Card, Mushroom usw.). Einrichtung komplett über die Oberfläche, keine `configuration.yaml`.

- **Standort automatisch** von einem Tracker (z. B. fest verbautes iPhone mit Companion App), neue Abfrage sobald sich der Wagen > 1 km bewegt
- **Standort manuell**: Ortssuche direkt am Dashboard (Ortsname, PLZ oder Campingplatz) oder Punkt auf der Karte setzen
- **Vorhersage** stündlich (72 h) und täglich (7 Tage), Wetterdaten von [Open-Meteo](https://open-meteo.com) (kostenlos, kein API-Schlüssel)
- **Warnungen**: Markise (Böen in den nächsten 3 h), Sturm (12 h), Frost (Tiefstwert 12 h) – Grenzwerte einstellbar
- **Ortsname** als Sensor (OpenStreetMap)
- Bei Funkloch werden die letzten Daten bis zu 6 h weiter angezeigt

## Installation (HACS)

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → URL dieses Repositories, Typ **Integration**
2. **Stellplatz-Wetter** suchen → Herunterladen → Home Assistant neu starten
3. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → *Stellplatz-Wetter*
   - Name (z. B. „Wohnwagen“)
   - Standort-Tracker (optional), z. B. `device_tracker.iphone_wohnwagen`
   - Manueller Ort (Startpunkt, wenn kein Tracker gewählt ist)

Grenzwerte, Tracker, Aktualisierungsintervall und den Ort auf der Karte änderst du später unter
**Konfigurieren**.

## Entitäten (Beispiel für den Namen „Wohnwagen“)

| Entität | Inhalt |
|---|---|
| `weather.wohnwagen_wetter` | Aktuelles Wetter + Vorhersage (täglich/stündlich) |
| `sensor.wohnwagen_ort` | Ortsname, Attribute: Koordinaten, Quelle, Datenalter |
| `select.wohnwagen_standortquelle` | *GPS-Tracker* oder *Manueller Ort* |
| `text.wohnwagen_ortssuche` | Ort, PLZ oder Campingplatz eintippen und mit Enter bestätigen |
| `select.wohnwagen_suchtreffer` | Bei mehreren Treffern: die besten 3 zur Auswahl |
| `binary_sensor.wohnwagen_markisenwarnung` | Böen ≥ Grenzwert in den nächsten 3 h |
| `binary_sensor.wohnwagen_sturmwarnung` | Böen ≥ Grenzwert in den nächsten 12 h |
| `binary_sensor.wohnwagen_frostwarnung` | Tiefstwert ≤ Grenzwert in den nächsten 12 h |

## Kachel-Beispiele

**Uhr, Datum und Vorhersage** ([Clock Weather Card](https://github.com/pkissling/clock-weather-card) aus HACS):

```yaml
type: custom:clock-weather-card
entity: weather.wohnwagen_wetter
forecast_rows: 4
locale: de
time_format: 24
```

**Ohne Zusatzkarte** (eingebaut):

```yaml
type: weather-forecast
entity: weather.wohnwagen_wetter
forecast_type: daily
forecast_slots: 4
```

**Standort wählen am Display:**

```yaml
type: entities
entities:
  - entity: sensor.wohnwagen_ort
  - entity: select.wohnwagen_standortquelle
  - entity: text.wohnwagen_ortssuche
```

### Ortssuche

| Eingabe | Ergebnis |
|---|---|
| `Grado` | eindeutiger Treffer → wird sofort übernommen |
| `Neustadt` | mehrere Treffer → die besten 3 erscheinen unter **Suchtreffer**, der Standort ändert sich erst nach deiner Auswahl |
| `84130` | Postleitzahl (zuerst im Land deiner HA-Einstellungen gesucht) |
| `6020, AT` / `Grado, IT` | mit Land eingegrenzt |
| `Camping Tenda Azzurra` | Freitext über OpenStreetMap, falls der Name kein Ort ist |

Passende Karte:

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: sensor.wohnwagen_ort
    name: Wetter-Standort
    icon: mdi:map-marker
    features:
      - type: select-options
        entity: select.wohnwagen_standortquelle
  - type: entities
    entities:
      - entity: text.wohnwagen_ortssuche
        name: Ort suchen
        icon: mdi:map-search
      - entity: select.wohnwagen_suchtreffer
        name: Treffer wählen
```

## Datenquellen

Wetterdaten: [Open-Meteo.com](https://open-meteo.com) (CC BY 4.0, kostenlos für private Nutzung).
Ortsnamen: © [OpenStreetMap](https://www.openstreetmap.org/copyright)-Mitwirkende (Nominatim).
