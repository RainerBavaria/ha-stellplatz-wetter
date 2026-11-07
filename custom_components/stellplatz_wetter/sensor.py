"""Sensor: Name des aktuellen Ortes."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PlaceSensor(entry.runtime_data, "place")])


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
            "daten_veraltet": data.stale,
            "abgerufen": data.weather.fetched_at.isoformat(),
        }
