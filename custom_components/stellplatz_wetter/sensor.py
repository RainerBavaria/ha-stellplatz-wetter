"""Sensoren: Ort, optional Solarprognose, Regen, Sonne, amtliche Warnungen."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .const import CONF_ENABLE_RAIN, CONF_ENABLE_SOLAR, CONF_ENABLE_SUN, CONF_ENABLE_WARNINGS
from .entity import StellplatzEntity
from .warnings import LEVEL_TEXT


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    entities: list[SensorEntity] = [PlaceSensor(c, "place")]
    if c.features[CONF_ENABLE_SOLAR]:
        entities += [SolarSensor(c, "solar_today", 0), SolarSensor(c, "solar_tomorrow", 1), SolarSensor(c, "solar_remaining_today", 0, True)]
    if c.features[CONF_ENABLE_RAIN]:
        entities.append(RainInSensor(c, "rain_in"))
    if c.features[CONF_ENABLE_SUN]:
        entities += [SunSensor(c, "sunrise"), SunSensor(c, "sunset")]
    if c.features[CONF_ENABLE_WARNINGS]:
        entities.append(OfficialWarningsSensor(c, "official_warnings"))
    async_add_entities(entities)


class PlaceSensor(StellplatzEntity, SensorEntity):
    _attr_icon = "mdi:map-marker"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        loc = self.coordinator.data.location
        return loc.name or f"{loc.latitude:.3f}, {loc.longitude:.3f}"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        data = self.coordinator.data
        return {
            "latitude": round(data.location.latitude, 5),
            "longitude": round(data.location.longitude, 5),
            "quelle": data.location.source,
            "land": data.location.country_code,
            "daten_veraltet": data.stale,
            "abgerufen": data.weather.fetched_at.isoformat(),
        }


class SolarSensor(StellplatzEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:solar-power-variant"

    def __init__(self, coordinator, key: str, day: int, from_now: bool = False) -> None:
        super().__init__(coordinator, key)
        self._day, self._from_now = day, from_now

    @property
    def native_value(self) -> float | None:
        return self.coordinator.solar_kwh(self._day, self._from_now)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        return {"modulleistung_wp": c.pv_power, "neigung": c.pv_tilt, "ausrichtung": c.pv_azimuth, "wirkungsgrad_prozent": c.pv_efficiency}


class RainInSensor(StellplatzEntity, SensorEntity):
    """Minuten bis zum nächsten Regen (unbekannt = kein Regen in den nächsten 3 Stunden)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:weather-rainy"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.rain_outlook()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        minutes, amount = self.coordinator.rain_outlook()
        return {"regen_naechste_stunde_mm": amount, "kein_regen_in_3_stunden": minutes is None}


class SunSensor(StellplatzEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_icon = "mdi:weather-sunset-up" if key == "sunrise" else "mdi:weather-sunset-down"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.sun_event(self._attr_translation_key)


class OfficialWarningsSensor(StellplatzEntity, SensorEntity):
    """Anzahl aktiver amtlicher Warnungen am Standort (DWD bzw. MeteoAlarm)."""

    _attr_icon = "mdi:alert"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if not data or data.warnings is None:
            return None
        return len(data.warnings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        warnings = (data.warnings or []) if data else []
        level = max((w.level for w in warnings), default=0)
        return {
            "hoechste_stufe": level,
            "hoechste_stufe_text": LEVEL_TEXT.get(level, ""),
            "quelle": warnings[0].source if warnings else ("DWD" if not data or (data.location.country_code or "DE") == "DE" else "MeteoAlarm"),
            "warnungen": [w.as_dict() for w in warnings],
            "fehler": data.warnings_error if data else None,
        }
