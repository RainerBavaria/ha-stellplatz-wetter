"""Einrichtung und Optionen über die Oberfläche."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
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
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        coordinator = getattr(entry, "runtime_data", None)
        current = {**entry.data, **entry.options}
        manual = (coordinator.state.get("manual") if coordinator else None) or {"latitude": self.hass.config.latitude, "longitude": self.hass.config.longitude}

        if user_input is not None:
            location = user_input.pop(CONF_LOCATION, None)
            if coordinator and location and distance_km(manual["latitude"], manual["longitude"], location["latitude"], location["longitude"]) > 0.02:
                await coordinator.async_store_manual_now(location["latitude"], location["longitude"])
            user_input[CONF_TRACKER] = user_input.get(CONF_TRACKER) or None
            return self.async_create_entry(data=user_input)

        tracker_default = {"suggested_value": current.get(CONF_TRACKER)} if current.get(CONF_TRACKER) else {}
        schema = vol.Schema({
            vol.Optional(CONF_TRACKER, description=tracker_default): TRACKER_SELECTOR,
            vol.Required(CONF_LOCATION, default={"latitude": manual["latitude"], "longitude": manual["longitude"]}): LOCATION_SELECTOR,
            vol.Required(CONF_UPDATE_MINUTES, default=current.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES)): _number(10, 180, 5, "min"),
            vol.Required(CONF_AWNING_GUST, default=current.get(CONF_AWNING_GUST, DEFAULT_AWNING_GUST)): _number(10, 150, 1, "km/h"),
            vol.Required(CONF_STORM_GUST, default=current.get(CONF_STORM_GUST, DEFAULT_STORM_GUST)): _number(20, 200, 1, "km/h"),
            vol.Required(CONF_FROST_TEMP, default=current.get(CONF_FROST_TEMP, DEFAULT_FROST_TEMP)): _number(-10, 10, 0.5, "°C"),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
