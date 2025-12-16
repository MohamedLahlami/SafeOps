/**
 * SafeOps Dashboard - Service Status Component
 */

import { RefreshCw, Server, Database, Cpu } from "lucide-react";
import type { HealthStatus, ModelInfo } from "../api/client";

interface ServiceStatusProps {
  health: HealthStatus | null;
  modelInfo: ModelInfo | null;
  queueInfo: {
    messages: number;
    processed_total: number;
    anomalies_detected: number;
  } | null;
  onRefresh: () => void;
  loading: boolean;
}

export function ServiceStatus({
  health,
  modelInfo,
  queueInfo,
  onRefresh,
  loading,
}: ServiceStatusProps) {
  const isHealthy = health?.status === "healthy" && health?.model_loaded;

  return (
    <div className="service-status">
      <div className="status-header">
        <h3>Service Status</h3>
        <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spinning" : ""} />
        </button>
      </div>

      <div className="status-items">
        <div className={`status-item ${isHealthy ? "healthy" : "unhealthy"}`}>
          <Server size={18} />
          <span className="status-label">API Service</span>
          <span className={`status-badge ${health ? "online" : "offline"}`}>
            {health ? "Online" : "Offline"}
          </span>
        </div>

        <div
          className={`status-item ${
            modelInfo?.is_trained ? "healthy" : "warning"
          }`}
        >
          <Cpu size={18} />
          <span className="status-label">ML Model</span>
          <span
            className={`status-badge ${
              modelInfo?.is_trained ? "ready" : "not-ready"
            }`}
          >
            {modelInfo?.is_trained
              ? `v${modelInfo.model_version}`
              : "Not Trained"}
          </span>
        </div>

        <div className="status-item">
          <Database size={18} />
          <span className="status-label">Queue</span>
          <span className="status-badge queue">
            {queueInfo ? `${queueInfo.messages} pending` : "N/A"}
          </span>
        </div>
      </div>

      {modelInfo && (
        <div className="model-stats">
          <div className="model-stat">
            <span className="stat-label">Training Samples</span>
            <span className="stat-value">
              {modelInfo.training_stats.n_samples || 0}
            </span>
          </div>
          <div className="model-stat">
            <span className="stat-label">Features</span>
            <span className="stat-value">
              {modelInfo.training_stats.n_features || 0}
            </span>
          </div>
          <div className="model-stat">
            <span className="stat-label">Contamination</span>
            <span className="stat-value">
              {(modelInfo.config.contamination * 100).toFixed(0)}%
            </span>
          </div>
          <div className="model-stat">
            <span className="stat-label">Estimators</span>
            <span className="stat-value">{modelInfo.config.n_estimators}</span>
          </div>
        </div>
      )}

      {queueInfo && (
        <div className="queue-stats">
          <div className="queue-stat">
            <span className="stat-label">Total Processed</span>
            <span className="stat-value">{queueInfo.processed_total}</span>
          </div>
          <div className="queue-stat">
            <span className="stat-label">Anomalies Found</span>
            <span className="stat-value anomaly">
              {queueInfo.anomalies_detected}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
