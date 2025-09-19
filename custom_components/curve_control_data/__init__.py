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
from .config_storage import ConfigStorage

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

    # Register services
    await _async_register_services(hass, collector)

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

    # Remove services if this was the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "trigger_manual_reading")
        hass.services.async_remove(DOMAIN, "get_sensor_status")

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _async_register_services(hass: HomeAssistant, collector: SimpleDataCollector):
    """Register services for the integration."""

    async def handle_manual_reading(call):
        """Handle manual reading service call."""
        try:
            await collector.trigger_manual_reading()
            _LOGGER.info("Manual sensor reading triggered")
        except Exception as e:
            _LOGGER.error(f"Error triggering manual reading: {e}")

    async def handle_get_sensor_status(call):
        """Handle get sensor status service call."""
        try:
            status = collector.get_sensor_status()
            stats = collector.get_collection_stats()

            _LOGGER.info("Curve Control Sensor Status:")
            for sensor, state in status.items():
                _LOGGER.info(f"  {sensor}: {state}")

            _LOGGER.info("Collection Stats:")
            for stat, value in stats.items():
                _LOGGER.info(f"  {stat}: {value}")

        except Exception as e:
            _LOGGER.error(f"Error getting sensor status: {e}")

    # Register services
    hass.services.async_register(
        DOMAIN,
        "trigger_manual_reading",
        handle_manual_reading
    )

    hass.services.async_register(
        DOMAIN,
        "get_sensor_status",
        handle_get_sensor_status
    )