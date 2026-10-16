import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type {
  CodexActivityHeatmapCell,
  CodexAnalyticsResponse,
  CodexTimelineUsage,
} from "../../types/codexAnalytics";
import { formatCompact } from "../../utils/format";

interface CodexInsightsProps {
  data: CodexAnalyticsResponse;
}

interface CompositionPart {
  key: "uncached" | "cached" | "visible" | "reasoning";
  label: string;
  color: string;
  value: number;
}

/** 处理：缓存属于输入、推理属于输出，先扣除父项再堆叠，避免图表重复计算。 */
function compositionParts(item: CodexTimelineUsage, labels: Record<CompositionPart["key"], string>): CompositionPart[] {
  const cached = Math.min(item.cached_tokens, item.input_tokens);
  const reasoning = Math.min(item.reasoning_tokens, item.output_tokens);
  return [
    { key: "uncached", label: labels.uncached, color: "#4f8cff", value: Math.max(0, item.input_tokens - cached) },
    { key: "cached", label: labels.cached, color: "#22d3a7", value: cached },
    { key: "visible", label: labels.visible, color: "#f6b84a", value: Math.max(0, item.output_tokens - reasoning) },
    { key: "reasoning", label: labels.reasoning, color: "#a78bfa", value: reasoning },
  ];
}

function deltaPercent(current: number, baseline: number): number | null {
  return baseline > 0 ? (current - baseline) / baseline * 100 : null;
}

/** 功能：显示今日值及其相对昨日、7 日均值和 30 日均值的变化。 */
function BaselineComparison({ data }: CodexInsightsProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const baseline = data.baseline_comparison;
  if (!baseline) return null;
  const cards = [
    { key: "today", label: t("codexInsights.today"), value: baseline.today_tokens, delta: null },
    { key: "yesterday", label: t("codexInsights.yesterday"), value: baseline.yesterday_tokens, delta: deltaPercent(baseline.today_tokens, baseline.yesterday_tokens) },
    { key: "average7d", label: t("codexInsights.average7d"), value: baseline.average_7d_tokens, delta: deltaPercent(baseline.today_tokens, baseline.average_7d_tokens) },
    { key: "average30d", label: t("codexInsights.average30d"), value: baseline.average_30d_tokens, delta: deltaPercent(baseline.today_tokens, baseline.average_30d_tokens) },
  ];
  return (
    <section className="codex-insight-section" aria-labelledby="codex-comparison-title">
      <header className="codex-insight-heading">
        <div><span className="eyeline">COMPARE / 01</span><h3 id="codex-comparison-title">{t("codexInsights.comparisonTitle")}</h3></div>
        <p>{t("codexInsights.comparisonDescription")}</p>
      </header>
      <div className="codex-baseline-grid">
        {cards.map((card) => (
          <article className={`codex-baseline-card${card.key === "today" ? " is-current" : ""}`} key={card.key}>
            <span>{card.label}</span>
            <strong title={card.value.toLocaleString(locale)}>{formatCompact(card.value)}</strong>
            {card.key === "today" ? <small>{t("codexInsights.localCalendarDay")}</small> : card.delta === null ? (
              <small>{t("codexInsights.noBaseline")}</small>
            ) : (
              <small className={card.delta >= 0 ? "is-up" : "is-down"}>
                {card.delta >= 0 ? "↑" : "↓"} {Math.abs(card.delta).toFixed(0)}% · {t("codexInsights.todayVsBaseline")}
              </small>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

/** 功能：绘制按小时/自然日分桶的 Token 构成堆叠图。 */
function CompositionChart({ data }: CodexInsightsProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const timeline = useMemo(() => data.timeline ?? [], [data.timeline]);
  const labels = {
    uncached: t("codexInsights.uncachedInput"),
    cached: t("codexInsights.cachedInput"),
    visible: t("codexInsights.visibleOutput"),
    reasoning: t("codexInsights.reasoning"),
  };
  const chart = useMemo(() => {
    const plot = { left: 64, top: 14, width: 912, height: 206 };
    const max = Math.max(1, ...timeline.map(item => item.total_tokens));
    const slot = plot.width / Math.max(1, timeline.length);
    const barWidth = Math.max(4, Math.min(30, slot * 0.72));
    return { plot, max, slot, barWidth };
  }, [timeline]);
  const hasData = timeline.some(item => item.total_tokens > 0);
  const timeFormatter = useMemo(() => new Intl.DateTimeFormat(locale, data.range === "24H"
    ? { hour: "2-digit", minute: "2-digit", hour12: false }
    : { month: "2-digit", day: "2-digit" }), [data.range, locale]);
  const tickIndexes = new Set(timeline.map((_, index) => index).filter(index => (
    index === 0 || index === timeline.length - 1 || index % Math.max(1, Math.ceil(timeline.length / 6)) === 0
  )));

  return (
    <section className="codex-insight-section" aria-labelledby="codex-composition-title">
      <header className="codex-insight-heading">
        <div><span className="eyeline">COMPOSITION / 02</span><h3 id="codex-composition-title">{t("codexInsights.compositionTitle")}</h3></div>
        <p>{t("codexInsights.compositionDescription")}</p>
      </header>
      <div className="codex-chart-legend" aria-label={t("codexInsights.compositionTitle")}>
        {compositionParts({ input_tokens: 0, cached_tokens: 0, output_tokens: 0, reasoning_tokens: 0, total_tokens: 0, completions: 0, sessions: 0, timestamp: "" }, labels).map(part => (
          <span key={part.key}><i style={{ background: part.color }} />{part.label}</span>
        ))}
      </div>
      {!hasData ? <div className="codex-insight-empty">{t("codexInsights.noTimeline")}</div> : (
        <div className="codex-svg-scroll">
          <svg className="codex-composition-chart" viewBox="0 0 1000 270" role="img" aria-label={t("codexInsights.compositionTitle")}>
            {[0, 0.33, 0.66, 1].map(ratio => {
              const y = chart.plot.top + chart.plot.height * (1 - ratio);
              return <g key={ratio}><line x1={chart.plot.left} x2={chart.plot.left + chart.plot.width} y1={y} y2={y} /><text x={chart.plot.left - 10} y={y + 4}>{formatCompact(chart.max * ratio)}</text></g>;
            })}
            {timeline.map((item, index) => {
              const x = chart.plot.left + chart.slot * index + (chart.slot - chart.barWidth) / 2;
              let cumulative = 0;
              const parts = compositionParts(item, labels);
              const detail = `${timeFormatter.format(new Date(item.timestamp))} · ${t("codexInsights.bucketTotal")} ${item.total_tokens.toLocaleString(locale)} Token · ${parts.map(part => `${part.label} ${part.value.toLocaleString(locale)}`).join(" · ")}`;
              return <g key={item.timestamp} tabIndex={0} aria-label={detail}>
                <title>{detail}</title>
                {parts.map(part => {
                  cumulative += part.value;
                  const height = part.value / chart.max * chart.plot.height;
                  const y = chart.plot.top + chart.plot.height - cumulative / chart.max * chart.plot.height;
                  return <rect key={part.key} x={x} y={y} width={chart.barWidth} height={height} rx="1.5" style={{ fill: part.color }} />;
                })}
                {tickIndexes.has(index) ? <text className="x-label" x={x + chart.barWidth / 2} y="248">{timeFormatter.format(new Date(item.timestamp))}</text> : null}
              </g>;
            })}
          </svg>
        </div>
      )}
    </section>
  );
}

/** 功能：将近 30 日活动汇总为固定 7×24 热力矩阵。 */
function ActivityHeatmap({ data }: CodexInsightsProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const cells = data.activity_heatmap ?? [];
  const max = Math.max(0, ...cells.map(cell => cell.total_tokens));
  const weekdays = Array.from({ length: 7 }, (_, index) => t(`codexInsights.weekdays.${index}`));
  const byPosition = new Map(cells.map(cell => [`${cell.weekday}-${cell.hour}`, cell]));
  const cellWidth = 34;
  const cellHeight = 23;
  const left = 74;
  const top = 20;
  const labelFor = (cell: CodexActivityHeatmapCell) => t("codexInsights.heatmapCell", {
    day: weekdays[cell.weekday],
    hour: String(cell.hour).padStart(2, "0"),
    tokens: cell.total_tokens.toLocaleString(locale),
    events: cell.events,
  });
  return (
    <section className="codex-insight-section" aria-labelledby="codex-heatmap-title">
      <header className="codex-insight-heading">
        <div><span className="eyeline">ACTIVITY / 03</span><h3 id="codex-heatmap-title">{t("codexInsights.heatmapTitle")}</h3></div>
        <p>{t("codexInsights.heatmapDescription")}</p>
      </header>
      <div className="codex-svg-scroll">
        <svg className="codex-heatmap" viewBox="0 0 1000 230" role="img" aria-label={t("codexInsights.heatmapTitle")}>
          {weekdays.map((day, weekday) => <text key={day} x={left - 12} y={top + weekday * cellHeight + 15}>{day}</text>)}
          {Array.from({ length: 24 }, (_, hour) => hour).map(hour => hour % 3 === 0 ? (
            <text className="x-label" key={hour} x={left + hour * cellWidth + 14} y="205">{String(hour).padStart(2, "0")}</text>
          ) : null)}
          {Array.from({ length: 7 }, (_, weekday) => Array.from({ length: 24 }, (_, hour) => {
            const cell = byPosition.get(`${weekday}-${hour}`) ?? { weekday, hour, total_tokens: 0, events: 0 };
            const intensity = max > 0 ? Math.pow(cell.total_tokens / max, 0.55) : 0;
            const label = labelFor(cell);
            return <rect
              key={`${weekday}-${hour}`}
              x={left + hour * cellWidth}
              y={top + weekday * cellHeight}
              width="29"
              height="18"
              rx="3"
              tabIndex={0}
              aria-label={label}
              style={{ fill: `rgba(34, 211, 167, ${0.07 + intensity * 0.93})` }}
            ><title>{label}</title></rect>;
          }))}
        </svg>
      </div>
      <div className="codex-heat-legend"><span>{t("codexInsights.less")}</span>{[0.08, 0.28, 0.5, 0.72, 1].map(level => <i key={level} style={{ background: `rgba(34, 211, 167, ${level})` }} />)}<span>{t("codexInsights.more")}</span></div>
    </section>
  );
}

/** 功能：组合个人监测优先级最高的环比、Token 构成和活动热力图。 */
export function CodexInsights({ data }: CodexInsightsProps) {
  return (
    <div className="codex-insights">
      <BaselineComparison data={data} />
      <CompositionChart data={data} />
      <ActivityHeatmap data={data} />
    </div>
  );
}
