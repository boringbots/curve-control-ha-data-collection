"""Data collection logic for Curve Control analytics."""
from __future__ import annotations

import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import deque

import aiohttp
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DOMAIN,
    CONF_DATA_ENDPOINT,
    CONF_API_KEY,
    CONF_COLLECTION_LEVEL,
    DEFAULT_DATA_ENDPOINT,
    BATCH_SIZE,
    MAX_QUEUE_SIZE,
    CURVE_CONTROL_ENTITIES,
    EVENT_USER_INPUT,
    EVENT_TEMPERATURE_CHANGE,
    EVENT_HVAC_ACTION,
    EVENT_OPTIMIZATION_RESULT,
    EVENT_THERMAL_LEARNING,
    EVENT_WEATHER_UPDATE,
)
from .daily_aggregator import DailyDataAggregator

_LOGGER = logging.getLogger(__name__)


class CurveControlDataCollector:
    """Collects and sends Curve Control usage data for analytics."""
    
    def __init__(self, hass: HomeAssistant, entry, anonymous_id: str):
        """Initialize data collector."""
        self.hass = hass
        self.entry = entry
        self.anonymous_id = anonymous_id
        self.session = async_get_clientsession(hass)
        
        # Configuration
        self.data_endpoint = entry.data.get(CONF_DATA_ENDPOINT, DEFAULT_DATA_ENDPOINT)
        self.api_key = entry.data.get(CONF_API_KEY)
        self.collection_level = entry.data.get(CONF_COLLECTION_LEVEL, "standard")
        
        # Data queue
        self.data_queue: deque = deque(maxlen=MAX_QUEUE_SIZE)

        # Daily data aggregator
        self.daily_aggregator = DailyDataAggregator(hass, entry, anonymous_id)

        # State tracking
        self._state_listeners = []
        self._last_states: Dict[str, Any] = {}

        # HVAC cycle tracking for daily aggregator
        self._last_hvac_action = None
        self._hvac_cycle_start = None
        self._hvac_cycle_start_temp = None
        
    async def async_setup(self) -> None:
        """Set up data collection."""
        # Set up daily aggregator
        await self.daily_aggregator.async_setup()

        # Find and monitor curve control entities
        await self._setup_entity_monitoring()

        # Listen for service calls
        self._setup_service_monitoring()

        _LOGGER.info("Data collector setup complete - monitoring %d entities", len(self._state_listeners))
    
    async def async_cleanup(self) -> None:
        """Clean up data collection."""
        # Clean up daily aggregator
        await self.daily_aggregator.async_cleanup()

        # Remove state listeners
        for unsubscribe in self._state_listeners:
            unsubscribe()

        # Send any remaining data
        if self.data_queue:
            await self._send_data_batch(list(self.data_queue))
    
    async def _setup_entity_monitoring(self) -> None:
        """Set up monitoring of curve control entities."""
        all_entities = list(self.hass.states.async_entity_ids())
        
        # Find entities matching our patterns
        monitored_entities = []
        for pattern in CURVE_CONTROL_ENTITIES:
            pattern_prefix = pattern.replace("*", "")
            matching = [e for e in all_entities if e.startswith(pattern_prefix)]
            monitored_entities.extend(matching)
        
        # Also monitor any thermostat that might be controlled by curve control
        for entity_id in all_entities:
            if entity_id.startswith("climate.") and "curve_control" in entity_id:
                monitored_entities.append(entity_id)
        
        # Set up state change listeners
        if monitored_entities:
            listener = async_track_state_change_event(
                self.hass,
                monitored_entities,
                self._async_state_changed
            )
            self._state_listeners.append(listener)
            
            # Record initial states
            for entity_id in monitored_entities:
                state = self.hass.states.get(entity_id)
                if state:
                    self._last_states[entity_id] = state
        
        _LOGGER.debug("Monitoring entities: %s", monitored_entities)
    
    def _setup_service_monitoring(self) -> None:
        """Set up monitoring of service calls."""
        # Listen for curve_control service calls
        self.hass.bus.async_listen("call_service", self._async_service_called)
    
    @callback
    def _async_state_changed(self, event: Event) -> None:
        """Handle state changes."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        
        # Determine event type and collect data
        if "temperature" in entity_id or entity_id.startswith("climate."):
            self._collect_temperature_data(entity_id, new_state, old_state)
        elif "hvac" in entity_id or entity_id.startswith("climate."):
            self._collect_hvac_data(entity_id, new_state, old_state)
        elif "thermal_learning" in entity_id:
            self._collect_thermal_learning_data(entity_id, new_state, old_state)
        elif "weather" in entity_id:
            self._collect_weather_data(entity_id, new_state, old_state)
        
        # Update last state
        self._last_states[entity_id] = new_state
    
    @callback
    def _async_service_called(self, event: Event) -> None:
        """Handle service calls."""
        domain = event.data.get("domain")
        service = event.data.get("service")
        service_data = event.data.get("service_data", {})
        
        # Only interested in curve_control service calls
        if domain == "curve_control":
            self._collect_user_input_data(service, service_data)
    
    def _collect_temperature_data(self, entity_id: str, new_state, old_state) -> None:
        """Collect temperature-related data."""
        if self.collection_level in ["standard", "detailed"]:
            data_point = {
                "event_type": EVENT_TEMPERATURE_CHANGE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entity_id": entity_id,
                "anonymous_id": self.anonymous_id,
                "data": {
                    "current_temperature": new_state.attributes.get("current_temperature"),
                    "target_temperature": new_state.attributes.get("temperature"),
                    "hvac_mode": new_state.attributes.get("hvac_mode"),
                    "hvac_action": new_state.attributes.get("hvac_action"),
                }
            }
            self._queue_data_point(data_point)

        # Send to daily aggregator
        self.daily_aggregator.record_temperature_data(entity_id, new_state)
    
    def _collect_hvac_data(self, entity_id: str, new_state, old_state) -> None:
        """Collect HVAC action data."""
        if self.collection_level in ["standard", "detailed"]:
            hvac_action = new_state.attributes.get("hvac_action")
            old_hvac_action = old_state.attributes.get("hvac_action") if old_state else None

            # Only log when HVAC action changes
            if hvac_action != old_hvac_action:
                data_point = {
                    "event_type": EVENT_HVAC_ACTION,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "entity_id": entity_id,
                    "anonymous_id": self.anonymous_id,
                    "data": {
                        "hvac_action": hvac_action,
                        "previous_action": old_hvac_action,
                        "hvac_mode": new_state.attributes.get("hvac_mode"),
                        "current_temperature": new_state.attributes.get("current_temperature"),
                        "target_temperature": new_state.attributes.get("temperature"),
                    }
                }
                self._queue_data_point(data_point)

                # Track HVAC cycles for daily aggregator
                self._track_hvac_cycle(entity_id, new_state, old_state)
    
    def _collect_thermal_learning_data(self, entity_id: str, new_state, old_state) -> None:
        """Collect thermal learning data."""
        if self.collection_level == "detailed":
            data_point = {
                "event_type": EVENT_THERMAL_LEARNING,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entity_id": entity_id,
                "anonymous_id": self.anonymous_id,
                "data": {
                    "heating_rate_learned": new_state.attributes.get("heating_rate_learned"),
                    "cooling_rate_learned": new_state.attributes.get("cooling_rate_learned"),
                    "natural_rate_learned": new_state.attributes.get("natural_rate_learned"),
                    "heat_up_rate_current": new_state.attributes.get("heat_up_rate_current"),
                    "cool_down_rate_current": new_state.attributes.get("cool_down_rate_current"),
                    "heating_samples": new_state.attributes.get("heating_samples"),
                    "cooling_samples": new_state.attributes.get("cooling_samples"),
                    "natural_samples": new_state.attributes.get("natural_samples"),
                    "total_data_points": new_state.attributes.get("total_data_points"),
                    "has_sufficient_data": new_state.attributes.get("has_sufficient_data"),
                }
            }
            self._queue_data_point(data_point)
    
    def _collect_weather_data(self, entity_id: str, new_state, old_state) -> None:
        """Collect weather data."""
        if self.collection_level == "detailed":
            data_point = {
                "event_type": EVENT_WEATHER_UPDATE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entity_id": entity_id,
                "anonymous_id": self.anonymous_id,
                "data": {
                    "temperature": new_state.attributes.get("temperature"),
                    "humidity": new_state.attributes.get("humidity"),
                    "condition": new_state.state,
                    "pressure": new_state.attributes.get("pressure"),
                }
            }
            self._queue_data_point(data_point)

        # Send to daily aggregator
        self.daily_aggregator.record_weather_data(entity_id, new_state)
    
    def _collect_user_input_data(self, service: str, service_data: Dict[str, Any]) -> None:
        """Collect user input data."""
        data_point = {
            "event_type": EVENT_USER_INPUT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "anonymous_id": self.anonymous_id,
            "data": {
                "service": service,
                "parameters": service_data,
            }
        }
        self._queue_data_point(data_point)

        # Send to daily aggregator
        self.daily_aggregator.record_user_input(service, service_data)

    def _track_hvac_cycle(self, entity_id: str, new_state, old_state) -> None:
        """Track HVAC cycles for daily aggregation."""
        hvac_action = new_state.attributes.get("hvac_action")
        old_hvac_action = old_state.attributes.get("hvac_action") if old_state else None
        current_temp = new_state.attributes.get("current_temperature")

        # Handle cycle start (idle -> heating/cooling)
        if (old_hvac_action == "idle" or old_hvac_action is None) and hvac_action in ["heating", "cooling"]:
            self._last_hvac_action = hvac_action
            self._hvac_cycle_start = datetime.now(timezone.utc)
            self._hvac_cycle_start_temp = current_temp

        # Handle cycle end (heating/cooling -> idle)
        elif old_hvac_action in ["heating", "cooling"] and hvac_action == "idle":
            if (self._hvac_cycle_start and self._hvac_cycle_start_temp is not None
                and current_temp is not None):

                # Record the completed cycle
                self.daily_aggregator.record_hvac_cycle(
                    action=old_hvac_action,
                    start_time=self._hvac_cycle_start,
                    end_time=datetime.now(timezone.utc),
                    start_temp=self._hvac_cycle_start_temp,
                    end_temp=current_temp
                )

            # Reset tracking
            self._last_hvac_action = None
            self._hvac_cycle_start = None
            self._hvac_cycle_start_temp = None

    def _queue_data_point(self, data_point: Dict[str, Any]) -> None:
        """Add data point to queue."""
        self.data_queue.append(data_point)
        _LOGGER.debug("Queued data point: %s", data_point["event_type"])
    
    async def async_collect_and_send(self) -> None:
        """Collect queued data and send to backend."""
        if not self.data_queue:
            return
        
        # Get batch of data to send
        batch_size = min(BATCH_SIZE, len(self.data_queue))
        batch = []
        for _ in range(batch_size):
            if self.data_queue:
                batch.append(self.data_queue.popleft())
        
        if batch:
            await self._send_data_batch(batch)
    
    async def _send_data_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Send batch of data to analytics backend."""
        if not self.data_endpoint or not batch:
            return
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            payload = {
                "anonymous_id": self.anonymous_id,
                "integration_version": "1.0.0",
                "collection_level": self.collection_level,
                "data_points": batch,
            }
            
            async with self.session.post(
                f"{self.data_endpoint}/analytics-realtime-event",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    _LOGGER.debug("Successfully sent %d data points", len(batch))
                else:
                    _LOGGER.warning("Failed to send data: HTTP %d", response.status)
                    # Re-queue the data
                    self.data_queue.extendleft(reversed(batch))
        
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout sending data to analytics backend")
            # Re-queue the data
            self.data_queue.extendleft(reversed(batch))
        except Exception as err:
            _LOGGER.warning("Error sending data to analytics backend: %s", err)
            # Re-queue the data
            self.data_queue.extendleft(reversed(batch))