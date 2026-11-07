"""Zugriff auf Open-Meteo (Wetter, Ortssuche) und OpenStreetMap (Ortsname)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .const import FORECAST_URL, GEOCODING_URL, REVERSE_URL, SEARCH_URL, USER_AGENT

TIMEOUT = ClientTimeout(total=20)

CURRENT_VARS = (
    "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day", "precipitation",
    "weather_code", "cloud_cover", "pressure_msl", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
)
HOURLY_VARS = (
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature", "precipitation_probability",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl", "wind_speed_10m", "wind_direction_10m",
    "wind_gusts_10m", "uv_index", "is_day",
)
DAILY_VARS = (
    "weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_probability_max",
    "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant", "uv_index_max", "sunrise", "sunset",
)


class ApiError(Exception):
    """Fehler bei einer Abfrage."""


@dataclass
class WeatherData:
    """Normalisierte Wetterdaten."""

    current: dict[str, Any]
    hourly: list[dict[str, Any]]
    daily: list[dict[str, Any]]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _rows(block: dict[str, Any] | None, names: tuple[str, ...]) -> list[dict[str, Any]]:
    block = block or {}
    times = block.get("time") or []
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(times):
        moment = _ts(raw)
        if moment is None:
            continue
        row: dict[str, Any] = {"time": moment}
        for name in names:
            values = block.get(name) or []
            row[name] = values[index] if index < len(values) else None
        rows.append(row)
    return rows


def parse_forecast(payload: dict[str, Any]) -> WeatherData:
    """Open-Meteo-Antwort (timeformat=unixtime) in WeatherData umwandeln."""
    if not isinstance(payload, dict) or "hourly" not in payload:
        raise ApiError("Unerwartete Antwort von Open-Meteo")
    current = dict(payload.get("current") or {})
    current["time"] = _ts(current.get("time"))
    hourly = _rows(payload.get("hourly"), HOURLY_VARS)
    daily = _rows(payload.get("daily"), DAILY_VARS)
    for day in daily:
        day["sunrise"] = _ts(day.get("sunrise"))
        day["sunset"] = _ts(day.get("sunset"))
    if not hourly:
        raise ApiError("Open-Meteo hat keine Vorhersage geliefert")
    return WeatherData(current=current, hourly=hourly, daily=daily)


async def async_fetch_forecast(session: ClientSession, latitude: float, longitude: float) -> WeatherData:
    params = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",  # Tagesgrenzen am Stellplatz
        "timeformat": "unixtime",  # Zeitpunkte eindeutig (UTC-Sekunden)
        "forecast_days": 7,
        "wind_speed_unit": "kmh",
    }
    try:
        async with session.get(FORECAST_URL, params=params, timeout=TIMEOUT) as response:
            payload = await response.json(content_type=None)
            if response.status != 200:
                raise ApiError(f"Open-Meteo HTTP {response.status}: {payload.get('reason') if isinstance(payload, dict) else ''}")
    except ApiError:
        raise
    except Exception as err:  # Netzwerk, Timeout, kaputtes JSON
        raise ApiError(f"Open-Meteo nicht erreichbar: {type(err).__name__}") from err
    return parse_forecast(payload)


@dataclass
class Place:
    latitude: float
    longitude: float
    name: str


MAX_RESULTS = 3


def _unique(places: list[Place]) -> list[Place]:
    """Doppelte Treffer entfernen, gleiche Namen unterscheidbar machen."""
    result: list[Place] = []
    for place in places:
        if any(distance_km(p.latitude, p.longitude, place.latitude, place.longitude) < 1 for p in result):
            continue
        if any(p.name == place.name for p in result):
            place = Place(place.latitude, place.longitude, f"{place.name} ({place.latitude:.2f}, {place.longitude:.2f})")
        result.append(place)
    return result[:MAX_RESULTS]


def parse_search(payload: dict[str, Any]) -> list[Place]:
    """Open-Meteo-Ortssuche -> Liste von Treffern."""
    places: list[Place] = []
    for item in (payload or {}).get("results") or []:
        try:
            lat, lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        parts = [item.get("name"), item.get("admin1"), item.get("country")]
        label = ", ".join(dict.fromkeys(p for p in parts if p)) or f"{lat:.3f}, {lon:.3f}"
        places.append(Place(lat, lon, label))
    return _unique(places)


POSTCODE_RE = re.compile(r"^\s*(?P<code>[0-9]{4,5})\s*(?:[, ]\s*(?P<cc>[A-Za-z]{2}))?\s*$")


def parse_nominatim_search(payload: Any, postcode: str | None = None) -> list[Place]:
    """Nominatim-Suche (format=jsonv2, addressdetails=1) -> Liste von Treffern."""
    if not isinstance(payload, list):
        return []
    places: list[Place] = []
    for item in payload:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        address = item.get("address") or {}
        town = next((address[k] for k in ("city", "town", "village", "municipality", "hamlet", "suburb") if address.get(k)), None)
        region = address.get("state")
        country = address.get("country")
        if town:
            first = f"{postcode or address.get('postcode') or ''} {town}".strip() if postcode else town
            label = ", ".join(dict.fromkeys(p for p in (first, region, country) if p))
        else:
            parts = [p.strip() for p in str(item.get("display_name") or "").split(",") if p.strip()]
            label = ", ".join(parts[:3]) or (postcode or f"{lat:.3f}, {lon:.3f}")
        places.append(Place(lat, lon, label))
    return _unique(places)


async def _nominatim(session: ClientSession, params: dict[str, Any], postcode: str | None = None) -> list[Place]:
    query = {"format": "jsonv2", "addressdetails": 1, "limit": MAX_RESULTS, "accept-language": "de", **params}
    async with session.get(SEARCH_URL, params=query, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as response:
        response.raise_for_status()
        return parse_nominatim_search(await response.json(content_type=None), postcode)


async def _open_meteo_search(session: ClientSession, query: str) -> list[Place]:
    params = {"name": query, "count": MAX_RESULTS, "language": "de", "format": "json"}
    async with session.get(GEOCODING_URL, params=params, timeout=TIMEOUT) as response:
        response.raise_for_status()
        return parse_search(await response.json(content_type=None))


async def async_search_places(session: ClientSession, query: str, home_country: str | None = None) -> list[Place]:
    """Ort suchen: Postleitzahl ("84130", "84130 DE", "84130, AT") oder Ortsname. Bis zu 3 Treffer."""
    try:
        match = POSTCODE_RE.match(query)
        if match:
            code, country = match["code"], (match["cc"] or "").lower()
            countries = [country] if country else ([home_country.lower()] if home_country else []) + [""]
            for cc in countries:
                places = await _nominatim(session, {"postalcode": code, **({"countrycodes": cc} if cc else {})}, code)
                if places:
                    return places
            return []
        places = await _open_meteo_search(session, query)
        if places:
            return places
        # Fallback: Freitextsuche bei OpenStreetMap (findet auch Adressen, Campingplätze usw.)
        return await _nominatim(session, {"q": query})
    except Exception as err:
        raise ApiError(f"Ortssuche fehlgeschlagen: {type(err).__name__}") from err


def parse_reverse(payload: dict[str, Any]) -> str | None:
    address = (payload or {}).get("address") or {}
    for key in ("city", "town", "village", "hamlet", "municipality", "suburb", "county"):
        if address.get(key):
            return str(address[key])
    name = (payload or {}).get("name")
    return str(name) if name else None


async def async_reverse_name(session: ClientSession, latitude: float, longitude: float) -> str | None:
    params = {"lat": f"{latitude:.5f}", "lon": f"{longitude:.5f}", "format": "jsonv2", "zoom": 14, "accept-language": "de"}
    try:
        async with session.get(REVERSE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as response:
            response.raise_for_status()
            return parse_reverse(await response.json(content_type=None))
    except Exception:
        return None


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))
