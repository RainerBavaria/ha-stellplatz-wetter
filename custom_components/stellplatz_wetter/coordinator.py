"""Koordinator: Standort bestimmen, Wetter holen, Warnungen berechnen."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, ReversePlace, WeatherData, async_fetch_forecast, async_reverse, async_search_places, distance_km
from .warnings import OfficialWarning, async_fetch_warnings
from .const import (
    AWNING_HOURS,
    CONF_AWNING_GUST,
    CONF_FROST_TEMP,
    CONF_STORM_GUST,
    CONF_TRACKER,
    CONF_UPDATE_MINUTES,
    DEFAULT_AWNING_GUST,
    DEFAULT_FROST_TEMP,
    DEFAULT_STORM_GUST,
    DEFAULT_UPDATE_MINUTES,
    CONF_ENABLE_RAIN,
    CONF_ENABLE_SOLAR,
    CONF_ENABLE_WARNINGS,
    CONF_PV_AZIMUTH,
    CONF_PV_EFFICIENCY,
    CONF_PV_POWER,
    CONF_PV_TILT,
    DEFAULT_PV_AZIMUTH,
    DEFAULT_PV_EFFICIENCY,
    DEFAULT_PV_POWER,
    DEFAULT_PV_TILT,
    DOMAIN,
    FEATURES,
    FROST_HOURS,
    RAIN_LOOKAHEAD_MIN,
    RAIN_THRESHOLD_MM,
    THUNDER_CODES,
    THUNDER_HOURS,
    MODE_MANUAL,
    MODE_TRACKER,
    REFRESH_DISTANCE_KM,
    STALE_DATA_HOURS,
    STORM_HOURS,
)

LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1


@dataclass
class Location:
    latitude: float
    longitude: float
    source: str  # tracker | tracker_last_known | manual | home
    name: str | None = None
    country_code: str | None = None
    regions: tuple[str, ...] = ()


@dataclass
class StellplatzData:
    weather: WeatherData
    location: Location
    stale: bool = False
    warnings: list[OfficialWarning] | None = None
    warnings_error: str | None = None


def current_index(rows: list[dict[str, Any]], now: datetime | None = None) -> int:
    """Index der Stunde, in der *now* liegt."""
    now = now or datetime.now(UTC)
    index = 0
    for position, row in enumerate(rows):
        if row["time"] <= now:
            index = position
        else:
            break
    return index


def _valid(lat: Any, lon: Any) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


class StellplatzCoordinator(DataUpdateCoordinator[StellplatzData]):
    """Ein Eintrag = ein Fahrzeug/Stellplatz."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        options = {**entry.data, **entry.options}
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=int(options.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES))),
        )
        self.tracker_id: str | None = options.get(CONF_TRACKER) or None
        self.awning_gust = float(options.get(CONF_AWNING_GUST, DEFAULT_AWNING_GUST))
        self.storm_gust = float(options.get(CONF_STORM_GUST, DEFAULT_STORM_GUST))
        self.frost_temp = float(options.get(CONF_FROST_TEMP, DEFAULT_FROST_TEMP))
        self.features = {feature: bool(options.get(feature, False)) for feature in FEATURES}
        self.pv_power = float(options.get(CONF_PV_POWER, DEFAULT_PV_POWER))
        self.pv_tilt = float(options.get(CONF_PV_TILT, DEFAULT_PV_TILT))
        self.pv_azimuth = float(options.get(CONF_PV_AZIMUTH, DEFAULT_PV_AZIMUTH))
        self.pv_efficiency = float(options.get(CONF_PV_EFFICIENCY, DEFAULT_PV_EFFICIENCY))
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.state: dict[str, Any] = {}
        self._place_cache: tuple[float, float, ReversePlace] | None = None
        self.last_search: str | None = None

    # ---------- Zustand (Modus, manueller Ort) ----------
    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        initial = self.entry.data.get("initial_location") or {}
        self.state = {
            "mode": stored.get("mode") or (MODE_TRACKER if self.tracker_id else MODE_MANUAL),
            "manual": stored.get("manual") or {
                "latitude": initial.get("latitude", self.hass.config.latitude),
                "longitude": initial.get("longitude", self.hass.config.longitude),
                "name": None,
            },
            "last_tracker": stored.get("last_tracker"),
            "results": stored.get("results") or [],
            "results_pending": bool(stored.get("results_pending")),
            "favorites": stored.get("favorites") or [],
        }
        if self.state["mode"] == MODE_TRACKER and not self.tracker_id:
            self.state["mode"] = MODE_MANUAL
        self.last_search = stored.get("last_search")

    async def async_store_manual_now(self, latitude: float, longitude: float) -> None:
        """Manuellen Ort sofort speichern (vor einem Neuladen der Integration)."""
        self.state["manual"] = {"latitude": float(latitude), "longitude": float(longitude), "name": None}
        self.state["mode"] = MODE_MANUAL
        self.state["results_pending"] = False
        await self._store.async_save({**self.state, "last_search": self.last_search})

    def _save(self) -> None:
        self._store.async_delay_save(lambda: {**self.state, "last_search": self.last_search}, 2)

    async def async_flush(self) -> None:
        """Zustand sofort schreiben (beim Entladen/Neuladen)."""
        await self._store.async_save({**self.state, "last_search": self.last_search})

    @property
    def mode(self) -> str:
        return self.state.get("mode", MODE_MANUAL)

    async def async_set_mode(self, mode: str) -> None:
        self.state["results_pending"] = False
        self.state["mode"] = mode
        self._save()
        await self.async_refresh()

    async def async_set_manual(self, latitude: float, longitude: float, name: str | None = None) -> None:
        self.state["manual"] = {"latitude": float(latitude), "longitude": float(longitude), "name": name}
        self.state["mode"] = MODE_MANUAL
        self.state["results_pending"] = False
        self._save()
        await self.async_refresh()

    async def async_search(self, query: str) -> bool:
        """Ort suchen. Ein Treffer: sofort übernehmen. Mehrere: in "Suchtreffer" zur Auswahl anbieten.

        False = nichts gefunden.
        """
        places = await async_search_places(async_get_clientsession(self.hass), query, self.hass.config.country)
        if not places:
            return False
        self.last_search = query
        self.state["results"] = [{"latitude": p.latitude, "longitude": p.longitude, "name": p.name} for p in places]
        if len(places) == 1:
            await self.async_set_manual(places[0].latitude, places[0].longitude, places[0].name)
        else:
            self.state["results_pending"] = True
            self._save()
            self.async_update_listeners()  # Suchtreffer-Auswahl aktualisieren, Standort bleibt
        return True

    @property
    def results_pending(self) -> bool:
        return bool(self.state.get("results_pending")) and bool(self.results)

    @property
    def results(self) -> list[dict[str, Any]]:
        return list(self.state.get("results") or [])

    async def async_select_result(self, name: str) -> None:
        for item in self.results:
            if item["name"] == name:
                await self.async_set_manual(item["latitude"], item["longitude"], item["name"])
                return
        raise ValueError(name)

    # ---------- Tracker beobachten ----------
    @callback
    def async_start_tracking(self) -> None:
        if not self.tracker_id:
            return

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            if self.mode != MODE_TRACKER or self.data is None:
                return
            new = event.data["new_state"]
            if new is None or not _valid(new.attributes.get("latitude"), new.attributes.get("longitude")):
                return
            loc = self.data.location
            if distance_km(loc.latitude, loc.longitude, float(new.attributes["latitude"]), float(new.attributes["longitude"])) >= REFRESH_DISTANCE_KM:
                self.hass.async_create_task(self.async_request_refresh())

        self.entry.async_on_unload(async_track_state_change_event(self.hass, [self.tracker_id], _changed))

    # ---------- Standort ----------
    def _resolve_location(self) -> Location:
        if self.mode == MODE_TRACKER and self.tracker_id:
            state = self.hass.states.get(self.tracker_id)
            if state and _valid(state.attributes.get("latitude"), state.attributes.get("longitude")):
                lat, lon = float(state.attributes["latitude"]), float(state.attributes["longitude"])
                last = self.state.get("last_tracker")
                if not last or distance_km(last["latitude"], last["longitude"], lat, lon) > 0.05:
                    self.state["last_tracker"] = {"latitude": lat, "longitude": lon}
                    self._save()
                return Location(lat, lon, "tracker")
            last = self.state.get("last_tracker")
            if last and _valid(last.get("latitude"), last.get("longitude")):
                return Location(float(last["latitude"]), float(last["longitude"]), "tracker_last_known")
        elif self.mode == MODE_MANUAL:
            manual = self.state.get("manual") or {}
            if _valid(manual.get("latitude"), manual.get("longitude")):
                return Location(float(manual["latitude"]), float(manual["longitude"]), "manual", manual.get("name"))
        return Location(float(self.hass.config.latitude), float(self.hass.config.longitude), "home")

    async def _async_place_details(self, loc: Location) -> ReversePlace | None:
        """Ortsname/Land/Regionen per OpenStreetMap, zwischengespeichert (neu erst ab 1 km Abstand)."""
        cache = self._place_cache
        if cache and distance_km(cache[0], cache[1], loc.latitude, loc.longitude) < REFRESH_DISTANCE_KM:
            return cache[2]
        details = await async_reverse(async_get_clientsession(self.hass), loc.latitude, loc.longitude)
        if details and (details.name or details.country_code):
            self._place_cache = (loc.latitude, loc.longitude, details)
            return details
        return cache[2] if cache and distance_km(cache[0], cache[1], loc.latitude, loc.longitude) < 5 else None

    # ---------- Abfrage ----------
    async def _async_update_data(self) -> StellplatzData:
        loc = self._resolve_location()
        session = async_get_clientsession(self.hass)
        solar = (self.pv_tilt, self.pv_azimuth) if self.features[CONF_ENABLE_SOLAR] else None
        try:
            weather = await async_fetch_forecast(session, loc.latitude, loc.longitude, solar=solar,
                                                 minutely=self.features[CONF_ENABLE_RAIN])
        except ApiError as err:
            previous = self.data
            if previous and datetime.now(UTC) - previous.weather.fetched_at < timedelta(hours=STALE_DATA_HOURS):
                LOGGER.warning("Wetter vorübergehend nicht abrufbar, zeige letzte Daten: %s", err)
                return StellplatzData(previous.weather, previous.location, True, previous.warnings, previous.warnings_error)
            raise UpdateFailed(str(err)) from err

        if not loc.name or self.features[CONF_ENABLE_WARNINGS]:
            details = await self._async_place_details(loc)
            if details:
                loc.name = loc.name or details.name
                loc.country_code = details.country_code
                loc.regions = details.regions

        warnings: list[OfficialWarning] | None = None
        warnings_error: str | None = None
        if self.features[CONF_ENABLE_WARNINGS]:
            try:
                warnings = await async_fetch_warnings(session, loc.latitude, loc.longitude, loc.country_code, loc.regions)
            except ApiError as err:
                warnings_error = str(err)
                previous = self.data
                if previous and previous.warnings is not None and distance_km(
                    previous.location.latitude, previous.location.longitude, loc.latitude, loc.longitude
                ) < REFRESH_DISTANCE_KM:
                    warnings = previous.warnings
                LOGGER.warning("Amtliche Warnungen nicht abrufbar: %s", err)
        return StellplatzData(weather, loc, False, warnings, warnings_error)

    # ---------- Auswertungen ----------
    def upcoming(self, hours: int) -> list[dict[str, Any]]:
        if not self.data:
            return []
        rows = self.data.weather.hourly
        start = current_index(rows)
        return rows[start:start + hours]

    @staticmethod
    def _max(rows: list[dict[str, Any]], key: str) -> float | None:
        values = [r[key] for r in rows if r.get(key) is not None]
        return max(values) if values else None

    @staticmethod
    def _min(rows: list[dict[str, Any]], key: str) -> float | None:
        values = [r[key] for r in rows if r.get(key) is not None]
        return min(values) if values else None

    def awning(self) -> tuple[bool | None, float | None]:
        gust = self._max(self.upcoming(AWNING_HOURS), "wind_gusts_10m")
        return (None, None) if gust is None else (gust >= self.awning_gust, gust)

    def storm(self) -> tuple[bool | None, float | None]:
        gust = self._max(self.upcoming(STORM_HOURS), "wind_gusts_10m")
        return (None, None) if gust is None else (gust >= self.storm_gust, gust)

    def frost(self) -> tuple[bool | None, float | None]:
        low = self._min(self.upcoming(FROST_HOURS), "temperature_2m")
        return (None, None) if low is None else (low <= self.frost_temp, low)

    # ---------- Optionale Auswertungen ----------
    def _day_bounds(self, day: int) -> tuple[datetime, datetime] | None:
        """Beginn/Ende des Tages (0 = heute) in Ortszeit des Stellplatzes."""
        if not self.data:
            return None
        daily = self.data.weather.daily
        if len(daily) < day + 2:
            return None
        return daily[day]["time"], daily[day + 1]["time"]

    def solar_kwh(self, day: int, from_now: bool = False) -> float | None:
        """Erwarteter PV-Ertrag in kWh: Einstrahlung (W/m², Stundenmittel) × Wp/1000 × Wirkungsgrad."""
        bounds = self._day_bounds(day)
        if not bounds:
            return None
        start, end = bounds
        rows = self.data.weather.hourly
        values: list[float] = []
        now = datetime.now(UTC)
        for row in rows:
            # Open-Meteo: Wert gilt für die Stunde *vor* dem Zeitstempel
            hour_end = row["time"]
            if not (start < hour_end <= end) or row.get("global_tilted_irradiance") is None:
                continue
            if from_now and hour_end <= now:
                continue
            values.append(float(row["global_tilted_irradiance"]))
        if not values:
            return 0.0 if from_now else None
        kwh = sum(values) / 1000 * (self.pv_power / 1000) * (self.pv_efficiency / 100)
        return round(kwh, 2)

    def rain_outlook(self) -> tuple[int | None, float]:
        """(Minuten bis Regen oder None, Regenmenge in der nächsten Stunde)."""
        if not self.data:
            return None, 0.0
        now = datetime.now(UTC)
        first: int | None = None
        total = 0.0
        for row in self.data.weather.minutely:
            # Wert gilt für die 15 Minuten vor dem Zeitstempel
            start = row["time"] - timedelta(minutes=15)
            if row["time"] <= now:
                continue
            amount = float(row.get("precipitation") or 0)
            minutes = max(0, int((start - now).total_seconds() // 60))
            if minutes < RAIN_LOOKAHEAD_MIN:
                total += amount
            if first is None and amount >= RAIN_THRESHOLD_MM:
                first = minutes
        return first, round(total, 1)

    def thunder(self) -> tuple[bool | None, str | None]:
        rows = self.upcoming(THUNDER_HOURS)
        if not rows:
            return None, None
        for row in rows:
            if row.get("weather_code") in THUNDER_CODES:
                return True, row["time"].isoformat()
        return False, None

    def sun_event(self, key: str) -> datetime | None:
        """Nächster Sonnenauf- bzw. -untergang am Stellplatz."""
        if not self.data:
            return None
        now = datetime.now(UTC)
        for day in self.data.weather.daily:
            moment = day.get(key)
            if moment and moment > now:
                return moment
        return None

    # ---------- Lieblingsplätze ----------
    @property
    def favorites(self) -> list[dict[str, Any]]:
        return list(self.state.get("favorites") or [])

    async def async_save_favorite(self) -> str:
        if not self.data:
            raise ValueError("Noch kein Standort bekannt")
        loc = self.data.location
        name = loc.name or f"{loc.latitude:.3f}, {loc.longitude:.3f}"
        favorites = self.favorites
        for fav in favorites:
            if distance_km(fav["latitude"], fav["longitude"], loc.latitude, loc.longitude) < 0.2:
                return fav["name"]
        if any(f["name"] == name for f in favorites):
            name = f"{name} ({loc.latitude:.3f}, {loc.longitude:.3f})"
        favorites.append({"name": name, "latitude": loc.latitude, "longitude": loc.longitude})
        self.state["favorites"] = favorites
        await self.async_flush()
        self.async_update_listeners()
        return name

    async def async_select_favorite(self, name: str) -> None:
        for fav in self.favorites:
            if fav["name"] == name:
                await self.async_set_manual(fav["latitude"], fav["longitude"], fav["name"])
                return
        raise ValueError(name)

    async def async_remove_favorites(self, names: list[str]) -> None:
        self.state["favorites"] = [f for f in self.favorites if f["name"] not in names]
        await self.async_flush()
