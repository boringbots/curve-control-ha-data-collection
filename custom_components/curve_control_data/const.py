"""Constants for the Curve Control Data Collection integration."""
from typing import Final

DOMAIN: Final = "curve_control_data"

# Configuration keys
CONF_DATA_ENDPOINT: Final = "data_endpoint"
CONF_API_KEY: Final = "api_key"
CONF_COLLECTION_LEVEL: Final = "collection_level"
CONF_ANONYMOUS_ID: Final = "anonymous_id"

# Defaults
DEFAULT_DATA_ENDPOINT: Final = "https://bwtakgwvkeflttjytuje.supabase.co/functions/v1"
DEFAULT_COLLECTION_LEVEL: Final = "standard"

# Collection levels
COLLECTION_LEVELS: Final = {
    "minimal": "Basic usage data only",
    "standard": "Temperature, HVAC, and optimization data", 
    "detailed": "Full analytics including weather and learning data"
}

# Data collection intervals
COLLECTION_INTERVAL_SECONDS: Final = 300  # 5 minutes
BATCH_SIZE: Final = 10  # Number of records to batch before sending
MAX_QUEUE_SIZE: Final = 1000  # Maximum records to queue locally

# Monitored entity patterns
CURVE_CONTROL_ENTITIES: Final = [
    "sensor.curve_control_energy_optimizer_*",
    "climate.curve_control_energy_optimizer_*",
    "switch.curve_control_*"
]

# Data types to collect
DATA_TYPES: Final = {
    "temperature": "Temperature readings and setpoints",
    "hvac_action": "HVAC system actions and cycles", 
    "user_input": "User preference changes and overrides",
    "thermal_learning": "Heat-up and cool-down rate learning",
    "weather": "Weather conditions and forecasts",
    "optimization": "Optimization results and performance metrics"
}

# Event types
EVENT_USER_INPUT: Final = "user_input"
EVENT_TEMPERATURE_CHANGE: Final = "temperature_change"
EVENT_HVAC_ACTION: Final = "hvac_action"
EVENT_OPTIMIZATION_RESULT: Final = "optimization_result"
EVENT_THERMAL_LEARNING: Final = "thermal_learning"
EVENT_WEATHER_UPDATE: Final = "weather_update"
EVENT_DAILY_SUMMARY: Final = "daily_summary"