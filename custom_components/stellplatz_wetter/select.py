"""Auswahl der Standortquelle (GPS-Tracker oder manueller Ort)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .const import MODE_MANUAL, MODE_TRACKER
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([LocationModeSelect(entry.runtime_data, "location_mode"), SearchResultSelect(entry.runtime_data, "search_results")])


class LocationModeSelect(StellplatzEntity, SelectEntity):
    _attr_icon = "mdi:crosshairs-gps"

    @property
    def options(self) -> list[str]:
        return [MODE_TRACKER, MODE_MANUAL] if self.coordinator.tracker_id else [MODE_MANUAL]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.mode

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(option)


NO_RESULTS = "–"


class SearchResultSelect(StellplatzEntity, SelectEntity):
    """Die besten Treffer der letzten Ortssuche."""

    _attr_icon = "mdi:format-list-bulleted"

    @property
    def options(self) -> list[str]:
        return [item["name"] for item in self.coordinator.results] or [NO_RESULTS]

    @property
    def current_option(self) -> str | None:
        manual = self.coordinator.state.get("manual") or {}
        if self.coordinator.mode == MODE_MANUAL and manual.get("name") in self.options:
            return manual["name"]
        return None

    async def async_select_option(self, option: str) -> None:
        if option == NO_RESULTS:
            return
        await self.coordinator.async_select_result(option)

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        return {"auswahl_offen": bool(self.coordinator.results) and self.current_option is None}
