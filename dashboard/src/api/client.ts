/**
 * SafeOps Dashboard - API Client
 * Connects to AnomalyDetector service
 */

import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:3002";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Types
export interface AnomalyResult {
  id: number;
  build_id: string;
  timestamp: string;
  is_anomaly: boolean;
  anomaly_score: number;
  prediction: number;
  confidence: number;
  anomaly_reasons: AnomalyReason[];
  top_features: FeatureContribution[];
  model_version: string;
  raw_features: Record<string, number> | null;
}

export interface AnomalyReason {
  feature?: string;
  value?: number;
  threshold?: number;
  reason: string;
  severity: "info" | "warning" | "critical";
}

export interface FeatureContribution {
  feature: string;
  value: number;
  z_score: number;
  deviation: "normal" | "high";
}

export interface AnomalyStats {
  period_hours: number;
  total_builds: number;
  total_anomalies: number;
  anomaly_rate: number;
  avg_score: number;
  min_score: number;
  max_score: number;
  avg_confidence: number;
}

export interface TimeSeriesData {
  time: string;
  total_builds: number;
  anomalies: number;
  avg_score: number;
}

export interface HealthStatus {
  status: string;
  service: string;
  model_loaded: boolean;
  version: string;
}

export interface ModelInfo {
  is_trained: boolean;
  model_version: string;
  feature_names: string[];
  config: {
    n_estimators: number;
    contamination: number;
  };
  training_stats: {
    n_samples: number;
    n_features: number;
    n_anomalies_detected: number;
    anomaly_ratio: number;
  };
}

export interface PredictRequest {
  build_id: string;
  features: Record<string, number>;
  save?: boolean;
}

export interface PredictResponse {
  build_id: string;
  is_anomaly: boolean;
  anomaly_score: number;
  prediction: number;
  confidence: number;
  anomaly_reasons: AnomalyReason[];
  top_contributing_features: FeatureContribution[];
  model_version: string;
  processed_at: string;
}

// API Functions
export const api = {
  // Health & Status
  async getHealth(): Promise<HealthStatus> {
    const { data } = await client.get<HealthStatus>("/health");
    return data;
  },

  async getModelInfo(): Promise<ModelInfo> {
    const { data } = await client.get<ModelInfo>("/model/info");
    return data;
  },

  // Results
  async getResults(params?: {
    limit?: number;
    anomalies_only?: boolean;
  }): Promise<{ count: number; results: AnomalyResult[] }> {
    const { data } = await client.get("/results", { params });
    return data;
  },

  async getResultByBuildId(buildId: string): Promise<AnomalyResult> {
    const { data } = await client.get<AnomalyResult>(`/results/${buildId}`);
    return data;
  },

  // Statistics
  async getStats(hours?: number): Promise<AnomalyStats> {
    const { data } = await client.get<AnomalyStats>("/stats", {
      params: { hours },
    });
    return data;
  },

  async getTimeSeries(params?: {
    hours?: number;
    interval?: string;
  }): Promise<TimeSeriesData[]> {
    const { data } = await client.get<TimeSeriesData[]>("/timeseries", {
      params,
    });
    return data;
  },

  // Predictions
  async predict(request: PredictRequest): Promise<PredictResponse> {
    const { data } = await client.post<PredictResponse>("/predict", request);
    return data;
  },

  // Model Management
  async trainModel(
    csvPath?: string
  ): Promise<{ status: string; training_stats: Record<string, number> }> {
    const { data } = await client.post("/model/train", { csv_path: csvPath });
    return data;
  },

  // Queue Management
  async getQueueInfo(): Promise<{
    queue: string;
    messages: number;
    consumers: number;
    processed_total: number;
    anomalies_detected: number;
  }> {
    const { data } = await client.get("/queue/info");
    return data;
  },

  async processQueue(count?: number | "all"): Promise<{
    processed: number;
    queue_status: Record<string, number>;
  }> {
    const { data } = await client.post("/queue/process", { count });
    return data;
  },
};

export default api;
