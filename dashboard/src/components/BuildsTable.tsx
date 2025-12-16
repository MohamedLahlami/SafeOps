/**
 * SafeOps Dashboard - Builds Table Component
 */

import { useState } from "react";
import { format } from "date-fns";
import {
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";
import type { AnomalyResult } from "../api/client";

// Helper to safely parse timestamp (handles RFC 2822 and ISO formats)
function parseTimestamp(timestamp: string): Date {
  const date = new Date(timestamp);
  return isNaN(date.getTime()) ? new Date() : date;
}

interface BuildsTableProps {
  builds: AnomalyResult[];
  loading: boolean;
  onSelectBuild: (build: AnomalyResult) => void;
}

export function BuildsTable({
  builds,
  loading,
  onSelectBuild,
}: BuildsTableProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (loading) {
    return (
      <div className="builds-table-container">
        <h3>Recent Builds</h3>
        <div className="table-skeleton">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="row-skeleton" />
          ))}
        </div>
      </div>
    );
  }

  if (builds.length === 0) {
    return (
      <div className="builds-table-container">
        <h3>Recent Builds</h3>
        <div className="table-empty">
          <p>No builds processed yet. Send webhook events to see results.</p>
        </div>
      </div>
    );
  }

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="builds-table-container">
      <h3>Recent Builds</h3>
      <table className="builds-table">
        <thead>
          <tr>
            <th>Build ID</th>
            <th>Timestamp</th>
            <th>Status</th>
            <th>Score</th>
            <th>Confidence</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {builds.map((build) => (
            <>
              <tr
                key={build.id}
                className={`build-row ${
                  build.is_anomaly ? "anomaly" : "normal"
                }`}
                onClick={() => onSelectBuild(build)}
              >
                <td className="build-id">
                  <code>{build.build_id}</code>
                </td>
                <td className="timestamp">
                  {format(parseTimestamp(build.timestamp), "MMM d, yyyy HH:mm:ss")}
                </td>
                <td className="status">
                  {build.is_anomaly ? (
                    <span className="badge anomaly">
                      <AlertTriangle size={14} />
                      Anomaly
                    </span>
                  ) : (
                    <span className="badge normal">
                      <CheckCircle size={14} />
                      Normal
                    </span>
                  )}
                </td>
                <td className="score">
                  <span
                    className={`score-value ${
                      build.anomaly_score < -0.1 ? "negative" : ""
                    }`}
                  >
                    {build.anomaly_score.toFixed(4)}
                  </span>
                </td>
                <td className="confidence">
                  <div className="confidence-bar">
                    <div
                      className="confidence-fill"
                      style={{ width: `${build.confidence * 100}%` }}
                    />
                    <span>{(build.confidence * 100).toFixed(0)}%</span>
                  </div>
                </td>
                <td className="expand">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand(build.id);
                    }}
                  >
                    {expandedId === build.id ? (
                      <ChevronUp size={18} />
                    ) : (
                      <ChevronDown size={18} />
                    )}
                  </button>
                </td>
              </tr>
              {expandedId === build.id && (
                <tr className="expanded-row">
                  <td colSpan={6}>
                    <div className="expanded-content">
                      <div className="reasons-section">
                        <h4>Detection Reasons</h4>
                        {build.anomaly_reasons &&
                        build.anomaly_reasons.length > 0 ? (
                          <ul className="reasons-list">
                            {build.anomaly_reasons.map((reason, idx) => (
                              <li
                                key={idx}
                                className={`reason ${reason.severity}`}
                              >
                                <span className="reason-text">
                                  {reason.reason}
                                </span>
                                {reason.feature && (
                                  <span className="reason-detail">
                                    {reason.feature}: {reason.value} (threshold:{" "}
                                    {reason.threshold})
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="no-reasons">
                            No specific reasons identified
                          </p>
                        )}
                      </div>
                      <div className="features-section">
                        <h4>Top Contributing Features</h4>
                        {build.top_features && build.top_features.length > 0 ? (
                          <ul className="features-list">
                            {build.top_features.map((feat, idx) => (
                              <li
                                key={idx}
                                className={`feature ${feat.deviation}`}
                              >
                                <span className="feature-name">
                                  {feat.feature}
                                </span>
                                <span className="feature-value">
                                  {feat.value.toFixed(2)}
                                </span>
                                <span className="feature-zscore">
                                  z-score: {feat.z_score}
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="no-features">
                            No feature data available
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
