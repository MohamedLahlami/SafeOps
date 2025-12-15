-- PostgreSQL/TimescaleDB Initialization Script
-- Creates tables for time-series metrics and anomaly detection results

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Build metrics table - stores extracted features per build
CREATE TABLE IF NOT EXISTS build_metrics (
    id SERIAL,
    build_id VARCHAR(255) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    branch VARCHAR(255),
    commit_sha VARCHAR(40),
    
    -- Feature vector for Isolation Forest
    duration_seconds FLOAT NOT NULL,           -- Total build duration (T_d)
    log_line_count INTEGER NOT NULL,           -- Log volume (V_l)
    char_density FLOAT,                        -- Average characters per line (D_c)
    error_count INTEGER DEFAULT 0,             -- Error occurrences
    warning_count INTEGER DEFAULT 0,           -- Warning occurrences
    
    -- Event distribution (Bag-of-Events) stored as JSONB
    event_distribution JSONB,
    
    -- Timestamps
    build_started_at TIMESTAMPTZ,
    build_finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (id, created_at)
);

-- Convert to TimescaleDB hypertable for efficient time-series queries
SELECT create_hypertable('build_metrics', 'created_at', if_not_exists => TRUE);

-- Anomaly detection results table
CREATE TABLE IF NOT EXISTS anomaly_results (
    id SERIAL,
    build_metric_id INTEGER NOT NULL,
    build_id VARCHAR(255) NOT NULL,
    
    -- Isolation Forest output
    anomaly_score FLOAT NOT NULL,              -- Raw anomaly score
    is_anomaly BOOLEAN NOT NULL,               -- True if score indicates anomaly
    prediction INTEGER NOT NULL,               -- -1 for anomaly, 1 for normal
    
    -- Explanation for dashboard
    anomaly_reasons JSONB,                     -- Why it was flagged
    
    -- Model metadata
    model_version VARCHAR(50),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (id, created_at)
);

-- Convert to hypertable
SELECT create_hypertable('anomaly_results', 'created_at', if_not_exists => TRUE);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_build_metrics_build_id ON build_metrics (build_id);
CREATE INDEX IF NOT EXISTS idx_build_metrics_repo ON build_metrics (repo_name);
CREATE INDEX IF NOT EXISTS idx_anomaly_results_build_id ON anomaly_results (build_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_results_is_anomaly ON anomaly_results (is_anomaly);

-- View for dashboard: recent builds with anomaly status
CREATE OR REPLACE VIEW recent_builds_status AS
SELECT 
    bm.build_id,
    bm.repo_name,
    bm.branch,
    bm.duration_seconds,
    bm.log_line_count,
    bm.error_count,
    bm.created_at,
    ar.is_anomaly,
    ar.anomaly_score,
    ar.anomaly_reasons
FROM build_metrics bm
LEFT JOIN anomaly_results ar ON bm.build_id = ar.build_id
ORDER BY bm.created_at DESC;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO safeops;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO safeops;
