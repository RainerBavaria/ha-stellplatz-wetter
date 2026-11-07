"""Warnungen: Markise, Sturm, Frost (aus der Vorhersage der nächsten Stunden)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .const import AWNING_HOURS, FROST_HOURS, STORM_HOURS
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        WarningSensor(coordinator, "awning_warning"),
        WarningSensor(coordinator, "storm_warning"),
        WarningSensor(coordinator, "frost_warning"),
    ])


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
