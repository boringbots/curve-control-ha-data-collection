"""Simple data collector for Curve Control - just raw 5-minute readings."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval, async_track_time_change
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_DATA_ENDPOINT

_LOGGER = logging.getLogger(__name__)

class SimpleDataCollector:
    """Collects raw sensor readings every 5 minutes and sends daily summaries."""

    def __init__(
        self,
        hass: HomeAssistant,
        anonymous_id: str,
        temperature_entity: str,
        hvac_entity: str,
        thermostat_entity: str,
        humidity_entity: Optional[str] = None,
        weather_entity: Optional[str] = None,
        data_endpoint: str = DEFAULT_DATA_ENDPOINT,
    ):
        self.hass = hass
        self.anonymous_id = anonymous_id
        self.temperature_entity = temperature_entity
        self.hvac_entity = hvac_entity
        self.thermostat_entity = thermostat_entity
        self.humidity_entity = humidity_entity
        self.weather_entity = weather_entity
        self.data_endpoint = data_endpoint

        # Storage for pending readings
        self.pending_readings: List[Dict] = []
        self.user_inputs_today: List[Dict] = []

        # Track unsubscribe functions
        self._unsub_5min = None
        self._unsub_midnight = None

    async def async_start(self):
        """Start the data collection."""
        _LOGGER.info("Starting simple data collection")

        # Collect readings every 5 minutes
        self._unsub_5min = async_track_time_interval(
            self.hass,
            self._collect_reading,
            timedelta(minutes=5)
        )

        # Send daily summary at midnight
        self._unsub_midnight = async_track_time_change(
            self.hass,
            self._send_daily_summary,
            hour=0,
            minute=5,  # 5 minutes after midnight to ensure day rollover
            second=0
        )

        # Collect initial reading
        await self._collect_reading(None)

    async def async_stop(self):
        """Stop the data collection."""
        if self._unsub_5min:
            self._unsub_5min()
        if self._unsub_midnight:
            self._unsub_midnight()

    async def _collect_reading(self, _):
        """Collect a single sensor reading."""
        try:
            # Get current sensor values
            temp_state = self.hass.states.get(self.temperature_entity)
            hvac_state = self.hass.states.get(self.hvac_entity)
            thermostat_state = self.hass.states.get(self.thermostat_entity)

            if not temp_state or not hvac_state or not thermostat_state:
                _LOGGER.warning("Missing required sensor states")
                return

            # Get humidity if available
            humidity = None
            if self.humidity_entity:
                humidity_state = self.hass.states.get(self.humidity_entity)
                if humidity_state and humidity_state.state not in ['unknown', 'unavailable']:
                    try:
                        humidity = float(humidity_state.state)
                    except (ValueError, TypeError):
                        pass

            # Get HVAC action from climate entity
            hvac_action = hvac_state.attributes.get('hvac_action', 'off').upper()
            # Map Home Assistant actions to our expected values
            if hvac_action in ['HEATING']:
                hvac_action = 'HEAT'
            elif hvac_action in ['COOLING']:
                hvac_action = 'COOL'
            else:
                hvac_action = 'OFF'

            # Create reading
            reading = {
                'timestamp': datetime.now().isoformat(),
                'indoor_temp': float(temp_state.state),
                'indoor_humidity': humidity,
                'hvac_state': hvac_action,
                'target_temp': float(thermostat_state.attributes.get('temperature', 0))
            }

            self.pending_readings.append(reading)

            # Send readings in batches of 12 (1 hour worth)
            if len(self.pending_readings) >= 12:
                await self._send_sensor_batch()

        except Exception as e:
            _LOGGER.error(f"Error collecting sensor reading: {e}")

    async def _send_sensor_batch(self):
        """Send a batch of sensor readings."""
        if not self.pending_readings:
            return

        try:
            session = async_get_clientsession(self.hass)

            payload = {
                'anonymous_id': self.anonymous_id,
                'readings': self.pending_readings
            }

            async with session.post(
                f"{self.data_endpoint}/sensor-data",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    _LOGGER.debug(f"Sent {len(self.pending_readings)} sensor readings")
                    self.pending_readings.clear()
                else:
                    _LOGGER.error(f"Failed to send sensor readings: {response.status}")

        except Exception as e:
            _LOGGER.error(f"Error sending sensor readings: {e}")

    async def _send_daily_summary(self, _):
        """Send daily summary at midnight."""
        try:
            # Send any pending readings first
            if self.pending_readings:
                await self._send_sensor_batch()

            # Get weather forecast for tomorrow
            weather_forecast = None
            if self.weather_entity:
                weather_state = self.hass.states.get(self.weather_entity)
                if weather_state:
                    weather_forecast = {
                        'condition': weather_state.state,
                        'temperature': weather_state.attributes.get('temperature'),
                        'humidity': weather_state.attributes.get('humidity'),
                        'forecast': weather_state.attributes.get('forecast', [])[:5]  # Next 5 periods
                    }

            # Prepare user inputs (services called today)
            user_inputs = {
                'inputs_today': len(self.user_inputs_today),
                'services_used': self.user_inputs_today
            }

            # Send daily summary
            session = async_get_clientsession(self.hass)

            payload = {
                'anonymous_id': self.anonymous_id,
                'date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),  # Yesterday's data
                'user_inputs': user_inputs,
                'weather_forecast': weather_forecast
            }

            async with session.post(
                f"{self.data_endpoint}/daily-summary",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    thermal_rates = result.get('thermal_rates', {})

                    _LOGGER.info(f"Daily summary sent. Thermal rates: {thermal_rates}")

                    # Store thermal rates as sensor values for Home Assistant to use
                    if thermal_rates:
                        await self._update_thermal_rate_sensors(thermal_rates)
                else:
                    _LOGGER.error(f"Failed to send daily summary: {response.status}")

            # Reset daily counters
            self.user_inputs_today.clear()

        except Exception as e:
            _LOGGER.error(f"Error sending daily summary: {e}")

    async def _update_thermal_rate_sensors(self, thermal_rates: Dict):
        """Update Home Assistant sensors with calculated thermal rates."""
        try:
            # These will be used by the thermal learning system
            if 'heating_rate' in thermal_rates and thermal_rates['heating_rate']:
                self.hass.states.async_set(
                    "sensor.curve_control_heating_rate",
                    thermal_rates['heating_rate'],
                    {'unit_of_measurement': '°F/hr', 'samples': thermal_rates.get('heating_samples', 0)}
                )

            if 'cooling_rate' in thermal_rates and thermal_rates['cooling_rate']:
                self.hass.states.async_set(
                    "sensor.curve_control_cooling_rate",
                    thermal_rates['cooling_rate'],
                    {'unit_of_measurement': '°F/hr', 'samples': thermal_rates.get('cooling_samples', 0)}
                )

            if 'natural_rate' in thermal_rates and thermal_rates['natural_rate']:
                self.hass.states.async_set(
                    "sensor.curve_control_natural_rate",
                    thermal_rates['natural_rate'],
                    {'unit_of_measurement': '°F/hr', 'samples': thermal_rates.get('natural_samples', 0)}
                )

        except Exception as e:
            _LOGGER.error(f"Error updating thermal rate sensors: {e}")

    def log_user_input(self, service: str, data: Dict):
        """Log a user input/service call for today's summary."""
        self.user_inputs_today.append({
            'timestamp': datetime.now().isoformat(),
            'service': service,
            'data': data
        })