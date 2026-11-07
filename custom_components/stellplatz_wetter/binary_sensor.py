"""Warnungen: Markise, Sturm, Frost (aus der Vorhersage der nächsten Stunden)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .const import AWNING_HOURS, CONF_ENABLE_RAIN, CONF_ENABLE_THUNDER, FROST_HOURS, RAIN_LOOKAHEAD_MIN, STORM_HOURS, THUNDER_HOURS
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        WarningSensor(coordinator, "awning_warning"),
        WarningSensor(coordinator, "storm_warning"),
        WarningSensor(coordinator, "frost_warning"),
    ]
    if coordinator.features[CONF_ENABLE_RAIN]:
        entities.append(RainSoonSensor(coordinator, "rain_soon"))
    if coordinator.features[CONF_ENABLE_THUNDER]:
        entities.append(ThunderSensor(coordinator, "thunder_warning"))
    async_add_entities(entities)


class WarningSensor(StellplatzEntity, BinarySensorEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._key = key
        self._attr_device_class = BinarySensorDeviceClass.COLD if key == "frost_warning" else BinarySensorDeviceClass.SAFETY

    def _evaluate(self) -> tuple[bool | None, float | None, float, int, str]:
        c = self.coordinator
        if self._key == "awning_warning":
            return (*c.awning(), c.awning_gust, AWNING_HOURS, "max_boeen_kmh")
        if self._key == "storm_warning":
            return (*c.storm(), c.storm_gust, STORM_HOURS, "max_boeen_kmh")
        return (*c.frost(), c.frost_temp, FROST_HOURS, "tiefstwert_c")

    @property
    def is_on(self) -> bool | None:
        return self._evaluate()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        _, value, threshold, hours, label = self._evaluate()
        return {label: value, "grenzwert": threshold, "vorausschau_stunden": hours}


class RainSoonSensor(StellplatzEntity, BinarySensorEntity):
    """An, wenn in der nächsten Stunde Regen erwartet wird."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_icon = "mdi:weather-pouring"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or not self.coordinator.data.weather.minutely:
            return None
        minutes, _ = self.coordinator.rain_outlook()
        return minutes is not None and minutes < RAIN_LOOKAHEAD_MIN

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        minutes, amount = self.coordinator.rain_outlook()
        return {"regen_in_minuten": minutes, "menge_naechste_stunde_mm": amount, "vorausschau_minuten": RAIN_LOOKAHEAD_MIN}


class ThunderSensor(StellplatzEntity, BinarySensorEntity):
    """An, wenn in den nächsten Stunden Gewitter vorhergesagt sind."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:weather-lightning"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.thunder()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"erstes_gewitter": self.coordinator.thunder()[1], "vorausschau_stunden": THUNDER_HOURS}
