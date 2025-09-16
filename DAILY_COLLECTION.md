# Daily Data Collection System

This document describes the new daily data collection and aggregation system for Curve Control analytics.

## Overview

The system now collects two types of data:

1. **Real-time Events** - Individual state changes and actions (existing system)
2. **Daily Summaries** - Aggregated daily reports sent at midnight (new system)

## Daily Data Collection

### What Data is Collected Daily

Every day at midnight (00:00), the system collects and sends a comprehensive daily report containing:

#### 1. HVAC Cycles Data
- **Total cycles**: Number of heating/cooling cycles
- **Cycle breakdown**: Separate counts for heating vs cooling
- **Runtime data**: Total minutes of operation per type
- **Cycle efficiency**: Average cycle length and temperature changes
- **Detailed cycle records**: Start/end times, temperatures, and durations

#### 2. Temperature & Humidity Data
- **Actual temperatures**: Min, max, average indoor temperatures
- **Target temperatures**: Setpoint changes and patterns
- **Humidity levels**: Indoor humidity readings throughout the day
- **Temperature variance**: How much actual temp varied from target

#### 3. User Inputs
- **Service calls**: All curve_control service invocations
- **Parameter changes**: Settings modifications and overrides
- **User interactions**: Frequency and types of manual adjustments

#### 4. Weather Conditions
- **Outdoor temperature**: Daily min, max, average
- **Weather conditions**: Primary weather patterns (sunny, cloudy, rainy, etc.)
- **Humidity**: Outdoor humidity levels
- **Pressure**: Atmospheric pressure readings

#### 5. Thermal Learning Rates
- **Heating rate**: Equipment heating performance (°F/30min when heater ON)
- **Cooling rate**: Equipment cooling performance (°F/30min when AC ON)
- **Natural rate**: Building thermal drift (°F/30min when HVAC OFF)
- **Sample counts**: Number of data points used for each rate
- **Learning status**: Whether sufficient data exists for reliable rates

### 7-Day Moving Averages

The backend calculates and returns:

- **Heating Rate 7-day Average**: Moving average of heating equipment performance
- **Cooling Rate 7-day Average**: Moving average of cooling equipment performance
- **Natural Rate 7-day Average**: Moving average of natural building thermal behavior
- **Trend Analysis**: Whether each rate is increasing, decreasing, or stable
- **Confidence Metrics**: Standard deviation and sample counts

## Data Flow Architecture

```
Home Assistant
     ↓ (Real-time events)
Real-time Data Collector
     ↓ (Feeds daily aggregator)
Daily Data Aggregator
     ↓ (Midnight trigger)
Daily Report Generation
     ↓ (HTTP POST)
Analytics Backend
     ↓ (Processes & stores)
Database Storage
     ↓ (Calculates)
7-Day Moving Averages
```

## Technical Implementation

### Daily Aggregator (`daily_aggregator.py`)

- **Midnight Timer**: Uses `async_track_time_change` to trigger at 00:00
- **Data Aggregation**: Summarizes all daily events into structured reports
- **HVAC Cycle Tracking**: Monitors state changes to detect complete cycles
- **Moving Average Calculation**: Computes 7-day rolling averages locally
- **Data Transmission**: Sends daily reports to backend via HTTP POST

### Data Collector Integration

The main data collector (`data_collector.py`) now:

- **Dual Collection**: Continues real-time event collection AND feeds daily aggregator
- **Cycle Detection**: Tracks HVAC on/off cycles for daily summaries
- **State Monitoring**: Records temperature, humidity, and weather data points
- **User Input Tracking**: Captures all service calls and parameter changes

### Backend API (`backend_example.py`)

Example Flask backend that:

- **Receives Daily Reports**: `/analytics/daily_report` endpoint
- **Stores Data**: SQLite database with daily reports and thermal rates
- **Calculates Moving Averages**: 7-day rolling averages with trend analysis
- **Serves Analytics**: API endpoints for retrieving historical data and averages

## Database Schema

### Daily Reports Table
```sql
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY,
    anonymous_id TEXT NOT NULL,
    date TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    daily_summary TEXT NOT NULL,  -- JSON blob
    moving_averages TEXT,         -- JSON blob
    UNIQUE(anonymous_id, date)
);
```

### Thermal Rates History Table
```sql
CREATE TABLE thermal_rates_history (
    id INTEGER PRIMARY KEY,
    anonymous_id TEXT NOT NULL,
    date TEXT NOT NULL,
    heating_rate REAL,
    cooling_rate REAL,
    natural_rate REAL,
    heating_samples INTEGER,
    cooling_samples INTEGER,
    natural_samples INTEGER,
    UNIQUE(anonymous_id, date)
);
```

## API Endpoints

### POST `/analytics/daily_report`
Receives daily summary reports from Home Assistant.

**Request Body:**
```json
{
  "date": "2025-01-15",
  "anonymous_id": "user-12345",
  "daily_summary": {
    "hvac_cycles": { ... },
    "temperature_data": { ... },
    "user_inputs": { ... },
    "weather_data": { ... },
    "thermal_rates": { ... }
  },
  "moving_averages": { ... },
  "timestamp": "2025-01-16T00:00:00Z"
}
```

### GET `/analytics/moving_averages/{anonymous_id}`
Returns current 7-day moving averages.

**Response:**
```json
{
  "anonymous_id": "user-12345",
  "moving_averages": {
    "heating_rate_7day_avg": 2.4567,
    "cooling_rate_7day_avg": 1.8934,
    "natural_rate_7day_avg": 0.5432,
    "heating_rate_trend": "stable",
    "cooling_rate_trend": "increasing",
    "natural_rate_trend": "decreasing",
    "days_included": 7
  }
}
```

### GET `/analytics/thermal_history/{anonymous_id}`
Returns historical thermal rates data.

## Benefits

1. **Seasonal Adaptation**: Natural rate automatically adjusts to changing weather
2. **Equipment Performance Tracking**: Separate heating and cooling efficiency monitoring
3. **User Behavior Analysis**: Understanding of manual override patterns
4. **Weather Correlation**: Ability to correlate performance with weather conditions
5. **Predictive Analytics**: Moving averages enable trend detection and forecasting
6. **Privacy Preserved**: Anonymous data collection with no personally identifiable information

## Configuration

The daily collection system uses the same configuration as the real-time collector:

- **Data Endpoint**: Where to send daily reports
- **API Key**: Authentication for backend communication
- **Collection Level**: standard/detailed (affects granularity)
- **Anonymous ID**: Unique identifier for data correlation

## Deployment

1. **Install Integration**: Deploy the updated curve-control-ha-data-collection
2. **Configure Backend**: Set up analytics backend to receive daily reports
3. **Database Setup**: Initialize SQLite or preferred database
4. **API Deployment**: Deploy backend API to cloud platform
5. **Configuration**: Update Home Assistant with backend endpoint

The system will automatically begin collecting daily data and sending midnight reports.