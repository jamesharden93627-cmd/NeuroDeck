import type { TimeRange, TokenActivityPoint, TokenVolumeBucket } from "../types/dashboard";

export interface TokenVolumeSummary {
  total: number;
  ollama: number;
  codex: number;
  antigravity: number;
  peakIndex: number;
  peakTotal: number;
}

/**
 * 功能：从同一份账本累计曲线反算小时/自然日增量。
 * 这样折线、柱状图和合计共享同一查询水位，活跃写入时不会出现瞬时差额。
 */
export function activityToTokenVolume(
  activity: TokenActivityPoint[],
  range: TimeRange,
): TokenVolumeBucket[] {
  if (activity.length < 2) return [];
  const buckets = new Map<string, TokenVolumeBucket>();

  for (let index = 1; index < activity.length; index += 1) {
    const previous = activity[index - 1];
    const current = activity[index];
    const currentTime = new Date(current.timestamp).getTime();
    if (!Number.isFinite(currentTime)) continue;

    // 边界：整点代表刚结束的前一个区间，减 1ms 后再归入小时或自然日。
    const bucketStart = new Date(currentTime - 1);
    if (range === "24H") {
      bucketStart.setMinutes(0, 0, 0);
    } else {
      bucketStart.setHours(0, 0, 0, 0);
    }
    const key = bucketStart.toISOString();
    const bucket = buckets.get(key) ?? {
      timestamp: key,
      ollama_tokens: 0,
      codex_tokens: 0,
      antigravity_tokens: 0,
    };
    bucket.ollama_tokens += Math.max(0, current.ollama_tokens - previous.ollama_tokens);
    bucket.codex_tokens += Math.max(0, current.codex_tokens - previous.codex_tokens);
    bucket.antigravity_tokens += Math.max(0, (current.antigravity_tokens ?? 0) - (previous.antigravity_tokens ?? 0));
    buckets.set(key, bucket);
  }

  return [...buckets.values()];
}

/** 功能：一次遍历完成柱状图合计和峰值计算，避免组件渲染中重复扫描序列。 */
export function summarizeTokenVolume(buckets: TokenVolumeBucket[]): TokenVolumeSummary {
  let ollama = 0;
  let codex = 0;
  let antigravity = 0;
  let peakIndex = -1;
  let peakTotal = 0;

  buckets.forEach((bucket, index) => {
    ollama += bucket.ollama_tokens;
    codex += bucket.codex_tokens;
    const agTokens = bucket.antigravity_tokens ?? 0;
    antigravity += agTokens;
    const combined = bucket.ollama_tokens + bucket.codex_tokens + agTokens;
    if (combined > peakTotal) {
      peakTotal = combined;
      peakIndex = index;
    }
  });

  return { total: ollama + codex + antigravity, ollama, codex, antigravity, peakIndex, peakTotal };
}

/** 功能：把原始最大值向上取为易读刻度，同时保证全零数据仍有稳定坐标轴。 */
export function niceTokenCeiling(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}
