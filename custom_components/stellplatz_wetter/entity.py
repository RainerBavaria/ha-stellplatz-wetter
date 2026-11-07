"""Gemeinsame Basis aller Entitäten."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StellplatzCoordinator


ATTRIBUTION = "Wetterdaten: Open-Meteo.com · Ortsnamen: © OpenStreetMap"


def setup_common(entity, coordinator: StellplatzCoordinator, key: str) -> None:
    """Name, ID und Gerät setzen (für alle Plattformen gleich)."""
    entry = coordinator.entry
    entity._attr_has_entity_name = True
    entity._attr_attribution = ATTRIBUTION
    entity._attr_translation_key = key
    entity._attr_unique_id = f"{entry.entry_id}_{key}"
    entity._attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Stellplatz-Wetter",
        model="Open-Meteo",
        entry_type=DeviceEntryType.SERVICE,
    )


class StellplatzEntity(CoordinatorEntity[StellplatzCoordinator]):
    def __init__(self, coordinator: StellplatzCoordinator, key: str) -> None:
        super().__init__(coordinator)
        setup_common(self, coordinator, key)
