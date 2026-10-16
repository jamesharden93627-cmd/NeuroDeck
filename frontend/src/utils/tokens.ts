import type { ProviderSnapshot, TimeRange, UsageBreakdown } from "../types/dashboard";

/**
 * 功能：返回供应商在所选范围内的 token 合计。
 * 兼容：热升级期间旧后端可能还没有 7D/30D 字段，此时回退到今日值而不让页面崩溃。
 */
export function getRangeTokenTotal(
  provider: ProviderSnapshot,
  range: TimeRange,
): number {
  if (range === "7D") return provider.tokens_7d ?? provider.total_tokens;
  if (range === "30D") return provider.tokens_30d ?? provider.total_tokens;
  return provider.total_tokens;
}

/**
 * 功能：返回所选范围的供应商用量分项。
 * 兼容：旧后端缺少范围分项时，今日仍使用实时快照；长范围只保留可信总量。
 */
export function getRangeUsage(
  provider: ProviderSnapshot,
  range: TimeRange,
): UsageBreakdown {
  const available = provider.range_usage?.[range];
  if (available) return available;
  const isToday = range === "24H";
  return {
    total_tokens: getRangeTokenTotal(provider, range),
    input_tokens: isToday ? provider.input_tokens : 0,
    output_tokens: isToday ? provider.output_tokens : 0,
    cached_tokens: isToday ? provider.cached_tokens : 0,
    reasoning_tokens: isToday ? provider.reasoning_tokens : 0,
    interactions: isToday ? provider.sessions_today : 0,
    exact_completions: isToday ? provider.completed_requests_today ?? 0 : 0,
  };
}
