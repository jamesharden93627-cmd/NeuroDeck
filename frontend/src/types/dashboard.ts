export interface ProviderSnapshot {
  provider: "ollama" | "codex" | string;
  online: boolean;
  model: string;
  status: "active" | "idle" | "offline" | "error" | string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  tokens_per_second: number;
  last_tokens_per_second: number;
  context_used: number;
  context_size: number;
  sessions_today: number;
  completed_requests_today?: number;
  previous_day_tokens: number;
  tokens_7d?: number;
  tokens_30d?: number;
  range_usage?: Partial<Record<TimeRange, UsageBreakdown>>;
  live_output_tokens: number;
  inflight_requests: number;
  metric_precision: "exact" | "estimated" | string;
  detail: string | null;
}

export interface HardwareSnapshot {
  cpu_usage: number;
  cpu_frequency_mhz: number;
  ram_used_gb: number;
  ram_total_gb: number;
  gpu_available: boolean;
  gpu_name: string;
  gpu_usage: number;
  vram_used_gb: number;
  vram_total_gb: number;
  gpu_temperature_c: number | null;
  gpu_power_w: number | null;
  gpu_fan_percent: number | null;
  uptime_seconds: number;
}

export interface TrendPoint {
  timestamp: string;
  ollama_tokens: number;
  codex_tokens: number;
  antigravity_tokens: number;
  ollama_tokens_per_second: number;
  cpu_usage: number;
  gpu_usage: number;
  gpu_temperature_c?: number | null;
  ram_usage: number;
  vram_usage: number;
}

export interface TokenVolumeBucket {
  timestamp: string;
  ollama_tokens: number;
  codex_tokens: number;
  antigravity_tokens: number;
}

export interface TokenActivityPoint {
  timestamp: string;
  ollama_tokens: number;
  codex_tokens: number;
  antigravity_tokens: number;
}

export interface SignalEvent {
  timestamp: string;
  source: string;
  event: string;
  detail: string;
  severity: "ok" | "warn" | "error" | string;
}

export interface OverviewSnapshot {
  timestamp: string;
  range_starts?: Partial<Record<TimeRange, string>>;
  mode: "live" | "demo" | string;
  ollama: ProviderSnapshot;
  codex: ProviderSnapshot;
  antigravity: ProviderSnapshot;
  codex_accounting?: Partial<Record<TimeRange, AccountingSummary>>;
  antigravity_accounting?: Partial<Record<TimeRange, AccountingSummary>>;
  hardware: HardwareSnapshot;
  history: TrendPoint[];
  recent_signals: SignalEvent[];
}

export interface RealtimeUpdate {
  type: "realtime_update";
  range_starts?: Partial<Record<TimeRange, string>>;
  timestamp: string;
  mode: "live" | "demo" | string;
  ollama: ProviderSnapshot;
  codex: ProviderSnapshot;
  antigravity: ProviderSnapshot;
  codex_accounting?: Partial<Record<TimeRange, AccountingSummary>>;
  antigravity_accounting?: Partial<Record<TimeRange, AccountingSummary>>;
  hardware: HardwareSnapshot;
  history_point: TrendPoint | null;
  history: [];
  recent_signals: SignalEvent[];
}

export type ConnectionState = "connecting" | "live" | "demo" | "offline";
export interface AccountingSummary { raw_tokens: number; accepted_tokens: number; duplicate_tokens: number; duplicate_events: number }
export interface UsageBreakdown {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  interactions: number;
  exact_completions: number;
}
export type TimeRange = "24H" | "7D" | "30D";
export type DashboardView = "overview" | "ollama" | "codex" | "antigravity" | "hardware" | "operations";

