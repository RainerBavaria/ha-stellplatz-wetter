"""Schaltfläche: aktuellen Ort als Lieblingsplatz speichern."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .const import CONF_ENABLE_FAVORITES
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.runtime_data.features[CONF_ENABLE_FAVORITES]:
        async_add_entities([SaveFavoriteButton(entry.runtime_data, "save_favorite")])


class SaveFavoriteButton(StellplatzEntity, ButtonEntity):
    _attr_icon = "mdi:star-plus"

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_save_favorite()
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
