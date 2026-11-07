"""Amtliche Unwetterwarnungen: DWD (Deutschland) und MeteoAlarm (übrige Länder Europas)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientSession

from .api import TIMEOUT, USER_AGENT, ApiError

DWD_URL = "https://maps.dwd.de/geoserver/dwd/ows"
METEOALARM_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-{country}"

SEVERITY_LEVEL = {"minor": 1, "moderate": 2, "severe": 3, "extreme": 4}
LEVEL_TEXT = {0: "keine", 1: "gering", 2: "markant", 3: "Unwetter", 4: "extrem"}

# Ländercode -> MeteoAlarm-Feedname
METEOALARM_FEEDS = {
    "AT": "austria", "BE": "belgium", "BA": "bosnia-herzegovina", "BG": "bulgaria", "HR": "croatia", "CY": "cyprus",
    "CZ": "czechia", "DK": "denmark", "EE": "estonia", "FI": "finland", "FR": "france", "GR": "greece",
    "HU": "hungary", "IS": "iceland", "IE": "ireland", "IL": "israel", "IT": "italy", "LV": "latvia",
    "LT": "lithuania", "LU": "luxembourg", "MT": "malta", "MD": "moldova", "ME": "montenegro", "NL": "netherlands",
    "MK": "republic-of-north-macedonia", "NO": "norway", "PL": "poland", "PT": "portugal", "RO": "romania",
    "RS": "serbia", "SK": "slovakia", "SI": "slovenia", "ES": "spain", "SE": "sweden", "CH": "switzerland",
    "UA": "ukraine", "GB": "united-kingdom",
}


@dataclass
class OfficialWarning:
    event: str
    level: int
    headline: str
    description: str
    onset: str | None
    expires: str | None
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ereignis": self.event, "stufe": self.level, "stufe_text": LEVEL_TEXT.get(self.level, ""),
            "ueberschrift": self.headline, "beschreibung": self.description,
            "beginn": self.onset, "ende": self.expires, "quelle": self.source,
        }


def _level(severity: Any) -> int:
    return SEVERITY_LEVEL.get(str(severity or "").strip().lower(), 0)


def _expired(expires: str | None, now: datetime) -> bool:
    if not expires:
        return False
    try:
        moment = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment < now


# ---------- Punkt-in-Polygon (GeoJSON, Längengrad/Breitengrad) ----------
def _in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(lon: float, lat: float, rings: list[list[list[float]]]) -> bool:
    if not rings or not _in_ring(lon, lat, rings[0]):
        return False
    return not any(_in_ring(lon, lat, hole) for hole in rings[1:])


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any] | None) -> bool:
    """True, wenn der Punkt in der Fläche liegt. Ohne Geometrie: True (nicht ausschließen)."""
    if not geometry:
        return True
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return _in_polygon(lon, lat, coords)
    if kind == "MultiPolygon":
        return any(_in_polygon(lon, lat, poly) for poly in coords)
    if kind == "GeometryCollection":
        return any(point_in_geometry(lon, lat, g) for g in geometry.get("geometries") or [])
    return True


# ---------- DWD ----------
def parse_dwd(payload: dict[str, Any], latitude: float, longitude: float, now: datetime) -> list[OfficialWarning]:
    result: list[OfficialWarning] = []
    seen: set[tuple] = set()
    for feature in (payload or {}).get("features") or []:
        props = feature.get("properties") or {}
        if not point_in_geometry(longitude, latitude, feature.get("geometry")):
            continue
        if _expired(props.get("EXPIRES"), now):
            continue
        key = (props.get("EVENT"), props.get("ONSET"), props.get("HEADLINE"))
        if key in seen:
            continue
        seen.add(key)
        result.append(OfficialWarning(
            event=str(props.get("EVENT") or "").strip().title(),
            level=_level(props.get("SEVERITY")),
            headline=str(props.get("HEADLINE") or "").strip(),
            description=str(props.get("DESCRIPTION") or "").strip(),
            onset=props.get("ONSET"),
            expires=props.get("EXPIRES"),
            source="DWD",
        ))
    return sorted(result, key=lambda w: -w.level)


async def async_fetch_dwd(session: ClientSession, latitude: float, longitude: float) -> list[OfficialWarning]:
    delta = 0.002
    params = {
        "service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": "dwd:Warnungen_Gemeinden",
        "outputFormat": "application/json", "srsName": "EPSG:4326",
        # WFS 1.0.0: Reihenfolge Längengrad, Breitengrad
        "bbox": f"{longitude - delta:.5f},{latitude - delta:.5f},{longitude + delta:.5f},{latitude + delta:.5f}",
    }
    try:
        async with session.get(DWD_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except Exception as err:
        raise ApiError(f"DWD nicht erreichbar: {type(err).__name__}") from err
    return parse_dwd(payload, latitude, longitude, datetime.now(UTC))


# ---------- MeteoAlarm ----------
def _norm(text: str) -> str:
    return " ".join(str(text).casefold().replace("-", " ").replace("/", " ").split())


def _pick_info(infos: list[dict[str, Any]]) -> dict[str, Any] | None:
    for prefix in ("de", "en"):
        for info in infos:
            if str(info.get("language") or "").lower().startswith(prefix):
                return info
    return infos[0] if infos else None


def parse_meteoalarm(payload: dict[str, Any], regions: tuple[str, ...], now: datetime) -> list[OfficialWarning]:
    """Warnungen, deren Gebietsname zu einem der Regionsnamen des Standorts passt."""
    names = [_norm(r) for r in regions if r]
    result: list[OfficialWarning] = []
    seen: set[tuple] = set()
    for item in (payload or {}).get("warnings") or []:
        alert = item.get("alert") or {}
        info = _pick_info(alert.get("info") or [])
        if not info or _expired(info.get("expires"), now):
            continue
        areas = [_norm(a.get("areaDesc") or "") for a in info.get("area") or []]
        if not any(area and any(area == n or area in n or n in area for n in names) for area in areas):
            continue
        key = (info.get("event"), info.get("onset"), tuple(areas))
        if key in seen:
            continue
        seen.add(key)
        result.append(OfficialWarning(
            event=str(info.get("event") or "").strip(),
            level=_level(info.get("severity")),
            headline=str(info.get("headline") or "").strip(),
            description=str(info.get("description") or "").strip(),
            onset=info.get("onset"),
            expires=info.get("expires"),
            source="MeteoAlarm",
        ))
    return sorted(result, key=lambda w: -w.level)


async def async_fetch_meteoalarm(session: ClientSession, country_code: str, regions: tuple[str, ...]) -> list[OfficialWarning]:
    feed = METEOALARM_FEEDS.get(country_code.upper())
    if not feed:
        return []
    try:
        async with session.get(METEOALARM_URL.format(country=feed), headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except Exception as err:
        raise ApiError(f"MeteoAlarm nicht erreichbar: {type(err).__name__}") from err
    return parse_meteoalarm(payload, regions, datetime.now(UTC))


async def async_fetch_warnings(
    session: ClientSession, latitude: float, longitude: float, country_code: str | None, regions: tuple[str, ...]
) -> list[OfficialWarning]:
    """Je nach Land DWD oder MeteoAlarm abfragen."""
    if (country_code or "DE").upper() == "DE":
        return await async_fetch_dwd(session, latitude, longitude)
    return await async_fetch_meteoalarm(session, country_code, regions)
