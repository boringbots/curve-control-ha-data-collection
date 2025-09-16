"""Daily data aggregation for Curve Control analytics."""
from __future__ import annotations

import logging
import json
import asyncio
from datetime import datetime, timezone, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict, deque
import statistics

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DOMAIN,
    CONF_DATA_ENDPOINT,
    CONF_API_KEY,
    DEFAULT_DATA_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

# Data retention for daily analysis
DAILY_DATA_RETENTION_DAYS = 8  # Keep 8 days for 7-day moving average


class DailyDataAggregator:
    """Aggregates daily HVAC and environmental data for analytics."""

    def __init__(self, hass: HomeAssistant, entry, anonymous_id: str):
        """Initialize daily data aggregator."""
        self.hass = hass
        self.entry = entry
        self.anonymous_id = anonymous_id
        self.session = async_get_clientsession(hass)

        # Configuration
        self.data_endpoint = entry.data.get(CONF_DATA_ENDPOINT, DEFAULT_DATA_ENDPOINT)
        self.api_key = entry.data.get(CONF_API_KEY)

        # Daily data tracking
        self.daily_hvac_cycles = []
        self.daily_temperature_data = []
        self.daily_user_inputs = []
        self.daily_weather_data = []

        # Historical data for moving averages (last 8 days)
        self.historical_daily_data = deque(maxlen=DAILY_DATA_RETENTION_DAYS)

        # State tracking for cycle detection
        self.last_hvac_state = None
        self.current_cycle_start = None

        # Timer for midnight collection
        self._midnight_timer = None

    async def async_setup(self) -> None:
        """Set up daily data aggregation."""
        # Schedule midnight data collection
        self._midnight_timer = async_track_time_change(
            self.hass,
            self._async_midnight_collection,
            hour=0,
            minute=0,
            second=0
        )

        # Initialize today's data collection
        await self._start_daily_collection()

        _LOGGER.info("Daily data aggregator setup complete")

    async def async_cleanup(self) -> None:
        """Clean up daily data aggregation."""
        if self._midnight_timer:
            self._midnight_timer()

        # Save today's partial data
        await self._collect_and_send_daily_data()

    async def _start_daily_collection(self) -> None:
        """Start collecting data for today."""
        # Reset daily counters
        self.daily_hvac_cycles = []
        self.daily_temperature_data = []
        self.daily_user_inputs = []
        self.daily_weather_data = []

        # Get current states for baseline
        await self._collect_baseline_states()

    async def _collect_baseline_states(self) -> None:
        """Collect current states as baseline for the day."""
        # Get thermostat state
        climate_entities = [e for e in self.hass.states.async_entity_ids()
                          if e.startswith("climate.") and "curve_control" in e]

        for entity_id in climate_entities:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                # Initialize HVAC cycle tracking
                hvac_action = state.attributes.get("hvac_action")
                if hvac_action != "idle":
                    self.last_hvac_state = hvac_action
                    self.current_cycle_start = datetime.now(timezone.utc)

                # Record initial temperature data
                self._record_temperature_data(entity_id, state)

        # Get weather baseline
        weather_entities = [e for e in self.hass.states.async_entity_ids()
                          if e.startswith("weather.")]

        for entity_id in weather_entities[:1]:  # Just use first weather entity
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._record_weather_data(entity_id, state)

    @callback
    def _async_midnight_collection(self, now: datetime) -> None:
        """Handle midnight data collection."""
        self.hass.async_create_task(self._collect_and_send_daily_data())

    async def _collect_and_send_daily_data(self) -> None:
        """Collect yesterday's data and send to backend."""
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)

        # Aggregate daily data
        daily_summary = await self._aggregate_daily_data(yesterday)

        # Calculate moving averages
        moving_averages = await self._calculate_moving_averages()

        # Combine data
        daily_report = {
            "date": yesterday.isoformat(),
            "anonymous_id": self.anonymous_id,
            "daily_summary": daily_summary,
            "moving_averages": moving_averages,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Send to backend
        await self._send_daily_report(daily_report)

        # Store for moving average calculations
        self.historical_daily_data.append(daily_summary)

        # Start new day collection
        await self._start_daily_collection()

    async def _aggregate_daily_data(self, date) -> Dict[str, Any]:
        """Aggregate all data collected during the day."""
        # HVAC cycles summary
        hvac_summary = self._summarize_hvac_cycles()

        # Temperature summary
        temp_summary = self._summarize_temperature_data()

        # User input summary
        user_summary = self._summarize_user_inputs()

        # Weather summary
        weather_summary = self._summarize_weather_data()

        # Get current thermal learning rates
        thermal_rates = await self._get_current_thermal_rates()

        return {
            "date": date.isoformat(),
            "hvac_cycles": hvac_summary,
            "temperature_data": temp_summary,
            "user_inputs": user_summary,
            "weather_data": weather_summary,
            "thermal_rates": thermal_rates,
        }

    def _summarize_hvac_cycles(self) -> Dict[str, Any]:
        """Summarize HVAC ON/OFF cycles for the day."""
        if not self.daily_hvac_cycles:
            return {
                "total_cycles": 0,
                "heating_cycles": 0,
                "cooling_cycles": 0,
                "total_runtime_minutes": 0,
                "heating_runtime_minutes": 0,
                "cooling_runtime_minutes": 0,
                "average_cycle_length_minutes": 0,
            }

        heating_cycles = [c for c in self.daily_hvac_cycles if c["action"] == "heating"]
        cooling_cycles = [c for c in self.daily_hvac_cycles if c["action"] == "cooling"]

        total_runtime = sum(c["duration_minutes"] for c in self.daily_hvac_cycles)
        heating_runtime = sum(c["duration_minutes"] for c in heating_cycles)
        cooling_runtime = sum(c["duration_minutes"] for c in cooling_cycles)

        avg_cycle_length = total_runtime / len(self.daily_hvac_cycles) if self.daily_hvac_cycles else 0

        return {
            "total_cycles": len(self.daily_hvac_cycles),
            "heating_cycles": len(heating_cycles),
            "cooling_cycles": len(cooling_cycles),
            "total_runtime_minutes": total_runtime,
            "heating_runtime_minutes": heating_runtime,
            "cooling_runtime_minutes": cooling_runtime,
            "average_cycle_length_minutes": round(avg_cycle_length, 2),
        }

    def _summarize_temperature_data(self) -> Dict[str, Any]:
        """Summarize temperature and humidity data for the day."""
        if not self.daily_temperature_data:
            return {}

        # Extract temperature values
        temps = [d["current_temp"] for d in self.daily_temperature_data if d.get("current_temp")]
        targets = [d["target_temp"] for d in self.daily_temperature_data if d.get("target_temp")]
        humidity = [d["humidity"] for d in self.daily_temperature_data if d.get("humidity")]

        summary = {}

        if temps:
            summary["actual_temperature"] = {
                "min": min(temps),
                "max": max(temps),
                "avg": round(statistics.mean(temps), 2),
                "readings_count": len(temps)
            }

        if targets:
            summary["target_temperature"] = {
                "min": min(targets),
                "max": max(targets),
                "avg": round(statistics.mean(targets), 2),
                "changes_count": len(set(targets))
            }

        if humidity:
            summary["humidity"] = {
                "min": min(humidity),
                "max": max(humidity),
                "avg": round(statistics.mean(humidity), 2),
                "readings_count": len(humidity)
            }

        return summary

    def _summarize_user_inputs(self) -> Dict[str, Any]:
        """Summarize user inputs for the day."""
        if not self.daily_user_inputs:
            return {"total_inputs": 0, "services_used": []}

        services = [inp["service"] for inp in self.daily_user_inputs]
        service_counts = defaultdict(int)
        for service in services:
            service_counts[service] += 1

        return {
            "total_inputs": len(self.daily_user_inputs),
            "services_used": dict(service_counts),
            "unique_services": len(service_counts)
        }

    def _summarize_weather_data(self) -> Dict[str, Any]:
        """Summarize weather data for the day."""
        if not self.daily_weather_data:
            return {}

        # Get weather conditions
        conditions = [w["condition"] for w in self.daily_weather_data if w.get("condition")]
        temps = [w["temperature"] for w in self.daily_weather_data if w.get("temperature")]
        humidity = [w["humidity"] for w in self.daily_weather_data if w.get("humidity")]

        summary = {}

        if conditions:
            condition_counts = defaultdict(int)
            for condition in conditions:
                condition_counts[condition] += 1
            summary["conditions"] = dict(condition_counts)
            summary["primary_condition"] = max(condition_counts.keys(),
                                             key=condition_counts.get)

        if temps:
            summary["outdoor_temperature"] = {
                "min": min(temps),
                "max": max(temps),
                "avg": round(statistics.mean(temps), 2)
            }

        if humidity:
            summary["outdoor_humidity"] = {
                "min": min(humidity),
                "max": max(humidity),
                "avg": round(statistics.mean(humidity), 2)
            }

        return summary

    async def _get_current_thermal_rates(self) -> Dict[str, Any]:
        """Get current thermal learning rates."""
        thermal_entities = [e for e in self.hass.states.async_entity_ids()
                          if "thermal_learning" in e]

        if not thermal_entities:
            return {}

        # Get the first thermal learning entity
        entity_id = thermal_entities[0]
        state = self.hass.states.get(entity_id)

        if not state or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return {}

        return {
            "heating_rate_learned": state.attributes.get("heating_rate_learned"),
            "cooling_rate_learned": state.attributes.get("cooling_rate_learned"),
            "natural_rate_learned": state.attributes.get("natural_rate_learned"),
            "heating_samples": state.attributes.get("heating_samples"),
            "cooling_samples": state.attributes.get("cooling_samples"),
            "natural_samples": state.attributes.get("natural_samples"),
            "has_sufficient_data": state.attributes.get("has_sufficient_data"),
        }

    async def _calculate_moving_averages(self) -> Dict[str, Any]:
        """Calculate 7-day moving averages for thermal rates."""
        if len(self.historical_daily_data) < 2:
            return {}

        # Extract thermal rates from historical data
        heating_rates = []
        cooling_rates = []
        natural_rates = []

        for day_data in self.historical_daily_data:
            thermal = day_data.get("thermal_rates", {})
            if thermal.get("heating_rate_learned") is not None:
                heating_rates.append(thermal["heating_rate_learned"])
            if thermal.get("cooling_rate_learned") is not None:
                cooling_rates.append(thermal["cooling_rate_learned"])
            if thermal.get("natural_rate_learned") is not None:
                natural_rates.append(thermal["natural_rate_learned"])

        moving_averages = {}

        if heating_rates:
            moving_averages["heating_rate_7day_avg"] = round(
                statistics.mean(heating_rates), 4)
            moving_averages["heating_rate_samples"] = len(heating_rates)

        if cooling_rates:
            moving_averages["cooling_rate_7day_avg"] = round(
                statistics.mean(cooling_rates), 4)
            moving_averages["cooling_rate_samples"] = len(cooling_rates)

        if natural_rates:
            moving_averages["natural_rate_7day_avg"] = round(
                statistics.mean(natural_rates), 4)
            moving_averages["natural_rate_samples"] = len(natural_rates)

        return moving_averages

    # Event recording methods (called by main data collector)
    def record_hvac_cycle(self, action: str, start_time: datetime, end_time: datetime,
                         start_temp: float, end_temp: float) -> None:
        """Record an HVAC cycle."""
        duration = (end_time - start_time).total_seconds() / 60  # minutes

        cycle_data = {
            "action": action,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_minutes": round(duration, 2),
            "start_temperature": start_temp,
            "end_temperature": end_temp,
            "temperature_change": round(end_temp - start_temp, 2)
        }

        self.daily_hvac_cycles.append(cycle_data)

    def record_temperature_data(self, entity_id: str, state) -> None:
        """Record temperature data point."""
        self._record_temperature_data(entity_id, state)

    def _record_temperature_data(self, entity_id: str, state) -> None:
        """Internal method to record temperature data."""
        temp_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity_id": entity_id,
            "current_temp": state.attributes.get("current_temperature"),
            "target_temp": state.attributes.get("temperature"),
            "humidity": state.attributes.get("humidity"),
            "hvac_mode": state.attributes.get("hvac_mode"),
            "hvac_action": state.attributes.get("hvac_action"),
        }

        self.daily_temperature_data.append(temp_data)

    def record_user_input(self, service: str, service_data: Dict[str, Any]) -> None:
        """Record user input."""
        input_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": service,
            "parameters": service_data,
        }

        self.daily_user_inputs.append(input_data)

    def record_weather_data(self, entity_id: str, state) -> None:
        """Record weather data point."""
        self._record_weather_data(entity_id, state)

    def _record_weather_data(self, entity_id: str, state) -> None:
        """Internal method to record weather data."""
        weather_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity_id": entity_id,
            "condition": state.state,
            "temperature": state.attributes.get("temperature"),
            "humidity": state.attributes.get("humidity"),
            "pressure": state.attributes.get("pressure"),
            "wind_speed": state.attributes.get("wind_speed"),
        }

        self.daily_weather_data.append(weather_data)

    async def _send_daily_report(self, daily_report: Dict[str, Any]) -> None:
        """Send daily report to analytics backend."""
        if not self.data_endpoint:
            _LOGGER.warning("No data endpoint configured - skipping daily report")
            return

        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with self.session.post(
                f"{self.data_endpoint}/analytics-daily-report",
                json=daily_report,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully sent daily report for %s",
                               daily_report["date"])
                else:
                    _LOGGER.warning("Failed to send daily report: HTTP %d",
                                  response.status)

        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout sending daily report to analytics backend")
        except Exception as err:
            _LOGGER.warning("Error sending daily report: %s", err)