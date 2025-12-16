/**
 * SafeOps Dashboard - Build Details Modal Component
 */

import { X, AlertTriangle, CheckCircle, TrendingUp, Clock } from "lucide-react";
import { format } from "date-fns";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";
import type { AnomalyResult } from "../api/client";

// Helper to safely parse timestamp (handles RFC 2822 and ISO formats)
function parseTimestamp(timestamp: string): Date {
  const date = new Date(timestamp);
  return isNaN(date.getTime()) ? new Date() : date;
}

interface BuildDetailsModalProps {
  build: AnomalyResult | null;
  onClose: () => void;
}

export function BuildDetailsModal({ build, onClose }: BuildDetailsModalProps) {
  if (!build) return null;

  // Prepare radar chart data from raw features
  const radarData = build.raw_features
    ? Object.entries(build.raw_features)
        .filter(([key]) => typeof build.raw_features![key] === "number")
        .slice(0, 6)
        .map(([key, value]) => ({
          feature: key.replace(/_/g, " "),
          value: Math.min(value as number, 100), // Cap for visualization
          fullMark: 100,
        }))
    : [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>
          <X size={24} />
        </button>

        <div className="modal-header">
          <div className="modal-title">
            <code>{build.build_id}</code>
            {build.is_anomaly ? (
              <span className="badge anomaly large">
                <AlertTriangle size={18} />
                Anomaly Detected
              </span>
            ) : (
              <span className="badge normal large">
                <CheckCircle size={18} />
                Normal Build
              </span>
            )}
          </div>
          <div className="modal-meta">
            <span>
              <Clock size={14} />
              {format(parseTimestamp(build.timestamp), "MMMM d, yyyy HH:mm:ss")}
            </span>
            <span>Model v{build.model_version}</span>
          </div>
        </div>

        <div className="modal-body">
          <div className="detail-grid">
            <div className="detail-card">
              <h4>Anomaly Score</h4>
              <div
                className={`score-display ${
                  build.is_anomaly ? "anomaly" : "normal"
                }`}
              >
                <TrendingUp size={32} />
                <span className="score-value">
                  {build.anomaly_score.toFixed(4)}
                </span>
              </div>
              <p className="score-description">
                {build.anomaly_score < -0.1
                  ? "Strong deviation from normal behavior"
                  : build.anomaly_score < 0
                  ? "Slight deviation detected"
                  : "Within normal parameters"}
              </p>
            </div>

            <div className="detail-card">
              <h4>Confidence Level</h4>
              <div className="confidence-display">
                <div className="confidence-ring">
                  <svg viewBox="0 0 36 36">
                    <path
                      className="confidence-bg"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                    <path
                      className="confidence-fg"
                      strokeDasharray={`${build.confidence * 100}, 100`}
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                  </svg>
                  <span className="confidence-text">
                    {(build.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          {radarData.length > 0 && (
            <div className="feature-radar">
              <h4>Feature Distribution</h4>
              <ResponsiveContainer width="100%" height={250}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#374151" />
                  <PolarAngleAxis
                    dataKey="feature"
                    tick={{ fill: "#9ca3af", fontSize: 11 }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 100]}
                    tick={{ fill: "#9ca3af" }}
                  />
                  <Radar
                    name="Features"
                    dataKey="value"
                    stroke={build.is_anomaly ? "#ef4444" : "#22c55e"}
                    fill={build.is_anomaly ? "#ef4444" : "#22c55e"}
                    fillOpacity={0.4}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="reasons-detail">
            <h4>Detection Analysis</h4>
            {build.anomaly_reasons && build.anomaly_reasons.length > 0 ? (
              <div className="reasons-grid">
                {build.anomaly_reasons.map((reason, idx) => (
                  <div key={idx} className={`reason-card ${reason.severity}`}>
                    <div className="reason-severity">{reason.severity}</div>
                    <div className="reason-content">
                      <p className="reason-text">{reason.reason}</p>
                      {reason.feature && (
                        <div className="reason-metrics">
                          <span>Feature: {reason.feature}</span>
                          <span>Value: {reason.value}</span>
                          {reason.threshold && (
                            <span>Threshold: {reason.threshold}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="no-reasons">
                Build metrics within normal parameters.
              </p>
            )}
          </div>

          {build.top_features && build.top_features.length > 0 && (
            <div className="features-detail">
              <h4>Feature Contributions</h4>
              <div className="features-bars">
                {build.top_features.map((feat, idx) => (
                  <div key={idx} className="feature-bar-item">
                    <div className="feature-bar-header">
                      <span className="feature-name">
                        {feat.feature.replace(/_/g, " ")}
                      </span>
                      <span className={`feature-deviation ${feat.deviation}`}>
                        {feat.deviation === "high" ? "HIGH" : "NORMAL"}
                      </span>
                    </div>
                    <div className="feature-bar">
                      <div
                        className={`feature-bar-fill ${feat.deviation}`}
                        style={{
                          width: `${Math.min(feat.z_score * 20, 100)}%`,
                        }}
                      />
                    </div>
                    <div className="feature-bar-stats">
                      <span>Value: {feat.value.toFixed(2)}</span>
                      <span>Z-Score: {feat.z_score}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
