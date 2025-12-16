/**
 * SafeOps Dashboard - Stats Cards Component
 */

import { AlertTriangle, CheckCircle, Activity, TrendingUp } from "lucide-react";
import type { AnomalyStats } from "../api/client";

interface StatsCardsProps {
  stats: AnomalyStats | null;
  loading: boolean;
}

export function StatsCards({ stats, loading }: StatsCardsProps) {
  if (loading || !stats) {
    return (
      <div className="stats-grid">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="stat-card loading">
            <div className="stat-skeleton" />
          </div>
        ))}
      </div>
    );
  }

  const anomalyRate = (stats.anomaly_rate * 100).toFixed(1);

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <div className="stat-icon builds">
          <Activity size={24} />
        </div>
        <div className="stat-content">
          <span className="stat-value">{stats.total_builds}</span>
          <span className="stat-label">Total Builds</span>
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-icon anomalies">
          <AlertTriangle size={24} />
        </div>
        <div className="stat-content">
          <span className="stat-value">{stats.total_anomalies}</span>
          <span className="stat-label">Anomalies Detected</span>
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-icon rate">
          <TrendingUp size={24} />
        </div>
        <div className="stat-content">
          <span className="stat-value">{anomalyRate}%</span>
          <span className="stat-label">Anomaly Rate</span>
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-icon confidence">
          <CheckCircle size={24} />
        </div>
        <div className="stat-content">
          <span className="stat-value">
            {(stats.avg_confidence * 100).toFixed(0)}%
          </span>
          <span className="stat-label">Avg Confidence</span>
        </div>
      </div>
    </div>
  );
}
