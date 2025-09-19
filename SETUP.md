# Curve Control Data Collection - Setup Guide

## 🚀 Quick Start

Your Curve Control Data Collection integration has been updated with the working reference implementation features. Follow these steps to get it working:

### Step 1: Configure Supabase Authentication

1. **Get your Supabase project details:**
   - Go to your Supabase project dashboard
   - Navigate to Settings > API
   - Copy the **Project URL** and **anon public key**

2. **Update the integration constants:**
   ```python
   # Edit: custom_components/curve_control_data/const.py

   # Line 13: Update with your Supabase URL
   DEFAULT_DATA_ENDPOINT: Final = "https://YOUR-PROJECT.supabase.co/functions/v1"

   # Line 17: Add your Supabase anon key
   SUPABASE_ANON_KEY: Final = "your_actual_anon_key_here"
   ```

### Step 2: Ensure Backend is Deployed

1. **Verify your Supabase backend has:**
   - ✅ Database schema from `simple_schema.sql`
   - ✅ Edge function `sensor-data` deployed
   - ✅ Edge function `daily-summary` deployed

2. **Test backend with curl:**
   ```bash
   curl -X POST "https://YOUR-PROJECT.supabase.co/functions/v1/sensor-data" \
     -H "Authorization: Bearer YOUR-ANON-KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "anonymous_id": "test-user",
       "readings": [{
         "timestamp": "2025-01-19T10:00:00Z",
         "indoor_temp": 72.5,
         "indoor_humidity": 45.2,
         "hvac_state": "OFF",
         "target_temp": 72.0
       }]
     }'
   ```

### Step 3: Install Updated Integration

1. **Copy files to Home Assistant:**
   ```bash
   # Copy the entire custom_components/curve_control_data directory
   # to your Home Assistant custom_components folder
   ```

2. **Restart Home Assistant**

### Step 4: Configure Integration

1. **Add integration in HA:**
   - Settings → Devices & Services
   - Add Integration → "Curve Control Data Collection"

2. **Configure required entities:**
   - **Temperature Entity**: Indoor temperature sensor
   - **HVAC Entity**: Climate entity that shows HVAC action
   - **Thermostat Entity**: Climate entity for target temperature
   - **Humidity Entity** (optional): Indoor humidity sensor
   - **Weather Entity** (optional): Weather integration

### Step 5: Test the Integration

1. **Check HA logs for startup:**
   ```
   Looking for: "Starting curve control data collection"
   ```

2. **Trigger manual reading:**
   ```yaml
   # In Developer Tools > Services:
   service: curve_control_data.trigger_manual_reading
   ```

3. **Check sensor status:**
   ```yaml
   # In Developer Tools > Services:
   service: curve_control_data.get_sensor_status
   ```

4. **Monitor logs for collection:**
   ```
   Looking for: "=== CURVE CONTROL SENSOR COLLECTION DEBUG ==="
   ```

## 🔍 New Features Added

### Enhanced Debugging
- Detailed logging shows exactly what sensors are being read
- Step-by-step collection process with ✅ ❌ indicators
- Network request/response logging

### Manual Testing Services
- `curve_control_data.trigger_manual_reading` - Test collection immediately
- `curve_control_data.get_sensor_status` - Check all sensor states

### Better Timing
- Uses precise clock-based timing (every 5 minutes: :00, :05, :10, etc.)
- More reliable than interval-based timing

### Authentication Fixed
- Proper Supabase authentication headers included
- No more 401/403 errors

### Configuration Storage
- Settings persist across HA restarts
- Better error handling and recovery

## 🛠️ Troubleshooting

### No Data Being Collected
1. Check HA logs for sensor collection debug messages
2. Verify entity IDs are correct and entities exist
3. Ensure entities have numeric values (not 'unknown' or 'unavailable')

### Authentication Errors (401/403)
1. Double-check your Supabase anon key in `const.py`
2. Verify your Supabase project URL is correct
3. Test backend with curl command above

### Network Errors
1. Check internet connectivity from HA
2. Verify Supabase edge functions are deployed and running
3. Check HA logs for specific error messages

### Sensor Status Issues
1. Use the `get_sensor_status` service to check entity states
2. Verify climate entities support `hvac_action` attribute
3. Check that temperature sensors return numeric values

## 📊 Expected Behavior

### Every 5 Minutes
- Detailed sensor collection logging appears
- Reading is added to pending batch
- After 12 readings (1 hour), batch is sent to Supabase

### Daily at Midnight
- Daily summary is sent with user inputs and weather
- Thermal rates are calculated and returned
- Thermal rate sensors are created in HA:
  - `sensor.curve_control_heating_rate`
  - `sensor.curve_control_cooling_rate`
  - `sensor.curve_control_natural_rate`

### Manual Testing
- `trigger_manual_reading` immediately collects and sends one reading
- `get_sensor_status` logs current state of all configured entities

## ⚡ Key Differences from Reference

- Adapted for HVAC thermal learning (vs general multi-sensor)
- Uses curve control specific entity names and data structure
- Includes daily thermal rate calculation and response handling
- Maintains existing thermal learning sensor creation

Your integration now has all the robust features from the working reference implementation!