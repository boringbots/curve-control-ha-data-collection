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
    CONF_USER_LABEL,
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

    # Log configuration details
    _LOGGER.info("🔧 Creating data collector with configuration:")
    _LOGGER.info(f"  Temperature entity: {entry.data.get('temperature_entity')}")
    _LOGGER.info(f"  HVAC entity: {entry.data.get('hvac_entity')}")
    _LOGGER.info(f"  Thermostat entity: {entry.data.get('thermostat_entity')}")
    _LOGGER.info(f"  Humidity entity: {entry.data.get('humidity_entity')}")
    _LOGGER.info(f"  Weather entity: {entry.data.get('weather_entity')}")

    # Create simple data collector
    try:
        collector = SimpleDataCollector(
            hass=hass,
            anonymous_id=anonymous_id,
            temperature_entity=entry.data.get('temperature_entity'),
            hvac_entity=entry.data.get('hvac_entity'),
            thermostat_entity=entry.data.get('thermostat_entity'),
            humidity_entity=entry.data.get('humidity_entity'),
            weather_entity=entry.data.get('weather_entity'),
            user_label=entry.data.get(CONF_USER_LABEL)
        )
        await collector.async_start()
        _LOGGER.info("✅ Data collector created and started successfully")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to create or start data collector: {e}")
        raise

    # Store collector
    hass.data[DOMAIN][entry.entry_id] = {
        "collector": collector,
        "config": entry.data,
    }

    # Register services
    try:
        await _async_register_services(hass, collector)
        _LOGGER.info("✅ Services registered successfully")
    except Exception as e:
        _LOGGER.error(f"❌ Failed to register services: {e}")

    _LOGGER.info("✅ Curve Control Data Collection initialized with anonymous ID: %s", anonymous_id[:8] + "...")
    _LOGGER.info("✅ Integration is ready for data collection and manual testing")

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
        hass.services.async_remove(DOMAIN, "trigger_thermal_calculation")

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _async_register_services(hass: HomeAssistant, collector: SimpleDataCollector):
    """Register services for the integration."""
    _LOGGER.info("🔧 Registering services for Curve Control Data Collection...")

    async def handle_manual_reading(call):
        """Handle manual reading service call."""
        _LOGGER.info("🔥 Manual reading service called!")
        try:
            await collector.trigger_manual_reading()
            _LOGGER.info("✅ Manual sensor reading triggered successfully")
        except Exception as e:
            _LOGGER.error(f"❌ Error triggering manual reading: {e}")

    async def handle_thermal_calculation(call):
        """Handle manual thermal calculation service call."""
        _LOGGER.info("🧮 Manual thermal calculation service called!")
        try:
            await collector.trigger_thermal_calculation()
            _LOGGER.info("✅ Manual thermal calculation completed")
        except Exception as e:
            _LOGGER.error(f"❌ Error triggering thermal calculation: {e}")

    async def handle_get_sensor_status(call):
        """Handle get sensor status service call."""
        _LOGGER.info("📊 Sensor status service called!")
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
            _LOGGER.error(f"❌ Error getting sensor status: {e}")

    # Register services only if they don't already exist
    if not hass.services.has_service(DOMAIN, "trigger_manual_reading"):
        hass.services.async_register(
            DOMAIN,
            "trigger_manual_reading",
            handle_manual_reading
        )
        _LOGGER.info("✅ Registered service: curve_control_data.trigger_manual_reading")
    else:
        _LOGGER.info("⚠️ Service trigger_manual_reading already exists")

    if not hass.services.has_service(DOMAIN, "get_sensor_status"):
        hass.services.async_register(
            DOMAIN,
            "get_sensor_status",
            handle_get_sensor_status
        )
        _LOGGER.info("✅ Registered service: curve_control_data.get_sensor_status")
    else:
        _LOGGER.info("⚠️ Service get_sensor_status already exists")

    if not hass.services.has_service(DOMAIN, "trigger_thermal_calculation"):
        hass.services.async_register(
            DOMAIN,
            "trigger_thermal_calculation",
            handle_thermal_calculation
        )
        _LOGGER.info("✅ Registered service: curve_control_data.trigger_thermal_calculation")
    else:
        _LOGGER.info("⚠️ Service trigger_thermal_calculation already exists")