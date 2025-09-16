# Native PostgreSQL Time-Series Solution

This guide explains the future-proofed implementation using PostgreSQL's native time-series capabilities instead of TimescaleDB.

## Why Native PostgreSQL?

### **TimescaleDB Deprecation**
Supabase is deprecating TimescaleDB support in favor of native PostgreSQL time-series features:
- **Simplified Architecture**: No external dependencies
- **Better Supabase Integration**: Full compatibility with all Supabase features
- **Future-Proof**: Based on stable PostgreSQL core features
- **Performance**: Comparable performance for most use cases
- **Maintenance**: Reduced complexity and maintenance overhead

### **Native PostgreSQL Time-Series Features**

1. **Native Partitioning**: PostgreSQL's built-in table partitioning
2. **Materialized Views**: Pre-computed aggregations with concurrent refresh
3. **Window Functions**: Advanced analytics without external extensions
4. **JSONB Support**: Flexible schema for varying data structures
5. **Advanced Indexing**: GIN, GiST, and partial indexes for optimization

## Architecture Overview

### **Partitioning Strategy**

#### **Daily Reports** - Monthly Partitions
```sql
-- Partitioned by report_date (monthly)
daily_reports_2025_01  -- January 2025
daily_reports_2025_02  -- February 2025
```

#### **Thermal Rates History** - Weekly Partitions
```sql
-- Partitioned by measured_at (weekly)
thermal_rates_history_2025_01  -- Week 1, 2025
thermal_rates_history_2025_02  -- Week 2, 2025
```

#### **Real-time Events** - Daily Partitions
```sql
-- Partitioned by timestamp (daily)
realtime_events_2025_01_15  -- January 15, 2025
realtime_events_2025_01_16  -- January 16, 2025
```

#### **HVAC Cycles** - Weekly Partitions
```sql
-- Partitioned by start_time (weekly)
hvac_cycles_2025_01  -- Week 1, 2025
hvac_cycles_2025_02  -- Week 2, 2025
```

### **Performance Optimizations**

#### **Partition Pruning**
```sql
-- Query automatically uses only relevant partitions
SELECT * FROM daily_reports
WHERE report_date BETWEEN '2025-01-01' AND '2025-01-31';
-- Only queries daily_reports_2025_01 partition
```

#### **Constraint Exclusion**
```sql
-- PostgreSQL automatically excludes irrelevant partitions
SELECT * FROM thermal_rates_history
WHERE measured_at >= '2025-01-15'::timestamptz;
-- Excludes older partitions automatically
```

#### **Parallel Query Execution**
```sql
-- PostgreSQL can query multiple partitions in parallel
SELECT anonymous_id, AVG(heating_rate)
FROM thermal_rates_history
WHERE measured_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY anonymous_id;
-- Executes across multiple partitions simultaneously
```

## Materialized Views for Analytics

### **Hourly Thermal Rates**
```sql
CREATE MATERIALIZED VIEW hourly_thermal_rates AS
SELECT
    DATE_TRUNC('hour', measured_at) AS hour,
    anonymous_id,
    AVG(heating_rate) as avg_heating_rate,
    AVG(cooling_rate) as avg_cooling_rate,
    AVG(natural_rate) as avg_natural_rate,
    COUNT(*) as measurements_count
FROM thermal_rates_history
WHERE measured_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', measured_at), anonymous_id;
```

### **Daily HVAC Performance**
```sql
CREATE MATERIALIZED VIEW daily_hvac_performance AS
SELECT
    DATE_TRUNC('day', start_time) AS day,
    anonymous_id,
    action,
    COUNT(*) as cycle_count,
    AVG(duration_minutes) as avg_duration,
    AVG(ABS(temperature_change)) as avg_temp_change,
    AVG(efficiency_rating) as avg_efficiency
FROM hvac_cycles
WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', start_time), anonymous_id, action;
```

### **Concurrent Refresh**
```sql
-- Safe refresh without blocking queries
REFRESH MATERIALIZED VIEW CONCURRENTLY hourly_thermal_rates;
```

## Advanced PostgreSQL Features Used

### **Generated Columns**
```sql
-- Automatically calculated columns
duration_minutes REAL GENERATED ALWAYS AS
    (EXTRACT(EPOCH FROM (end_time - start_time)) / 60) STORED,
temperature_change REAL GENERATED ALWAYS AS
    (end_temperature - start_temperature) STORED
```

### **Partial Indexes**
```sql
-- Index only on relevant data
CREATE INDEX idx_daily_reports_thermal_rates
ON daily_reports(anonymous_id)
WHERE heating_rate_learned IS NOT NULL;
```

### **JSONB Columns**
```sql
-- Flexible data storage for varying event types
event_data JSONB NOT NULL DEFAULT '{}',
user_services_used JSONB DEFAULT '{}'
```

### **Window Functions for Trends**
```sql
-- Trend calculation using native PostgreSQL
WITH recent_rates AS (
    SELECT heating_rate,
           ROW_NUMBER() OVER (ORDER BY report_date DESC) as rn
    FROM thermal_rates_history
    WHERE anonymous_id = 'user123'
)
SELECT
    CASE
        WHEN (SELECT AVG(heating_rate) FROM recent_rates WHERE rn <= 3) >
             (SELECT AVG(heating_rate) FROM recent_rates WHERE rn > 3)
        THEN 'increasing'
        ELSE 'decreasing'
    END as trend
```

## Automated Maintenance

### **Partition Management**
```sql
-- Function to create new partitions
CREATE OR REPLACE FUNCTION create_new_partitions()
RETURNS VOID AS $$
DECLARE
    start_date TIMESTAMPTZ;
    end_date TIMESTAMPTZ;
    partition_name TEXT;
BEGIN
    -- Create next month's partition
    start_date := DATE_TRUNC('month', CURRENT_DATE + INTERVAL '1 month');
    end_date := start_date + INTERVAL '1 month';
    partition_name := 'daily_reports_' || TO_CHAR(start_date, 'YYYY_MM');

    EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF daily_reports
                   FOR VALUES FROM (%L) TO (%L)',
                   partition_name, start_date, end_date);
END;
$$ LANGUAGE plpgsql;
```

### **Automatic Cleanup**
```sql
-- Function to drop old partitions
CREATE OR REPLACE FUNCTION cleanup_old_partitions()
RETURNS VOID AS $$
DECLARE
    partition_record RECORD;
    cutoff_date TIMESTAMPTZ;
BEGIN
    cutoff_date := CURRENT_TIMESTAMP - INTERVAL '30 days';

    FOR partition_record IN
        SELECT tablename
        FROM pg_tables
        WHERE tablename LIKE 'realtime_events_%'
        AND tablename < 'realtime_events_' || TO_CHAR(cutoff_date, 'YYYY_MM_DD')
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS %I', partition_record.tablename);
    END LOOP;
END;
$$ LANGUAGE plpgsql;
```

### **Edge Function Scheduler**
```typescript
// Maintenance scheduler edge function
export default async function(req: Request) {
    // Refresh materialized views
    await supabase.rpc('refresh_analytics_views')

    // Create new partitions
    await supabase.rpc('create_new_partitions')

    // Cleanup old partitions
    await supabase.rpc('cleanup_old_partitions')
}
```

## Query Performance Optimization

### **Efficient Time-Range Queries**
```sql
-- Good: Uses partition pruning
SELECT * FROM thermal_rates_history
WHERE measured_at >= '2025-01-01'::timestamptz
AND measured_at < '2025-02-01'::timestamptz;

-- Bad: Scans all partitions
SELECT * FROM thermal_rates_history
WHERE EXTRACT(month FROM measured_at) = 1;
```

### **Index Usage**
```sql
-- Composite indexes for common query patterns
CREATE INDEX idx_thermal_rates_user_time
ON thermal_rates_history(anonymous_id, measured_at DESC);

-- Covering indexes to avoid table lookups
CREATE INDEX idx_hvac_cycles_covering
ON hvac_cycles(anonymous_id, start_time)
INCLUDE (duration_minutes, efficiency_rating);
```

### **Query Plan Analysis**
```sql
-- Check query execution plan
EXPLAIN (ANALYZE, BUFFERS)
SELECT AVG(heating_rate)
FROM thermal_rates_history
WHERE anonymous_id = 'user123'
AND measured_at >= CURRENT_DATE - INTERVAL '7 days';
```

## Migration from TimescaleDB

### **Schema Differences**

| TimescaleDB Feature | Native PostgreSQL Equivalent |
|-------------------|------------------------------|
| `create_hypertable()` | Native partitioning with `PARTITION BY RANGE` |
| `time_bucket()` | `DATE_TRUNC()` function |
| Continuous aggregates | Materialized views with concurrent refresh |
| Retention policies | Scheduled partition dropping |
| Compression | PostgreSQL table compression or archival |

### **Performance Comparison**

| Operation | TimescaleDB | Native PostgreSQL |
|-----------|-------------|-------------------|
| **Time-range queries** | Excellent | Excellent (with partitioning) |
| **Aggregations** | Excellent | Very Good (with materialized views) |
| **Inserts** | Excellent | Very Good (with partition pruning) |
| **Space efficiency** | Good (compression) | Good (partition pruning) |
| **Maintenance** | Automatic | Scheduled functions |

### **Migration Steps**

1. **Create New Schema**: Deploy `supabase_native_schema.sql`
2. **Data Migration**:
   ```sql
   INSERT INTO new_daily_reports
   SELECT * FROM old_hypertable_daily_reports;
   ```
3. **Update Edge Functions**: Use new table structures
4. **Test Performance**: Verify query performance meets requirements
5. **Cutover**: Switch applications to new schema

## Monitoring and Observability

### **Partition Health**
```sql
-- Check partition sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE tablename LIKE 'daily_reports_%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### **Query Performance**
```sql
-- Monitor slow queries
SELECT
    query,
    calls,
    total_time,
    mean_time,
    rows
FROM pg_stat_statements
WHERE query LIKE '%thermal_rates_history%'
ORDER BY mean_time DESC;
```

### **Materialized View Freshness**
```sql
-- Check when views were last refreshed
SELECT
    schemaname,
    matviewname,
    ispopulated,
    definition
FROM pg_matviews;
```

## Benefits of Native PostgreSQL Approach

### **Advantages**

1. **Future-Proof**: Based on stable PostgreSQL core features
2. **Simplified Stack**: No external dependencies or extensions
3. **Full Supabase Compatibility**: Works with all Supabase features
4. **Cost Effective**: No additional licensing or complexity costs
5. **Maintenance**: Standard PostgreSQL maintenance procedures
6. **Flexibility**: Easy to modify and extend
7. **Performance**: Excellent performance for most time-series workloads

### **Considerations**

1. **Manual Maintenance**: Requires scheduled maintenance functions
2. **Complex Queries**: Some advanced time-series operations require more SQL
3. **Partition Management**: Manual partition creation and cleanup
4. **Monitoring**: Need to monitor partition health and performance

## Deployment Guide

### **1. Deploy Schema**
```bash
# Apply the native PostgreSQL schema
supabase db reset
supabase db push
```

### **2. Deploy Edge Functions**
```bash
# Deploy all functions including maintenance scheduler
supabase functions deploy
```

### **3. Schedule Maintenance**
```bash
# Set up cron job or scheduled function calls
# Call maintenance-scheduler edge function daily
```

### **4. Monitor Performance**
```bash
# Use database-stats edge function to monitor health
curl -X GET "https://your-project.supabase.co/functions/v1/database-stats"
```

This native PostgreSQL approach provides excellent time-series performance while being future-proof and fully compatible with Supabase's direction.