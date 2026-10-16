export interface RequestRecord {
  request_id: string;
  timestamp: string;
  model: string;
  endpoint: string;
  status: string;
  http_status: number | null;
  metric_precision: string;
  error_type: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_seconds: number | null;
  tokens_per_second: number | null;
}

export interface OperationsData {
  updated_at: string;
  snapshot_id: number;
  summary: {
    requests: number; succeeded: number; failed: number; cancelled: number;
    incomplete: number; metered: number; input_tokens: number; output_tokens: number;
    success_rate: number | null; avg_duration_seconds: number | null;
    p95_duration_seconds: number | null; duration_samples: number;
  };
  models: Array<{ model: string; requests: number; succeeded: number; tokens: number }>;
  model_options: string[];
  series: Array<{ day: string; requests: number; input_tokens: number; output_tokens: number }>;
  performance_series?: OperationsPerformancePoint[];
  requests: RequestRecord[];
  page: number;
  page_size: number;
  page_count: number;
}

export interface OperationsPerformancePoint {
  timestamp: string;
  requests: number;
  succeeded: number;
  other_outcomes: number;
  success_rate: number | null;
  avg_duration_seconds: number | null;
  p95_duration_seconds: number | null;
  duration_samples: number;
  avg_tokens_per_second: number | null;
  speed_samples: number;
}
