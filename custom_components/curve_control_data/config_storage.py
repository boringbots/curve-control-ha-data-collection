"""Configuration storage for Curve Control Data Collection."""
import json
import os
import logging
import uuid
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)

class ConfigStorage:
    """Handles persistent storage of sensor configuration."""

    def __init__(self, config_dir: str):
        """Initialize config storage."""
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "curve_control_data_config.json")

    async def save_sensor_config(self, sensor_entities: Dict[str, str], anonymous_id: str, data_endpoint: str):
        """Save sensor configuration to file."""
        try:
            config = {
                "sensor_entities": sensor_entities,
                "anonymous_id": anonymous_id,
                "data_endpoint": data_endpoint,
                "version": "1.0"
            }

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            _LOGGER.info(f"Saved sensor configuration to {self.config_file}")

        except Exception as e:
            _LOGGER.error(f"Error saving sensor configuration: {e}")

    async def load_sensor_config(self) -> Optional[Dict]:
        """Load sensor configuration from file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)

                _LOGGER.info(f"Loaded sensor configuration from {self.config_file}")
                return config
            else:
                _LOGGER.debug("No stored sensor configuration found")
                return None

        except Exception as e:
            _LOGGER.error(f"Error loading sensor configuration: {e}")
            return None

    def delete_config(self):
        """Delete the configuration file."""
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
                _LOGGER.info(f"Deleted configuration file: {self.config_file}")
        except Exception as e:
            _LOGGER.error(f"Error deleting configuration file: {e}")

    async def get_or_create_anonymous_id(self) -> str:
        """Get existing anonymous ID or create a new one."""
        config = await self.load_sensor_config()
        if config and config.get("anonymous_id"):
            return config["anonymous_id"]
        else:
            return str(uuid.uuid4())