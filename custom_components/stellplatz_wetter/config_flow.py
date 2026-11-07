"""Einrichtung und Optionen über die Oberfläche."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    EntitySelector,
    EntitySelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import distance_km
from .const import (
    CONF_AWNING_GUST,
    CONF_ENABLE_SOLAR,
    CONF_PV_AZIMUTH,
    CONF_PV_EFFICIENCY,
    CONF_PV_POWER,
    CONF_PV_TILT,
    CONF_REMOVE_FAVORITES,
    DEFAULT_PV_AZIMUTH,
    DEFAULT_PV_EFFICIENCY,
    DEFAULT_PV_POWER,
    DEFAULT_PV_TILT,
    FEATURES,
    CONF_FROST_TEMP,
    CONF_LOCATION,
    CONF_STORM_GUST,
    CONF_TRACKER,
    CONF_UPDATE_MINUTES,
    DEFAULT_AWNING_GUST,
    DEFAULT_FROST_TEMP,
    DEFAULT_NAME,
    DEFAULT_STORM_GUST,
    DEFAULT_UPDATE_MINUTES,
    DOMAIN,
)

TRACKER_SELECTOR = EntitySelector(EntitySelectorConfig(domain=["device_tracker", "person"]))
LOCATION_SELECTOR = LocationSelector(LocationSelectorConfig(radius=False))


def _number(minimum: float, maximum: float, step: float, unit: str) -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX))


class StellplatzConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            location = user_input.get(CONF_LOCATION) or {}
            data = {
                CONF_TRACKER: user_input.get(CONF_TRACKER) or None,
                "initial_location": {"latitude": location.get("latitude"), "longitude": location.get("longitude")} if location else None,
            }
            return self.async_create_entry(title=user_input[CONF_NAME], data=data)
        home = {"latitude": self.hass.config.latitude, "longitude": self.hass.config.longitude}
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Optional(CONF_TRACKER): TRACKER_SELECTOR,
            vol.Required(CONF_LOCATION, default=home): LOCATION_SELECTOR,
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StellplatzOptionsFlow()


class StellplatzOptionsFlow(OptionsFlow):
    """Schritt 1: Standort, Grenzwerte, Zusatzfunktionen. Schritt 2 (nur mit Solarprognose): Solaranlage."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        coordinator = getattr(entry, "runtime_data", None)
        current = {**entry.data, **entry.options}
        manual = (coordinator.state.get("manual") if coordinator else None) or {"latitude": self.hass.config.latitude, "longitude": self.hass.config.longitude}
        favorites = [f["name"] for f in coordinator.favorites] if coordinator else []

        if user_input is not None:
            location = user_input.pop(CONF_LOCATION, None)
            remove = user_input.pop(CONF_REMOVE_FAVORITES, None) or []
            if coordinator and location and distance_km(manual["latitude"], manual["longitude"], location["latitude"], location["longitude"]) > 0.02:
                await coordinator.async_store_manual_now(location["latitude"], location["longitude"])
                # falls sich sonst nichts ändert, lädt HA nicht neu -> selbst aktualisieren
                await coordinator.async_request_refresh()
            if coordinator and remove:
                await coordinator.async_remove_favorites(remove)
                coordinator.async_update_listeners()
            user_input[CONF_TRACKER] = user_input.get(CONF_TRACKER) or None
            # Solar-Einstellungen behalten, auch wenn Schritt 2 übersprungen wird
            for key in (CONF_PV_POWER, CONF_PV_TILT, CONF_PV_AZIMUTH, CONF_PV_EFFICIENCY):
                if key in current:
                    user_input.setdefault(key, current[key])
            self._options = user_input
            if user_input.get(CONF_ENABLE_SOLAR):
                return await self.async_step_solar()
            return self.async_create_entry(data=self._options)

        tracker_default = {"suggested_value": current.get(CONF_TRACKER)} if current.get(CONF_TRACKER) else {}
        fields: dict[Any, Any] = {
            vol.Optional(CONF_TRACKER, description=tracker_default): TRACKER_SELECTOR,
            vol.Required(CONF_LOCATION, default={"latitude": manual["latitude"], "longitude": manual["longitude"]}): LOCATION_SELECTOR,
            vol.Required(CONF_UPDATE_MINUTES, default=current.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES)): _number(10, 180, 5, "min"),
            vol.Required(CONF_AWNING_GUST, default=current.get(CONF_AWNING_GUST, DEFAULT_AWNING_GUST)): _number(10, 150, 1, "km/h"),
            vol.Required(CONF_STORM_GUST, default=current.get(CONF_STORM_GUST, DEFAULT_STORM_GUST)): _number(20, 200, 1, "km/h"),
            vol.Required(CONF_FROST_TEMP, default=current.get(CONF_FROST_TEMP, DEFAULT_FROST_TEMP)): _number(-10, 10, 0.5, "°C"),
        }
        for feature in FEATURES:
            fields[vol.Required(feature, default=bool(current.get(feature, False)))] = BooleanSelector()
        if favorites:
            fields[vol.Optional(CONF_REMOVE_FAVORITES, default=[])] = SelectSelector(
                SelectSelectorConfig(options=favorites, multiple=True, mode=SelectSelectorMode.LIST)
            )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))

    async def async_step_solar(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._options, **user_input})
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema({
            vol.Required(CONF_PV_POWER, default=current.get(CONF_PV_POWER, DEFAULT_PV_POWER)): _number(10, 5000, 10, "Wp"),
            vol.Required(CONF_PV_TILT, default=current.get(CONF_PV_TILT, DEFAULT_PV_TILT)): _number(0, 90, 1, "°"),
            vol.Required(CONF_PV_AZIMUTH, default=current.get(CONF_PV_AZIMUTH, DEFAULT_PV_AZIMUTH)): _number(-180, 180, 5, "°"),
            vol.Required(CONF_PV_EFFICIENCY, default=current.get(CONF_PV_EFFICIENCY, DEFAULT_PV_EFFICIENCY)): _number(30, 100, 1, "%"),
        })
        return self.async_show_form(step_id="solar", data_schema=schema)
