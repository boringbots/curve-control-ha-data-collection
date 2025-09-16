# Curve Control Data Collection

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant integration that collects HVAC sensor data for thermal learning and optimization.

## Features

- **5-minute sensor collection**: Indoor temperature, humidity, HVAC state, and target temperature
- **Daily thermal rate calculation**: Heating, cooling, and natural drift rates calculated from your HVAC data
- **Privacy-focused**: Uses anonymous IDs, no personal information collected
- **Lightweight**: Simple data collection with minimal impact on Home Assistant performance

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the "+" button
4. Search for "Curve Control Data Collection"
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy `custom_components/curve_control_data` to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Curve Control Data Collection"
4. Configure the required entities:
   - **Temperature Entity**: Sensor that reports current indoor temperature
   - **HVAC Entity**: Climate entity that shows HVAC action (heating/cooling/off)
   - **Thermostat Entity**: Climate entity for target temperature
   - **Humidity Entity** (optional): Indoor humidity sensor
   - **Weather Entity** (optional): Weather integration for forecasts

## How It Works

1. **Data Collection**: Every 5 minutes, collects current temperature, humidity, HVAC state, and target temperature
2. **Batching**: Sends data in 1-hour batches to minimize network requests
3. **Daily Processing**: At midnight, sends daily summary and receives calculated thermal rates
4. **Thermal Learning**: Creates Home Assistant sensors with calculated rates:
   - `sensor.curve_control_heating_rate` - °F/hour heating rate
   - `sensor.curve_control_cooling_rate` - °F/hour cooling rate
   - `sensor.curve_control_natural_rate` - °F/hour natural drift rate

## Privacy

- Uses anonymous UUIDs - no personal information collected
- Only HVAC performance data is transmitted
- Data is used solely for thermal learning calculations
- No user identification or location tracking

## Thermal Rate Sensors

The integration creates sensors that can be used by other automations:

```yaml
# Example automation using thermal rates
automation:
  - alias: "Optimize heating based on learned rates"
    trigger:
      platform: state
      entity_id: sensor.curve_control_heating_rate
    action:
      service: climate.set_temperature
      data:
        temperature: "{{ (states('sensor.target_temp') | float) + (states('sensor.curve_control_heating_rate') | float * 0.1) }}"
```

## Troubleshooting

- **No thermal rates calculated**: Ensure HVAC system runs regularly and check logs for data collection
- **Integration won't load**: Verify all required entities exist and are accessible
- **Data not sending**: Check internet connectivity and backend service status

## Support

- [GitHub Issues](https://github.com/boringbots/curve-control-ha-data-collection/issues)
- [Documentation](https://github.com/boringbots/curve-control-ha-data-collection)

## Related Projects

- [Curve Control HA Integration](https://github.com/boringbots/curve-control-ha-integration) - Main HVAC optimization integration