"""The Curve Control Data Collection integration."""
from __future__ import annotations

import logging
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_ANONYMOUS_ID,
)
from .simple_collector import SimpleDataCollector

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []  # No entities, just data collection


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Curve Control Data Collection from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Generate anonymous ID if not present
    if CONF_ANONYMOUS_ID not in entry.data:
        anonymous_id = str(uuid.uuid4())
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ANONYMOUS_ID: anonymous_id}
        )
    else:
        anonymous_id = entry.data[CONF_ANONYMOUS_ID]

    # Create simple data collector
    collector = SimpleDataCollector(
        hass=hass,
        anonymous_id=anonymous_id,
        temperature_entity=entry.data.get('temperature_entity'),
        hvac_entity=entry.data.get('hvac_entity'),
        thermostat_entity=entry.data.get('thermostat_entity'),
        humidity_entity=entry.data.get('humidity_entity'),
        weather_entity=entry.data.get('weather_entity')
    )
    await collector.async_start()

    # Store collector
    hass.data[DOMAIN][entry.entry_id] = {
        "collector": collector,
        "config": entry.data,
    }

    _LOGGER.info("Curve Control Data Collection initialized with anonymous ID: %s", anonymous_id[:8] + "...")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data:
        # Clean up collector
        collector = data.get("collector")
        if collector:
            await collector.async_stop()

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)