"""Konstanten für Stellplatz-Wetter."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "stellplatz_wetter"
PLATFORMS = [Platform.WEATHER, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.TEXT]

CONF_TRACKER = "tracker"
CONF_LOCATION = "location"
CONF_UPDATE_MINUTES = "update_minutes"
CONF_AWNING_GUST = "awning_gust_kmh"
CONF_STORM_GUST = "storm_gust_kmh"
CONF_FROST_TEMP = "frost_temperature"

DEFAULT_NAME = "Wohnwagen"
DEFAULT_UPDATE_MINUTES = 30
DEFAULT_AWNING_GUST = 38.0
DEFAULT_STORM_GUST = 75.0
DEFAULT_FROST_TEMP = 2.0

# Vorausschau der Warnungen (Stunden ab jetzt)
AWNING_HOURS = 3
STORM_HOURS = 12
FROST_HOURS = 12

MODE_TRACKER = "tracker"
MODE_MANUAL = "manual"

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "HomeAssistant-Stellplatz-Wetter/1.0 (custom integration)"

# Ab dieser Bewegung (km) des Trackers wird neu abgefragt
REFRESH_DISTANCE_KM = 1.0
# So lange werden alte Daten bei Netzproblemen weiter angezeigt
STALE_DATA_HOURS = 6
