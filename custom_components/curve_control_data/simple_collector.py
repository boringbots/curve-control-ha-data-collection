"""Simple data collector for Curve Control - just raw 5-minute readings."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval, async_track_time_change
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_DATA_ENDPOINT, SUPABASE_ANON_KEY

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
        self._unsub_hourly = None
        self._unsub_midnight = None

    async def async_start(self):
        """Start the data collection."""
        _LOGGER.info("Starting curve control data collection")

        # Collect readings at specific clock times: :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55
        self._unsub_5min = async_track_time_change(
            self.hass,
            self._collect_reading,
            minute=[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55],
            second=0
        )

        # Send batched data at the top of each hour (:00)
        self._unsub_hourly = async_track_time_change(
            self.hass,
            self._send_hourly_batch,
            minute=0,
            second=30  # 30 seconds after the hour to ensure the :00 reading is collected
        )

        # Send daily summary at midnight
        self._unsub_midnight = async_track_time_change(
            self.hass,
            self._send_daily_summary,
            hour=0,
            minute=5,  # 5 minutes after midnight to ensure day rollover
            second=0
        )

        _LOGGER.info("Scheduled collection every 5 minutes on the clock (:00, :05, :10, etc.)")
        _LOGGER.info("Scheduled hourly batch upload at the top of each hour")
        _LOGGER.info("Scheduled daily summary at midnight")

        # Collect initial reading
        await self._collect_reading(None)

    async def async_stop(self):
        """Stop the data collection."""
        if self._unsub_5min:
            self._unsub_5min()
        if self._unsub_hourly:
            self._unsub_hourly()
        if self._unsub_midnight:
            self._unsub_midnight()

        # Send any remaining readings before stopping
        if self.pending_readings:
            _LOGGER.info("Sending final batch of readings before stopping...")
            await self._send_sensor_batch()

    async def _collect_reading(self, _):
        """Collect a single sensor reading."""
        try:
            _LOGGER.info("=== CURVE CONTROL SENSOR COLLECTION DEBUG ===")
            current_time = datetime.now()
            _LOGGER.info(f"Collection time: {current_time.strftime('%H:%M:%S')}")

            # Get current sensor values
            temp_state = self.hass.states.get(self.temperature_entity)
            hvac_state = self.hass.states.get(self.hvac_entity)
            thermostat_state = self.hass.states.get(self.thermostat_entity)

            _LOGGER.info(f"Checking required entities:")
            _LOGGER.info(f"  Temperature entity: {self.temperature_entity} -> {temp_state.state if temp_state else 'NOT FOUND'}")
            _LOGGER.info(f"  HVAC entity: {self.hvac_entity} -> {hvac_state.state if hvac_state else 'NOT FOUND'}")
            _LOGGER.info(f"  Thermostat entity: {self.thermostat_entity} -> {thermostat_state.state if thermostat_state else 'NOT FOUND'}")

            if not temp_state or not hvac_state or not thermostat_state:
                _LOGGER.error("❌ Missing required sensor states - cannot collect reading")
                return

            # Get humidity if available
            humidity = None
            if self.humidity_entity:
                humidity_state = self.hass.states.get(self.humidity_entity)
                _LOGGER.info(f"  Humidity entity: {self.humidity_entity} -> {humidity_state.state if humidity_state else 'NOT FOUND'}")
                if humidity_state and humidity_state.state not in ['unknown', 'unavailable']:
                    try:
                        humidity = float(humidity_state.state)
                        _LOGGER.info(f"  ✅ Humidity value: {humidity}")
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"  ⚠️ Could not convert humidity '{humidity_state.state}' to float: {e}")
            else:
                _LOGGER.info("  Humidity entity: Not configured")

            # Get HVAC action from climate entity
            hvac_action = hvac_state.attributes.get('hvac_action', 'off').upper()
            _LOGGER.info(f"  Raw HVAC action: {hvac_action}")

            # Map Home Assistant actions to our expected values
            if hvac_action in ['HEATING']:
                hvac_action = 'HEAT'
            elif hvac_action in ['COOLING']:
                hvac_action = 'COOL'
            else:
                hvac_action = 'OFF'
            _LOGGER.info(f"  Mapped HVAC action: {hvac_action}")

            try:
                indoor_temp = float(temp_state.state)
                target_temp = float(thermostat_state.attributes.get('temperature', 0))
                _LOGGER.info(f"  ✅ Temperature values: indoor={indoor_temp}, target={target_temp}")
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"  ❌ Could not convert temperature values to float: {e}")
                return

            # Create reading
            reading = {
                'timestamp': current_time.isoformat(),
                'indoor_temp': indoor_temp,
                'indoor_humidity': humidity,
                'hvac_state': hvac_action,
                'target_temp': target_temp
            }

            self.pending_readings.append(reading)
            _LOGGER.info(f"✅ Collected reading: {reading}")
            _LOGGER.info(f"Pending readings: {len(self.pending_readings)} (will send at top of hour)")

            # For manual triggers, send immediately for testing
            if hasattr(self, '_manual_trigger') and self._manual_trigger:
                _LOGGER.info("Manual trigger - sending reading immediately for testing...")
                await self._send_sensor_batch()
                self._manual_trigger = False
            # Note: Automatic readings are now sent via hourly timer, not immediate batch sending
            # This ensures consistent hourly uploads regardless of collection timing

            _LOGGER.info("=== END CURVE CONTROL SENSOR COLLECTION DEBUG ===")

        except Exception as e:
            _LOGGER.error(f"Error collecting sensor reading: {e}")

    async def _send_sensor_batch(self):
        """Send a batch of sensor readings."""
        if not self.pending_readings:
            _LOGGER.info("No pending readings to send")
            return

        try:
            session = async_get_clientsession(self.hass)

            payload = {
                'anonymous_id': self.anonymous_id,
                'readings': self.pending_readings
            }

            # Add authentication headers for Supabase
            headers = {
                'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
                'apikey': SUPABASE_ANON_KEY,
                'Content-Type': 'application/json'
            }

            _LOGGER.info(f"Sending {len(self.pending_readings)} readings to {self.data_endpoint}/sensor-data")
            _LOGGER.debug(f"Payload: {payload}")

            async with session.post(
                f"{self.data_endpoint}/sensor-data",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    _LOGGER.info(
                        f"✅ Successfully sent {len(self.pending_readings)} sensor readings. "
                        f"Server response: {result.get('message', 'Success')}"
                    )
                    self.pending_readings.clear()
                else:
                    error_text = await response.text()
                    _LOGGER.error(f"❌ Failed to send sensor readings: {response.status} - {error_text}")

        except asyncio.TimeoutError:
            _LOGGER.error("❌ Timeout sending sensor readings to server")
        except aiohttp.ClientError as e:
            _LOGGER.error(f"❌ Network error sending sensor readings: {e}")
        except Exception as e:
            _LOGGER.error(f"❌ Unexpected error sending sensor readings: {e}")

    async def _send_hourly_batch(self, _):
        """Send hourly batch of readings at the top of each hour."""
        if not self.pending_readings:
            _LOGGER.info("⏰ Hourly batch check - no pending readings to send")
            return

        current_time = datetime.now()
        _LOGGER.info(f"⏰ Hourly batch upload at {current_time.strftime('%H:%M:%S')} - sending {len(self.pending_readings)} readings")
        await self._send_sensor_batch()

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

            # Add authentication headers for Supabase
            headers = {
                'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
                'apikey': SUPABASE_ANON_KEY,
                'Content-Type': 'application/json'
            }

            async with session.post(
                f"{self.data_endpoint}/daily-summary",
                json=payload,
                headers=headers,
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

    async def trigger_manual_reading(self):
        """Trigger a manual reading (for testing or user request)."""
        _LOGGER.info("Triggering manual sensor reading")
        self._manual_trigger = True  # Flag to send immediately after collection
        await self._collect_reading(None)

    def get_sensor_status(self) -> Dict[str, str]:
        """Get status of all configured sensors."""
        status = {}

        # Check temperature entity
        if self.temperature_entity:
            temp_state = self.hass.states.get(self.temperature_entity)
            status['temperature'] = f"{temp_state.state} {temp_state.attributes.get('unit_of_measurement', '')}".strip() if temp_state else "Entity not found"
        else:
            status['temperature'] = "Not configured"

        # Check HVAC entity
        if self.hvac_entity:
            hvac_state = self.hass.states.get(self.hvac_entity)
            status['hvac'] = f"{hvac_state.state} (action: {hvac_state.attributes.get('hvac_action', 'unknown')})" if hvac_state else "Entity not found"
        else:
            status['hvac'] = "Not configured"

        # Check thermostat entity
        if self.thermostat_entity:
            thermo_state = self.hass.states.get(self.thermostat_entity)
            status['thermostat'] = f"{thermo_state.state} (target: {thermo_state.attributes.get('temperature', 'unknown')})" if thermo_state else "Entity not found"
        else:
            status['thermostat'] = "Not configured"

        # Check humidity entity (optional)
        if self.humidity_entity:
            humidity_state = self.hass.states.get(self.humidity_entity)
            status['humidity'] = f"{humidity_state.state} {humidity_state.attributes.get('unit_of_measurement', '')}".strip() if humidity_state else "Entity not found"
        else:
            status['humidity'] = "Not configured"

        # Check weather entity (optional)
        if self.weather_entity:
            weather_state = self.hass.states.get(self.weather_entity)
            status['weather'] = f"{weather_state.state}" if weather_state else "Entity not found"
        else:
            status['weather'] = "Not configured"

        return status

    def get_collection_stats(self) -> Dict[str, any]:
        """Get collection statistics."""
        return {
            'pending_readings': len(self.pending_readings),
            'collection_active': self._unsub_5min is not None,
            'daily_summary_active': self._unsub_midnight is not None,
            'user_inputs_today': len(self.user_inputs_today),
            'anonymous_id': self.anonymous_id[:8] + "..." if self.anonymous_id else "None",
            'data_endpoint': self.data_endpoint
        }