"""Config flow for Curve Control Data Collection integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_DATA_ENDPOINT,
    DEFAULT_DATA_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)

    # Test connection to our simplified backend
    endpoint = data.get(CONF_DATA_ENDPOINT, DEFAULT_DATA_ENDPOINT)

    try:
        headers = {"Content-Type": "application/json"}

        # Test with a simple sensor data payload
        test_payload = {
            "anonymous_id": "test-config",
            "readings": [{
                "timestamp": "2025-01-01T00:00:00Z",
                "indoor_temp": 70.0,
                "hvac_state": "OFF",
                "target_temp": 70.0
            }]
        }

        async with session.post(
            f"{endpoint}/sensor-data",
            json=test_payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status not in [200, 400, 401]:  # 401 = needs auth, 400 = test data
                raise CannotConnect(f"Backend returned status {response.status}")

    except aiohttp.ClientError as err:
        raise CannotConnect(f"Failed to connect to backend: {err}")
    except Exception as err:
        _LOGGER.exception("Unexpected exception during validation")
        raise InvalidEndpoint(f"Unexpected error: {err}")

    return {"title": "Curve Control Data Collection"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Curve Control Data Collection."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Only allow one instance
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured(updates=user_input)

                return self.async_create_entry(title=info["title"], data=user_input)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidEndpoint:
                errors["base"] = "invalid_endpoint"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Create the form schema with entity selection
        data_schema = vol.Schema(
            {
                vol.Required("temperature_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required("hvac_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["climate", "sensor", "binary_sensor"])
                ),
                vol.Required("thermostat_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Optional("humidity_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional("weather_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
                vol.Optional(
                    CONF_DATA_ENDPOINT,
                    default=DEFAULT_DATA_ENDPOINT,
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "temperature_entity": "Temperature sensor (e.g., sensor.thermostat_temperature)",
                "hvac_entity": "HVAC action sensor (e.g., climate.thermostat)",
                "thermostat_entity": "Thermostat entity (e.g., climate.thermostat)",
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidEndpoint(HomeAssistantError):
    """Error to indicate the endpoint is invalid."""