export function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: value >= 1_000_000 ? 2 : 1,
  }).format(value);
}

export function formatPercent(used: number, total: number): number {
  return total > 0 ? Math.min(100, Math.max(0, (used / total) * 100)) : 0;
}

/** 功能：按当前界面语言显示运行时长，数值计算保持不变。 */
export function formatDuration(seconds: number, language = "en"): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  if (language.startsWith("zh")) {
    if (days > 0) return `${days}天 ${hours}小时`;
    return `${hours}小时 ${minutes}分`;
  }
  if (days > 0) return `${days}d ${hours}h`;
  return `${hours}h ${minutes}m`;
}

export function formatTime(timestamp: string): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}
