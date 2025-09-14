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
    CONF_API_KEY,
    CONF_COLLECTION_LEVEL,
    DEFAULT_DATA_ENDPOINT,
    DEFAULT_COLLECTION_LEVEL,
    COLLECTION_LEVELS,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    
    # Test connection to analytics backend
    endpoint = data.get(CONF_DATA_ENDPOINT, DEFAULT_DATA_ENDPOINT)
    api_key = data.get(CONF_API_KEY)
    
    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # Test with a minimal payload
        test_payload = {
            "anonymous_id": "test",
            "integration_version": "1.0.0",
            "collection_level": data[CONF_COLLECTION_LEVEL],
            "data_points": []
        }
        
        async with session.post(
            f"{endpoint}/analytics/curve_control/test",
            json=test_payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status not in [200, 404]:  # 404 is OK for test endpoint
                raise CannotConnect(f"Backend returned status {response.status}")
    
    except aiohttp.ClientError as err:
        raise CannotConnect(f"Failed to connect to analytics backend: {err}")
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
        
        # Build collection level options
        collection_options = [
            selector.SelectOptionDict(value=k, label=v)
            for k, v in COLLECTION_LEVELS.items()
        ]
        
        # Create the form schema
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_COLLECTION_LEVEL,
                    default=DEFAULT_COLLECTION_LEVEL,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=collection_options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_DATA_ENDPOINT,
                    default=DEFAULT_DATA_ENDPOINT,
                ): str,
                vol.Optional(CONF_API_KEY): str,
            }
        )
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
    
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Update the config entry
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=user_input,
                    title=info["title"],
                )
                
                # Reload the integration
                await self.hass.config_entries.async_reload(entry.entry_id)
                
                return self.async_abort(reason="reconfigure_successful")
            
            except CannotConnect:
                errors = {"base": "cannot_connect"}
            except InvalidEndpoint:
                errors = {"base": "invalid_endpoint"}
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors = {"base": "unknown"}
        else:
            user_input = entry.data
            errors = {}
        
        # Use the same schema as initial setup
        return await self.async_step_user(user_input)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidEndpoint(HomeAssistantError):
    """Error to indicate the endpoint is invalid."""