import type { TimeRange } from "../types/dashboard";

/** 功能：优先采用服务器自然日起点，旧后端/演示模式按浏览器本地日期回退。 */
export function rangeStart(range: TimeRange, endTime: number, serverStart?: string): number {
  const parsed = serverStart ? Date.parse(serverStart) : NaN;
  if (Number.isFinite(parsed)) return parsed;
  const start = new Date(endTime);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - ({ "24H": 1, "7D": 7, "30D": 30 }[range] - 1));
  return start.getTime();
}
