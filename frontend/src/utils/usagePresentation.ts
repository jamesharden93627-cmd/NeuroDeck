import type { TokenActivityPoint } from "../types/dashboard";

/** 功能：保留接口边界原有日期和 UTC 偏移，避免浏览器时区把“今日”转换成另一天。 */
export function formatAccountingBoundary(value: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::[\d.]+)?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return "—";
  return `${match[1]} ${match[2]} UTC${match[3] === "Z" ? "+00:00" : match[3]}`;
}

/** 功能：图表数字来自当前曲线的最后一点；加载失败或无点时保持未知，不能混入另一帧 KPI。 */
export function recordedTokenTotals(activity: TokenActivityPoint[]) {
  const latest = activity.at(-1);
  return latest ? { ollama: latest.ollama_tokens, codex: latest.codex_tokens, antigravity: latest.antigravity_tokens ?? 0 } : null;
}
