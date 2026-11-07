"""Diagnose-Download (Einstellungen → Geräte & Dienste → Stellplatz-Wetter → ⋮ → Diagnose herunterladen)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import StellplatzConfigEntry

TO_REDACT = {"latitude", "longitude", "initial_location", "manual", "last_tracker", "favorites", "results", "tracker", "name"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: StellplatzConfigEntry) -> dict[str, Any]:
    c = entry.runtime_data
    data = c.data
    summary: dict[str, Any] = {}
    if data:
        w = data.weather
        summary = {
            "abgerufen": w.fetched_at.isoformat(),
            "daten_veraltet": data.stale,
            "quelle": data.location.source,
            "land": data.location.country_code,
            "ort_bekannt": bool(data.location.name),
            "stunden": len(w.hourly),
            "tage": len(w.daily),
            "viertelstunden": len(w.minutely),
            "aktuell": {k: v for k, v in w.current.items() if k != "time"},
            "einstrahlung_vorhanden": any(r.get("global_tilted_irradiance") is not None for r in w.hourly),
            "amtliche_warnungen": None if data.warnings is None else len(data.warnings),
            "warnungen_fehler": data.warnings_error,
        }
    return {
        "version": entry.version,
        "options": async_redact_data({**entry.data, **entry.options}, TO_REDACT),
        "features": c.features,
        "zustand": async_redact_data({**c.state, "anzahl_lieblingsplaetze": len(c.favorites)}, TO_REDACT),
        "letzte_abfrage_erfolgreich": c.last_update_success,
        "daten": summary,
    }
