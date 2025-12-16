/**
 * SafeOps Dashboard - Main Application
 */

import { useState, useEffect, useCallback } from "react";
import {
  StatsCards,
  TimeSeriesChart,
  BuildsTable,
  BuildDetailsModal,
  ServiceStatus,
} from "./components";
import api from "./api/client";
import type {
  AnomalyStats,
  TimeSeriesData,
  AnomalyResult,
  HealthStatus,
  ModelInfo,
} from "./api/client";
import { Shield, RefreshCw, AlertCircle } from "lucide-react";
import "./App.css";

function App() {
  // State
  const [stats, setStats] = useState<AnomalyStats | null>(null);
  const [timeSeries, setTimeSeries] = useState<TimeSeriesData[]>([]);
  const [builds, setBuilds] = useState<AnomalyResult[]>([]);
  const [selectedBuild, setSelectedBuild] = useState<AnomalyResult | null>(
    null
  );
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [queueInfo, setQueueInfo] = useState<{
    messages: number;
    processed_total: number;
    anomalies_detected: number;
  } | null>(null);

  // Loading states
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Filter state
  const [showAnomaliesOnly, setShowAnomaliesOnly] = useState(false);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      setError(null);

      const [
        healthRes,
        statsRes,
        timeSeriesRes,
        buildsRes,
        modelRes,
        queueRes,
      ] = await Promise.allSettled([
        api.getHealth(),
        api.getStats(24),
        api.getTimeSeries({ hours: 24, interval: "1 hour" }),
        api.getResults({ limit: 50, anomalies_only: showAnomaliesOnly }),
        api.getModelInfo(),
        api.getQueueInfo(),
      ]);

      if (healthRes.status === "fulfilled") setHealth(healthRes.value);
      if (statsRes.status === "fulfilled") setStats(statsRes.value);
      if (timeSeriesRes.status === "fulfilled")
        setTimeSeries(timeSeriesRes.value);
      if (buildsRes.status === "fulfilled") setBuilds(buildsRes.value.results);
      if (modelRes.status === "fulfilled") setModelInfo(modelRes.value);
      if (queueRes.status === "fulfilled") setQueueInfo(queueRes.value);

      // Check if API is reachable
      if (healthRes.status === "rejected") {
        setError(
          "Unable to connect to AnomalyDetector service. Make sure it is running on port 3002."
        );
      }
    } catch (err) {
      setError(
        "Failed to fetch data. Check if the backend service is running."
      );
      console.error("Fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [showAnomaliesOnly]);

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchData();

    if (autoRefresh) {
      const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [fetchData, autoRefresh]);

  // Manual refresh
  const handleRefresh = () => {
    setLoading(true);
    fetchData();
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <Shield className="logo" size={32} />
          <div className="header-title">
            <h1>SafeOps LogMiner</h1>
            <span className="subtitle">CI/CD Pipeline Anomaly Detection</span>
          </div>
        </div>
        <div className="header-right">
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-refresh</span>
          </label>
          <button
            className="refresh-btn primary"
            onClick={handleRefresh}
            disabled={loading}
          >
            <RefreshCw size={18} className={loading ? "spinning" : ""} />
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          <span>{error}</span>
          <button onClick={handleRefresh}>Retry</button>
        </div>
      )}

      <main className="app-main">
        <div className="main-content">
          <StatsCards stats={stats} loading={loading} />

          <TimeSeriesChart data={timeSeries} loading={loading} />

          <div className="builds-section">
            <div className="builds-header">
              <h3>Recent Builds</h3>
              <label className="filter-toggle">
                <input
                  type="checkbox"
                  checked={showAnomaliesOnly}
                  onChange={(e) => setShowAnomaliesOnly(e.target.checked)}
                />
                <span>Show anomalies only</span>
              </label>
            </div>
            <BuildsTable
              builds={builds}
              loading={loading}
              onSelectBuild={setSelectedBuild}
            />
          </div>
        </div>

        <aside className="sidebar">
          <ServiceStatus
            health={health}
            modelInfo={modelInfo}
            queueInfo={queueInfo}
            onRefresh={handleRefresh}
            loading={loading}
          />
        </aside>
      </main>

      <BuildDetailsModal
        build={selectedBuild}
        onClose={() => setSelectedBuild(null)}
      />

      <footer className="app-footer">
        <span>SafeOps LogMiner v1.0.0</span>
        <span>•</span>
        <span>Isolation Forest ML Detection</span>
        <span>•</span>
        <span>DevSecOps Pipeline Security</span>
      </footer>
    </div>
  );
}

export default App;
