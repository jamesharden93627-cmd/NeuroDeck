import type { TimeRange } from "./dashboard";

export interface CodexLedgerUsage {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  completions: number;
  sessions: number;
}

export interface CodexAnalyticsSummary extends CodexLedgerUsage {
  models: number;
  workspaces: number;
  cache_ratio: number;
}

export interface CodexModelUsage extends CodexLedgerUsage {
  model: string;
  share_percent: number;
}

export interface CodexWorkspaceUsage extends CodexLedgerUsage {
  workspace_id: string;
  workspace: string;
  last_active: string;
  share_percent: number;
}

export interface CodexSessionUsage extends CodexLedgerUsage {
  session_id: string;
  session: string;
  model: string;
  workspace_id: string;
  workspace: string;
  last_active: string;
  share_percent: number;
}

export interface CodexDailyUsage extends CodexLedgerUsage {
  day: string;
}

export interface CodexAnalyticsResponse {
  provider: "codex";
  range: TimeRange;
  start: string;
  updated_at: string;
  snapshot_id: number;
  summary: CodexAnalyticsSummary;
  models: CodexModelUsage[];
  workspaces: CodexWorkspaceUsage[];
  sessions: CodexSessionUsage[];
  daily: CodexDailyUsage[];
  local_start?: string;
  local_end?: string;
  period_comparison?: CodexPeriodUsage[];
  baseline_comparison?: CodexBaselineComparison;
  timeline?: CodexTimelineUsage[];
  activity_heatmap?: CodexActivityHeatmapCell[];
}

/** 功能：不同范围共用的今日环比基线，所有值均来自同一账本水位。 */
export interface CodexBaselineComparison {
  today_tokens: number;
  yesterday_tokens: number;
  average_7d_tokens: number;
  average_30d_tokens: number;
}

export interface CodexTimelineUsage extends CodexLedgerUsage {
  timestamp: string;
}

export interface CodexActivityHeatmapCell {
  weekday: number;
  hour: number;
  total_tokens: number;
  events: number;
}

/** 功能：同一账本水位的时间口径对比，边界保留服务器时区偏移。 */
export interface CodexPeriodUsage {
  period: "local_today" | "utc_today" | "rolling_24h";
  start: string;
  end: string;
  total_tokens: number;
  /** Codex 会话累计快照之和，仅用于与桌面 Token 活动面板对账。 */
  activity_tokens?: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  events: number;
  sessions: number;
  activity_events?: number;
}
