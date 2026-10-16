import type { OverviewSnapshot, TimeRange, TokenActivityPoint, TokenVolumeBucket, TrendPoint } from "../types/dashboard";
import type { CodexAnalyticsResponse } from "../types/codexAnalytics";

/** 功能：给响应头和 JSON 正文设置统一超时，避免一次挂起请求永久阻止后续轮询。 */
export async function fetchJson<T>(url: string, signal?: AbortSignal, timeoutMs = 10_000): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs);
  const response = await fetch(url, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export async function fetchOverview(signal?: AbortSignal): Promise<OverviewSnapshot> {
  return fetchJson("/api/dashboard/overview", signal);
}

/** 功能：按 UI 选择的时间范围获取 SQLite 聚合趋势。 */
export async function fetchHistory(
  range: TimeRange,
  signal?: AbortSignal,
): Promise<TrendPoint[]> {
  return fetchJson(`/api/analytics/history?range=${encodeURIComponent(range)}`, signal);
}

/** 功能：获取来自 Ollama / Codex 独立事件账本的真实 Token 增量。 */
export async function fetchTokenVolume(
  range: TimeRange,
  signal?: AbortSignal,
): Promise<TokenVolumeBucket[]> {
  return fetchJson(`/api/analytics/token-volume?range=${encodeURIComponent(range)}`, signal);
}

/** 功能：获取由精确事件账本重建的范围累计 Token 曲线。 */
export async function fetchTokenActivity(
  range: TimeRange,
  signal?: AbortSignal,
): Promise<TokenActivityPoint[]> {
  return fetchJson(`/api/analytics/token-activity?range=${encodeURIComponent(range)}`, signal);
}

/** 功能：获取 Codex 匿名账本的模型、工作区和会话分析。 */
export async function fetchCodexAnalytics(
  range: TimeRange,
  signal?: AbortSignal,
): Promise<CodexAnalyticsResponse> {
  return fetchJson(`/api/analytics/codex?range=${encodeURIComponent(range)}`, signal);
}

/** 功能：获取 Antigravity 匿名账本的模型、工作区和会话分析。 */
export async function fetchAntigravityAnalytics(
  range: TimeRange,
  signal?: AbortSignal,
): Promise<CodexAnalyticsResponse> {
  return fetchJson(`/api/analytics/antigravity?range=${encodeURIComponent(range)}`, signal);
}

export function realtimeUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/realtime`;
}
