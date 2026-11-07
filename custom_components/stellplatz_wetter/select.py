"""Auswahl der Standortquelle (GPS-Tracker oder manueller Ort)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import StellplatzConfigEntry
from .const import CONF_ENABLE_FAVORITES, MODE_MANUAL, MODE_TRACKER
from .entity import StellplatzEntity


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    entities: list[SelectEntity] = [LocationModeSelect(c, "location_mode"), SearchResultSelect(c, "search_results")]
    if c.features[CONF_ENABLE_FAVORITES]:
        entities.append(FavoriteSelect(c, "favorites"))
    async_add_entities(entities)


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
PENDING = "Bitte Treffer wählen"


class SearchResultSelect(StellplatzEntity, SelectEntity):
    """Die besten Treffer der letzten Ortssuche."""

    @property
    def icon(self) -> str:
        return "mdi:gesture-tap" if self.coordinator.results_pending else "mdi:format-list-bulleted"

    @property
    def options(self) -> list[str]:
        names = [item["name"] for item in self.coordinator.results]
        if self.coordinator.results_pending:
            return [PENDING, *names]
        return names or [NO_RESULTS]

    @property
    def current_option(self) -> str | None:
        if self.coordinator.results_pending:
            return PENDING
        manual = self.coordinator.state.get("manual") or {}
        if self.coordinator.mode == MODE_MANUAL and manual.get("name") in self.options:
            return manual["name"]
        return NO_RESULTS if not self.coordinator.results else None

    async def async_select_option(self, option: str) -> None:
        if option in (NO_RESULTS, PENDING):
            return
        await self.coordinator.async_select_result(option)

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        return {"auswahl_offen": self.coordinator.results_pending}


class FavoriteSelect(StellplatzEntity, SelectEntity):
    """Gespeicherte Lieblingsplätze – Auswahl setzt den Wetter-Standort."""

    _attr_icon = "mdi:star"

    @property
    def options(self) -> list[str]:
        return [NO_RESULTS] + [f["name"] for f in self.coordinator.favorites]

    @property
    def current_option(self) -> str | None:
        manual = self.coordinator.state.get("manual") or {}
        if self.coordinator.mode == MODE_MANUAL:
            for fav in self.coordinator.favorites:
                if fav["name"] == manual.get("name"):
                    return fav["name"]
        return NO_RESULTS

    async def async_select_option(self, option: str) -> None:
        if option == NO_RESULTS:
            return
        await self.coordinator.async_select_favorite(option)
