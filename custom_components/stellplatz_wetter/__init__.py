"""Stellplatz-Wetter: Wetter mit Vorhersage für den aktuellen Standort des Wohnwagens."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import StellplatzCoordinator

type StellplatzConfigEntry = ConfigEntry[StellplatzCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: StellplatzConfigEntry) -> bool:
    coordinator = StellplatzCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start_tracking()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StellplatzConfigEntry) -> bool:
    await entry.runtime_data.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: StellplatzConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
