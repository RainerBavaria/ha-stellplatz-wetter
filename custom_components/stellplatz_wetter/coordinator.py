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

from .api import ApiError, WeatherData, async_fetch_forecast, async_reverse_name, async_search_place, distance_km
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
    DOMAIN,
    FROST_HOURS,
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


@dataclass
class StellplatzData:
    weather: WeatherData
    location: Location
    stale: bool = False


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
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.state: dict[str, Any] = {}
        self._name_cache: tuple[float, float, str] | None = None
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
        }
        if self.state["mode"] == MODE_TRACKER and not self.tracker_id:
            self.state["mode"] = MODE_MANUAL
        self.last_search = stored.get("last_search")

    async def async_store_manual_now(self, latitude: float, longitude: float) -> None:
        """Manuellen Ort sofort speichern (vor einem Neuladen der Integration)."""
        self.state["manual"] = {"latitude": float(latitude), "longitude": float(longitude), "name": None}
        self.state["mode"] = MODE_MANUAL
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
        self.state["mode"] = mode
        self._save()
        await self.async_refresh()

    async def async_set_manual(self, latitude: float, longitude: float, name: str | None = None) -> None:
        self.state["manual"] = {"latitude": float(latitude), "longitude": float(longitude), "name": name}
        self.state["mode"] = MODE_MANUAL
        self._save()
        await self.async_refresh()

    async def async_search(self, query: str) -> bool:
        """Ort suchen und als manuellen Standort setzen. False = nicht gefunden."""
        place = await async_search_place(async_get_clientsession(self.hass), query)
        if place is None:
            return False
        self.last_search = query
        await self.async_set_manual(place.latitude, place.longitude, place.name)
        return True

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

    async def _async_place_name(self, loc: Location) -> str | None:
        if loc.name:
            return loc.name
        cache = self._name_cache
        if cache and distance_km(cache[0], cache[1], loc.latitude, loc.longitude) < REFRESH_DISTANCE_KM:
            return cache[2]
        name = await async_reverse_name(async_get_clientsession(self.hass), loc.latitude, loc.longitude)
        if name:
            self._name_cache = (loc.latitude, loc.longitude, name)
            return name
        return cache[2] if cache and distance_km(cache[0], cache[1], loc.latitude, loc.longitude) < 5 else None

    # ---------- Abfrage ----------
    async def _async_update_data(self) -> StellplatzData:
        loc = self._resolve_location()
        session = async_get_clientsession(self.hass)
        try:
            weather = await async_fetch_forecast(session, loc.latitude, loc.longitude)
        except ApiError as err:
            previous = self.data
            if previous and datetime.now(UTC) - previous.weather.fetched_at < timedelta(hours=STALE_DATA_HOURS):
                LOGGER.warning("Wetter vorübergehend nicht abrufbar, zeige letzte Daten: %s", err)
                return StellplatzData(previous.weather, previous.location, stale=True)
            raise UpdateFailed(str(err)) from err
        loc.name = await self._async_place_name(loc)
        return StellplatzData(weather, loc)

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
