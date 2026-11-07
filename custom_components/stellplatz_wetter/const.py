"""Konstanten für Stellplatz-Wetter."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "stellplatz_wetter"
PLATFORMS = [Platform.WEATHER, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.TEXT, Platform.BUTTON]

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

# ---------- Optionale Funktionen (alle standardmäßig aus) ----------
CONF_ENABLE_SOLAR = "enable_solar"
CONF_ENABLE_RAIN = "enable_rain"
CONF_ENABLE_THUNDER = "enable_thunder"
CONF_ENABLE_SUN = "enable_sun"
CONF_ENABLE_FAVORITES = "enable_favorites"
CONF_ENABLE_WARNINGS = "enable_official_warnings"
FEATURES = (CONF_ENABLE_SOLAR, CONF_ENABLE_RAIN, CONF_ENABLE_THUNDER, CONF_ENABLE_SUN, CONF_ENABLE_FAVORITES, CONF_ENABLE_WARNINGS)

CONF_PV_POWER = "pv_power_wp"
CONF_PV_TILT = "pv_tilt"
CONF_PV_AZIMUTH = "pv_azimuth"
CONF_PV_EFFICIENCY = "pv_efficiency"
CONF_REMOVE_FAVORITES = "remove_favorites"
DEFAULT_PV_POWER = 200.0
DEFAULT_PV_TILT = 0.0
DEFAULT_PV_AZIMUTH = 0.0  # 0 = Süden, -90 = Osten, 90 = Westen
DEFAULT_PV_EFFICIENCY = 75.0  # Prozent (Leitungs-, Regler-, Temperaturverluste)

RAIN_THRESHOLD_MM = 0.1  # pro 15 Minuten
RAIN_LOOKAHEAD_MIN = 60
THUNDER_HOURS = 6
THUNDER_CODES = (95, 96, 99)

# Entitäten je Funktion (für das Aufräumen beim Abschalten)
BASE_KEYS = ("weather", "place", "awning_warning", "storm_warning", "frost_warning", "location_mode", "place_search", "search_results")
FEATURE_KEYS = {
    CONF_ENABLE_SOLAR: ("solar_today", "solar_tomorrow", "solar_remaining_today"),
    CONF_ENABLE_RAIN: ("rain_soon", "rain_in"),
    CONF_ENABLE_THUNDER: ("thunder_warning",),
    CONF_ENABLE_SUN: ("sunrise", "sunset"),
    CONF_ENABLE_FAVORITES: ("favorites", "save_favorite"),
    CONF_ENABLE_WARNINGS: ("official_warnings",),
}
