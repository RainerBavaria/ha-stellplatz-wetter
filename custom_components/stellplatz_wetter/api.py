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
    minutely: list[dict[str, Any]] = field(default_factory=list)
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
    hourly = _rows(payload.get("hourly"), HOURLY_VARS + ("global_tilted_irradiance",))
    daily = _rows(payload.get("daily"), DAILY_VARS)
    for day in daily:
        day["sunrise"] = _ts(day.get("sunrise"))
        day["sunset"] = _ts(day.get("sunset"))
    if not hourly:
        raise ApiError("Open-Meteo hat keine Vorhersage geliefert")
    minutely = _rows(payload.get("minutely_15"), ("precipitation",))
    return WeatherData(current=current, hourly=hourly, daily=daily, minutely=minutely)


async def async_fetch_forecast(
    session: ClientSession,
    latitude: float,
    longitude: float,
    *,
    solar: tuple[float, float] | None = None,
    minutely: bool = False,
) -> WeatherData:
    """Wetter abfragen. solar=(Neigung, Azimut) fordert Einstrahlung an, minutely 15-Minuten-Niederschlag."""
    hourly = HOURLY_VARS + (("global_tilted_irradiance",) if solar else ())
    params: dict[str, Any] = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(hourly),
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",  # Tagesgrenzen am Stellplatz
        "timeformat": "unixtime",  # Zeitpunkte eindeutig (UTC-Sekunden)
        "forecast_days": 7,
        "wind_speed_unit": "kmh",
    }
    if solar:
        params["tilt"] = f"{solar[0]:g}"
        params["azimuth"] = f"{solar[1]:g}"
    if minutely:
        params["minutely_15"] = "precipitation"
        params["forecast_minutely_15"] = 12  # 3 Stunden
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
    country_code: str | None = None
    match_text: str = ""


MAX_RESULTS = 3


def _unique(places: list[Place]) -> list[Place]:
    """Doppelte Treffer entfernen, gleiche Namen unterscheidbar machen."""
    result: list[Place] = []
    for place in places:
        if any(distance_km(p.latitude, p.longitude, place.latitude, place.longitude) < 1 for p in result):
            continue
        if any(p.name == place.name for p in result):
            place = Place(place.latitude, place.longitude, f"{place.name} ({place.latitude:.2f}, {place.longitude:.2f})",
                          place.country_code, place.match_text)
        result.append(place)
    return result[:MAX_RESULTS]


def parse_search(payload: dict[str, Any], limit: int | None = MAX_RESULTS) -> list[Place]:
    """Open-Meteo-Ortssuche -> Liste von Treffern."""
    places: list[Place] = []
    for item in (payload or {}).get("results") or []:
        try:
            lat, lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        parts = [item.get("name"), item.get("admin1"), item.get("country")]
        label = ", ".join(dict.fromkeys(p for p in parts if p)) or f"{lat:.3f}, {lon:.3f}"
        match = " ".join(str(item.get(k) or "") for k in ("name", "admin1", "admin2", "admin3", "admin4", "country", "country_code"))
        places.append(Place(lat, lon, label, (item.get("country_code") or "").upper() or None, match.casefold()))
    return places if limit is None else _unique(places)[:limit]


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


async def _open_meteo_search(session: ClientSession, name: str, country: str | None = None) -> list[Place]:
    params = {"name": name, "count": 20, "language": "de", "format": "json"}
    if country:
        params["countryCode"] = country.upper()
    async with session.get(GEOCODING_URL, params=params, timeout=TIMEOUT) as response:
        response.raise_for_status()
        return parse_search(await response.json(content_type=None), limit=None)


def split_query(query: str) -> tuple[str, str | None, str | None]:
    """"Neustadt, Bayern, DE" -> ("Neustadt", "Bayern", "DE")."""
    parts = [p.strip() for p in query.split(",") if p.strip()]
    country = None
    if len(parts) >= 2 and re.fullmatch(r"[A-Za-z]{2}", parts[-1]):
        country = parts.pop().upper()
    name = parts[0] if parts else query.strip()
    region = ", ".join(parts[1:]) or None
    return name, region, country


def rank_places(places: list[Place], words: list[str], home_country: str | None, country: str | None) -> list[Place]:
    """Treffer filtern (alle eingegebenen Wörter müssen vorkommen) und das eigene Land nach vorne sortieren."""
    words = [w.casefold() for w in words if w]
    matching = [p for p in places if all(w in p.match_text for w in words)]
    chosen = matching or places
    if not country and home_country:
        home = home_country.upper()
        chosen = sorted(chosen, key=lambda p: p.country_code != home)  # stabil: Reihenfolge der API bleibt erhalten
    return _unique(chosen)[:MAX_RESULTS]


async def _name_search(session: ClientSession, query: str, home_country: str | None) -> list[Place]:
    name, region, country = split_query(query)
    words = name.split()
    queries = [f"{name}, {region}" if region else name]
    if not region and len(words) >= 2:
        # "neustadt bayern" -> zusätzlich "neustadt" mit "bayern" als Region
        queries.append(f"{words[0]}, {' '.join(words[1:])}")
    found: list[Place] = []
    for text in queries:
        found += await _open_meteo_search(session, text, country)
    if not found and not region and len(words) >= 2:
        found = await _open_meteo_search(session, words[0], country)
    return rank_places(found, words + (region or "").replace(",", " ").split(), home_country, country)


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
        places = await _name_search(session, query, home_country)
        if places:
            return places
        # Fallback: Freitextsuche bei OpenStreetMap (findet auch Adressen, Campingplätze usw.)
        name, region, country = split_query(query)
        text = ", ".join(p for p in (name, region) if p)
        return await _nominatim(session, {"q": text, **({"countrycodes": country.lower()} if country else {})})
    except Exception as err:
        raise ApiError(f"Ortssuche fehlgeschlagen: {type(err).__name__}") from err


@dataclass
class ReversePlace:
    name: str | None
    country_code: str | None = None
    regions: tuple[str, ...] = ()


def parse_reverse_details(payload: dict[str, Any]) -> ReversePlace:
    address = (payload or {}).get("address") or {}
    name = None
    for key in ("city", "town", "village", "hamlet", "municipality", "suburb", "county"):
        if address.get(key):
            name = str(address[key])
            break
    if name is None and (payload or {}).get("name"):
        name = str(payload["name"])
    regions = tuple(
        str(address[k]) for k in ("city", "town", "village", "municipality", "county", "state_district", "state", "region")
        if address.get(k)
    )
    code = address.get("country_code")
    return ReversePlace(name, code.upper() if code else None, regions)


def parse_reverse(payload: dict[str, Any]) -> str | None:
    return parse_reverse_details(payload).name


async def async_reverse(session: ClientSession, latitude: float, longitude: float) -> ReversePlace | None:
    params = {"lat": f"{latitude:.5f}", "lon": f"{longitude:.5f}", "format": "jsonv2", "zoom": 14,
              "addressdetails": 1, "accept-language": "de"}
    try:
        async with session.get(REVERSE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as response:
            response.raise_for_status()
            return parse_reverse_details(await response.json(content_type=None))
    except Exception:
        return None


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))
