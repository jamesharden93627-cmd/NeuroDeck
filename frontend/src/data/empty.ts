import type { OverviewSnapshot, ProviderSnapshot } from "../types/dashboard";

/** 功能：真实首帧到达前仅保留结构占位，避免演示用量被误认成本机统计。 */
const emptyProvider: ProviderSnapshot = {
  provider: "", online: false, model: "", status: "offline", total_tokens: 0,
  input_tokens: 0, output_tokens: 0, cached_tokens: 0, reasoning_tokens: 0,
  tokens_per_second: 0, last_tokens_per_second: 0, context_used: 0, context_size: 0,
  sessions_today: 0, completed_requests_today: 0, previous_day_tokens: 0, live_output_tokens: 0,
  range_usage: {}, inflight_requests: 0, metric_precision: "unavailable", detail: null,
};

export const emptySnapshot: OverviewSnapshot = {
  timestamp: new Date().toISOString(), mode: "waiting",
  ollama: { ...emptyProvider, provider: "ollama" }, codex: { ...emptyProvider, provider: "codex" },
  antigravity: { ...emptyProvider, provider: "antigravity" },
  hardware: { cpu_usage: 0, cpu_frequency_mhz: 0, ram_used_gb: 0, ram_total_gb: 0,
    gpu_available: false, gpu_name: "", gpu_usage: 0, vram_used_gb: 0, vram_total_gb: 0,
    gpu_temperature_c: null, gpu_power_w: null, gpu_fan_percent: null, uptime_seconds: 0 },
  history: [], recent_signals: [],
};
