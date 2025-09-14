"""The Curve Control Data Collection integration."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_ANONYMOUS_ID,
    COLLECTION_INTERVAL_SECONDS,
)
from .data_collector import CurveControlDataCollector

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
    
    # Create data collector
    collector = CurveControlDataCollector(hass, entry, anonymous_id)
    await collector.async_setup()
    
    # Store collector
    hass.data[DOMAIN][entry.entry_id] = {
        "collector": collector,
        "config": entry.data,
    }
    
    # Set up periodic data collection
    async def periodic_collection(now):
        """Periodic data collection."""
        await collector.async_collect_and_send()
    
    # Schedule data collection every 5 minutes
    cancel_interval = async_track_time_interval(
        hass, periodic_collection, timedelta(seconds=COLLECTION_INTERVAL_SECONDS)
    )
    hass.data[DOMAIN][entry.entry_id]["cancel_interval"] = cancel_interval
    
    _LOGGER.info("Curve Control Data Collection initialized with anonymous ID: %s", anonymous_id[:8] + "...")
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data:
        # Cancel periodic collection
        if "cancel_interval" in data:
            data["cancel_interval"]()
        
        # Clean up collector
        collector = data.get("collector")
        if collector:
            await collector.async_cleanup()
    
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)