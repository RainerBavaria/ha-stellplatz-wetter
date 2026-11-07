"""Ortssuche: Ortsnamen eintippen, der Ort wird als Wetter-Standort gesetzt."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .api import ApiError
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PlaceSearch(entry.runtime_data, "place_search")])


class PlaceSearch(StellplatzEntity, TextEntity):
    _attr_icon = "mdi:map-search"
    _attr_native_min = 0
    _attr_native_max = 100

    @property
    def native_value(self) -> str | None:
        return self.coordinator.last_search or ""

    async def async_set_value(self, value: str) -> None:
        query = value.strip()
        if not query:
            return
        try:
            found = await self.coordinator.async_search(query)
        except ApiError as err:
            raise HomeAssistantError(str(err)) from err
        if not found:
            raise HomeAssistantError(f"Ort „{query}“ nicht gefunden")
        self.async_write_ha_state()
