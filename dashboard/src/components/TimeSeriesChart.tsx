/**
 * SafeOps Dashboard - Time Series Chart Component
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { format } from "date-fns";
import type { TimeSeriesData } from "../api/client";

// Helper to safely parse timestamp (handles RFC 2822 and ISO formats)
function parseTimestamp(timestamp: string): Date {
  const date = new Date(timestamp);
  return isNaN(date.getTime()) ? new Date() : date;
}

interface TimeSeriesChartProps {
  data: TimeSeriesData[];
  loading: boolean;
}

export function TimeSeriesChart({ data, loading }: TimeSeriesChartProps) {
  if (loading) {
    return (
      <div className="chart-container">
        <h3>Build Activity Over Time</h3>
        <div className="chart-skeleton" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="chart-container">
        <h3>Build Activity Over Time</h3>
        <div className="chart-empty">
          <p>
            No data available yet. Process some builds to see activity trends.
          </p>
        </div>
      </div>
    );
  }

  const formattedData = data.map((item) => ({
    ...item,
    time: format(parseTimestamp(item.time), "MMM d, HH:mm"),
    normalBuilds: item.total_builds - item.anomalies,
  }));

  return (
    <div className="chart-container">
      <h3>Build Activity Over Time</h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart
          data={formattedData}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorNormal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0.1} />
            </linearGradient>
            <linearGradient id="colorAnomalies" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="time"
            stroke="#9ca3af"
            fontSize={12}
            tickLine={false}
          />
          <YAxis stroke="#9ca3af" fontSize={12} tickLine={false} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              borderRadius: "8px",
            }}
            labelStyle={{ color: "#f3f4f6" }}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="normalBuilds"
            name="Normal Builds"
            stackId="1"
            stroke="#22c55e"
            fill="url(#colorNormal)"
          />
          <Area
            type="monotone"
            dataKey="anomalies"
            name="Anomalies"
            stackId="1"
            stroke="#ef4444"
            fill="url(#colorAnomalies)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
