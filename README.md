# Curve Control Data Collection for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

An optional Home Assistant integration that anonymously collects usage data from Curve Control Energy Optimizer to help improve optimization algorithms and provide better energy savings.

## Features

- **Anonymous Data Collection** - All data is collected with anonymous IDs, no personal information
- **Configurable Collection Levels** - Choose what data to share (minimal, standard, or detailed)
- **Privacy-First Design** - Data is queued locally and sent in batches
- **Automatic Discovery** - Finds and monitors Curve Control entities automatically
- **Resilient Communication** - Re-queues data if backend is temporarily unavailable

## What Data is Collected

### Minimal Level
- Basic integration usage (start/stop events)
- Anonymous installation ID

### Standard Level (Default)
- Temperature readings and setpoints
- HVAC actions and cycles
- User preference changes
- Optimization results and performance metrics

### Detailed Level
- All standard data plus:
- Thermal learning progress (heat-up/cool-down rates)
- Weather conditions
- Detailed optimization analytics

## Privacy & Security

- **Anonymous IDs**: Each installation gets a unique anonymous identifier
- **No Personal Data**: No names, addresses, or identifying information collected
- **Local Queuing**: Data is stored locally and sent in batches
- **Configurable**: You choose what level of data to share
- **Transparent**: Open source - you can see exactly what data is collected

## Installation

### Method 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu → Custom repositories
4. Add this repository URL with category "Integration"
5. Install "Curve Control Data Collection"
6. Restart Home Assistant

### Method 2: Manual Installation

1. Copy the `curve_control_data` folder to your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "Curve Control Data Collection"

## Configuration

1. **Collection Level**: Choose how much data to share
   - **Minimal**: Basic usage only
   - **Standard**: Temperature and optimization data (recommended)
   - **Detailed**: Full analytics including weather and learning data

2. **Analytics Endpoint**: (Advanced) URL where data is sent
3. **API Key**: (Optional) Authentication key if required

## Data Usage

The collected data helps:

- **Improve Algorithms**: Better optimization strategies based on real-world usage
- **Algorithm Training**: Machine learning models for better energy predictions  
- **Feature Development**: Understanding how users interact with the system
- **Bug Detection**: Identifying common issues and edge cases
- **Regional Optimization**: Better algorithms for different climates and utility rates

## Technical Details

### Data Collection Events

- **Temperature Changes**: Current temp, setpoints, HVAC mode
- **HVAC Actions**: Heating/cooling cycles, idle periods
- **User Inputs**: Settings changes, manual overrides
- **Optimization Results**: Energy savings, cost reductions
- **Thermal Learning**: Heat-up/cool-down rate calculations
- **Weather Updates**: Outdoor conditions (detailed level only)

### Data Format

Data is sent as JSON with this structure:

```json
{
  "anonymous_id": "uuid-generated-id",
  "integration_version": "1.0.0", 
  "collection_level": "standard",
  "data_points": [
    {
      "event_type": "temperature_change",
      "timestamp": "2024-01-01T12:00:00Z",
      "entity_id": "climate.curve_control_thermostat",
      "data": {
        "current_temperature": 72.5,
        "target_temperature": 72.0,
        "hvac_action": "idle"
      }
    }
  ]
}
```

### Collection Frequency

- **State Changes**: Monitored continuously 
- **Batch Sending**: Every 5 minutes
- **Batch Size**: Up to 10 data points per batch
- **Queue Limit**: Maximum 1000 points stored locally

## Disabling Data Collection

To stop data collection:

1. Go to Settings → Devices & Services
2. Find "Curve Control Data Collection"
3. Click "Remove Integration"

Or disable specific data types by changing the collection level.

## Support

For issues, feature requests, or questions:
- Open an issue on GitHub
- Check the [documentation](https://github.com/boringbots/curve-control-ha-data-collection)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

We welcome contributions! Please see our contributing guidelines for more information.

---

**Note**: This integration is completely optional and separate from the main Curve Control Energy Optimizer. The main integration works perfectly without data collection enabled.