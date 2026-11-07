"""Wetter-Entität mit stündlicher und täglicher Vorhersage."""
from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SUNNY,
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .coordinator import StellplatzCoordinator, current_index
from .entity import setup_common

HOURLY_LIMIT = 72

WMO_TO_CONDITION: dict[int, str] = {
    0: ATTR_CONDITION_SUNNY, 1: ATTR_CONDITION_SUNNY, 2: ATTR_CONDITION_PARTLYCLOUDY, 3: ATTR_CONDITION_CLOUDY,
    45: ATTR_CONDITION_FOG, 48: ATTR_CONDITION_FOG,
    51: ATTR_CONDITION_RAINY, 53: ATTR_CONDITION_RAINY, 55: ATTR_CONDITION_RAINY, 56: ATTR_CONDITION_RAINY, 57: ATTR_CONDITION_RAINY,
    61: ATTR_CONDITION_RAINY, 63: ATTR_CONDITION_RAINY, 65: ATTR_CONDITION_POURING, 66: ATTR_CONDITION_RAINY, 67: ATTR_CONDITION_POURING,
    71: ATTR_CONDITION_SNOWY, 73: ATTR_CONDITION_SNOWY, 75: ATTR_CONDITION_SNOWY, 77: ATTR_CONDITION_SNOWY,
    80: ATTR_CONDITION_RAINY, 81: ATTR_CONDITION_RAINY, 82: ATTR_CONDITION_POURING, 85: ATTR_CONDITION_SNOWY, 86: ATTR_CONDITION_SNOWY,
    95: ATTR_CONDITION_LIGHTNING, 96: ATTR_CONDITION_LIGHTNING, 99: ATTR_CONDITION_LIGHTNING,
}


def condition_for(code: Any, is_day: Any = 1) -> str | None:
    if code is None:
        return None
    try:
        condition = WMO_TO_CONDITION.get(int(code))
    except (TypeError, ValueError):
        return None
    if condition == ATTR_CONDITION_SUNNY and is_day is not None and not is_day:
        return ATTR_CONDITION_CLEAR_NIGHT
    return condition


def hourly_forecast(rows: list[dict[str, Any]], now=None) -> list[Forecast]:
    start = current_index(rows, now)
    return [
        Forecast(
            datetime=row["time"].isoformat(),
            condition=condition_for(row.get("weather_code"), row.get("is_day")),
            native_temperature=row.get("temperature_2m"),
            native_apparent_temperature=row.get("apparent_temperature"),
            native_dew_point=row.get("dew_point_2m"),
            humidity=row.get("relative_humidity_2m"),
            cloud_coverage=row.get("cloud_cover"),
            native_pressure=row.get("pressure_msl"),
            native_precipitation=row.get("precipitation"),
            precipitation_probability=row.get("precipitation_probability"),
            native_wind_speed=row.get("wind_speed_10m"),
            native_wind_gust_speed=row.get("wind_gusts_10m"),
            wind_bearing=row.get("wind_direction_10m"),
            uv_index=row.get("uv_index"),
            is_daytime=None if row.get("is_day") is None else bool(row.get("is_day")),
        )
        for row in rows[start:start + HOURLY_LIMIT]
    ]


def daily_forecast(rows: list[dict[str, Any]]) -> list[Forecast]:
    return [
        Forecast(
            datetime=row["time"].isoformat(),
            condition=condition_for(row.get("weather_code")),
            native_temperature=row.get("temperature_2m_max"),
            native_templow=row.get("temperature_2m_min"),
            native_precipitation=row.get("precipitation_sum"),
            precipitation_probability=row.get("precipitation_probability_max"),
            native_wind_speed=row.get("wind_speed_10m_max"),
            native_wind_gust_speed=row.get("wind_gusts_10m_max"),
            wind_bearing=row.get("wind_direction_10m_dominant"),
            uv_index=row.get("uv_index_max"),
        )
        for row in rows
    ]


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([StellplatzWeather(entry.runtime_data)])


class StellplatzWeather(SingleCoordinatorWeatherEntity[StellplatzCoordinator]):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, coordinator: StellplatzCoordinator) -> None:
        super().__init__(coordinator)
        setup_common(self, coordinator, "weather")

    @property
    def _now(self) -> dict[str, Any]:
        return self.coordinator.data.weather.current if self.coordinator.data else {}

    @property
    def condition(self) -> str | None:
        return condition_for(self._now.get("weather_code"), self._now.get("is_day"))

    @property
    def native_temperature(self):
        return self._now.get("temperature_2m")

    @property
    def native_apparent_temperature(self):
        return self._now.get("apparent_temperature")

    @property
    def humidity(self):
        return self._now.get("relative_humidity_2m")

    @property
    def native_pressure(self):
        return self._now.get("pressure_msl")

    @property
    def cloud_coverage(self):
        return self._now.get("cloud_cover")

    @property
    def native_wind_speed(self):
        return self._now.get("wind_speed_10m")

    @property
    def native_wind_gust_speed(self):
        return self._now.get("wind_gusts_10m")

    @property
    def wind_bearing(self):
        return self._now.get("wind_direction_10m")

    @property
    def native_dew_point(self):
        rows = self.coordinator.data.weather.hourly if self.coordinator.data else []
        return rows[current_index(rows)].get("dew_point_2m") if rows else None

    @property
    def uv_index(self):
        rows = self.coordinator.data.weather.hourly if self.coordinator.data else []
        return rows[current_index(rows)].get("uv_index") if rows else None

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        return hourly_forecast(self.coordinator.data.weather.hourly) if self.coordinator.data else None

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        return daily_forecast(self.coordinator.data.weather.daily) if self.coordinator.data else None
