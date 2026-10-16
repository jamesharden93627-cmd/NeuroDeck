import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { OperationsPerformancePoint } from "../../types/operations";
import type { TimeRange } from "../../types/dashboard";
import { formatCompact } from "../../utils/format";

interface OperationsPerformanceProps {
  points: OperationsPerformancePoint[];
  range: TimeRange;
}

function tickIndexes(length: number): Set<number> {
  const step = Math.max(1, Math.ceil(length / 6));
  return new Set(Array.from({ length }, (_, index) => index).filter(index => index === 0 || index === length - 1 || index % step === 0));
}

/** 功能：生成连续有效样本的折线段；没有耗时的桶保持断开，不伪造零值。 */
function lineSegments(points: OperationsPerformancePoint[], field: "avg_duration_seconds" | "p95_duration_seconds", max: number): string[] {
  const plot = { left: 58, top: 18, width: 516, height: 164 };
  const slot = plot.width / Math.max(1, points.length - 1);
  const segments: string[] = [];
  let current: string[] = [];
  points.forEach((point, index) => {
    const value = point[field];
    if (value == null) {
      if (current.length > 1) segments.push(current.join(" "));
      current = [];
      return;
    }
    const x = plot.left + index * slot;
    const y = plot.top + plot.height * (1 - value / max);
    current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
  });
  if (current.length > 1) segments.push(current.join(" "));
  return segments;
}

/** 功能：展示耗时折线和请求结果柱图，所有点均复用当前筛选与记录水位。 */
export function OperationsPerformance({ points, range }: OperationsPerformanceProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const formatter = useMemo(() => new Intl.DateTimeFormat(locale, range === "24H"
    ? { hour: "2-digit", minute: "2-digit", hour12: false }
    : { month: "2-digit", day: "2-digit" }), [locale, range]);
  const ticks = tickIndexes(points.length);
  const maxDuration = Math.max(1, ...points.flatMap(point => [point.avg_duration_seconds ?? 0, point.p95_duration_seconds ?? 0]));
  const maxRequests = Math.max(1, ...points.map(point => point.requests));
  const hasDuration = points.some(point => point.duration_samples > 0);
  const hasRequests = points.some(point => point.requests > 0);
  const avgSegments = lineSegments(points, "avg_duration_seconds", maxDuration);
  const p95Segments = lineSegments(points, "p95_duration_seconds", maxDuration);
  const requestSlot = 516 / Math.max(1, points.length);
  const barWidth = Math.max(5, Math.min(32, requestSlot * .68));

  return <section className="ops-panel ops-performance-panel">
    <div className="ops-heading"><h2>{t("operations.performance")}</h2><span>{t("operations.performanceNote")}</span></div>
    <div className="ops-performance-grid">
      <figure>
        <figcaption><strong>{t("operations.latencyTrend")}</strong><span><i className="avg" />{t("operations.average")}<i className="p95" />P95</span></figcaption>
        {!hasDuration ? <div className="ops-performance-empty">{t("operations.noDuration")}</div> : <div className="ops-performance-scroll"><svg viewBox="0 0 600 224" role="img" aria-label={t("operations.latencyTrend")}>
          {[0, .5, 1].map(ratio => { const y = 18 + 164 * (1 - ratio); return <g key={ratio}><line x1="58" x2="574" y1={y} y2={y} /><text x="50" y={y + 4}>{(maxDuration * ratio).toFixed(maxDuration < 10 ? 1 : 0)}s</text></g>; })}
          {avgSegments.map((segment, index) => <polyline className="avg-line" points={segment} key={`avg-${index}`} />)}
          {p95Segments.map((segment, index) => <polyline className="p95-line" points={segment} key={`p95-${index}`} />)}
          {points.map((point, index) => {
            const x = 58 + index * (516 / Math.max(1, points.length - 1));
            const label = formatter.format(new Date(point.timestamp));
            return <g key={point.timestamp} tabIndex={point.duration_samples ? 0 : undefined} aria-label={point.duration_samples ? `${label} · ${t("operations.average")} ${point.avg_duration_seconds?.toFixed(2)} ${t("operations.seconds")} · P95 ${point.p95_duration_seconds?.toFixed(2)} ${t("operations.seconds")} · ${t("operations.samples", { count: point.duration_samples })}` : undefined}>
              {point.avg_duration_seconds != null ? <circle className="avg-dot" cx={x} cy={18 + 164 * (1 - point.avg_duration_seconds / maxDuration)} r="3"><title>{label} · {t("operations.average")} {point.avg_duration_seconds.toFixed(2)}s</title></circle> : null}
              {point.p95_duration_seconds != null ? <circle className="p95-dot" cx={x} cy={18 + 164 * (1 - point.p95_duration_seconds / maxDuration)} r="3"><title>{label} · P95 {point.p95_duration_seconds.toFixed(2)}s</title></circle> : null}
              {ticks.has(index) ? <text className="x-label" x={x} y="207">{label}</text> : null}
            </g>;
          })}
        </svg></div>}
      </figure>
      <figure>
        <figcaption><strong>{t("operations.qualityTrend")}</strong><span><i className="success" />{t("operations.successful")}<i className="other" />{t("operations.otherOutcomes")}</span></figcaption>
        {!hasRequests ? <div className="ops-performance-empty">{t("operations.noRequests")}</div> : <div className="ops-performance-scroll"><svg viewBox="0 0 600 224" role="img" aria-label={t("operations.qualityTrend")}>
          {[0, .5, 1].map(ratio => { const y = 18 + 164 * (1 - ratio); return <g key={ratio}><line x1="58" x2="574" y1={y} y2={y} /><text x="50" y={y + 4}>{formatCompact(Math.ceil(maxRequests * ratio))}</text></g>; })}
          {points.map((point, index) => {
            const x = 58 + index * requestSlot + (requestSlot - barWidth) / 2;
            const totalHeight = point.requests / maxRequests * 164;
            const successHeight = point.succeeded / maxRequests * 164;
            const otherHeight = totalHeight - successHeight;
            const label = formatter.format(new Date(point.timestamp));
            const aria = `${label} · ${point.requests} ${t("operations.requests")} · ${point.succeeded} ${t("operations.successful")} · ${point.other_outcomes} ${t("operations.otherOutcomes")} · ${point.success_rate?.toFixed(1) ?? "—"}%`;
            return <g key={point.timestamp} tabIndex={point.requests ? 0 : undefined} aria-label={point.requests ? aria : undefined}>
              <title>{aria}</title>
              <rect className="success-bar" x={x} y={18 + 164 - successHeight} width={barWidth} height={successHeight} rx="1" />
              <rect className="other-bar" x={x} y={18 + 164 - totalHeight} width={barWidth} height={otherHeight} rx="1" />
              {ticks.has(index) ? <text className="x-label" x={x + barWidth / 2} y="207">{label}</text> : null}
            </g>;
          })}
        </svg></div>}
      </figure>
    </div>
  </section>;
}
