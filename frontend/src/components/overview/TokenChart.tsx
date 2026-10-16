import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { TimeRange, TokenActivityPoint } from "../../types/dashboard";
import { formatCompact } from "../../utils/format";
import { rangeStart } from "../../utils/timeRanges";
import { formatAccountingBoundary, recordedTokenTotals } from "../../utils/usagePresentation";

interface TokenChartProps {
  activity: TokenActivityPoint[];
  range: TimeRange;
  loading: boolean;
  ollamaSpeed: number;
  endTimestamp: string;
  startTimestamp?: string;
  mode?: "overview" | "ollama" | "codex" | "antigravity";
}

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "2-digit",
  day: "2-digit",
});

/** 功能：刻度始终覆盖完整选择范围，数据不足时会自然留白而不是被拉伸铺满。 */
function buildAxisLabels(range: TimeRange, startTime: number, endTime: number, nowLabel: string): string[] {
  return Array.from({ length: 6 }, (_, index) => {
    if (index === 5) return nowLabel;
    const timestamp = new Date(startTime + (index / 5) * (endTime - startTime));
    return range === "24H" ? timeFormatter.format(timestamp) : dateFormatter.format(timestamp);
  });
}

interface ChartLineProps {
  points: string;
  className: string;
}

function ChartLine({ points, className }: ChartLineProps) {
  return <polyline className={className} points={points} />;
}

/**
 * 功能：Overview 使用双序列独立归一化；供应商明细使用单序列真实 token 刻度。
 * 明细轴允许从非零值起步，以免累计总量很大时把近期变化压成一条直线。
 */
export function TokenChart({
  activity,
  range,
  loading,
  ollamaSpeed,
  endTimestamp,
  startTimestamp,
  mode = "overview",
}: TokenChartProps) {
  const { t } = useTranslation();
  const chart = useMemo(() => {
    const width = 900;
    const height = 250;
    const paddingY = 12;
    const parsedEndTime = new Date(endTimestamp).getTime();
    // 一致性：账本请求可能比最近 WebSocket 帧更新，不能把已经入账的末点裁掉。
    const activityEnd = new Date(activity.at(-1)?.timestamp ?? "").getTime();
    const endTime = Math.max(Number.isFinite(parsedEndTime) ? parsedEndTime : 0, Number.isFinite(activityEnd) ? activityEnd : 0);
    const startTime = rangeStart(range, endTime, startTimestamp);
    const rangeMs = Math.max(1, endTime - startTime);
    const safe = activity.filter((point) => {
      const timestamp = new Date(point.timestamp).getTime();
      return Number.isFinite(timestamp) && timestamp >= startTime && timestamp <= endTime;
    });

    // 可视化：Overview 曲线数量级差异很大，各自缩放后才能同时观察趋势。
    const toNormalizedSeries = (select: (point: TokenActivityPoint) => number) => {
      const values = safe.map(select);
      const min = values.length ? Math.min(...values) : 0;
      const max = values.length ? Math.max(...values) : 0;
      const span = max - min;
      const coordinates = safe.map((point) => {
        const timestamp = new Date(point.timestamp).getTime();
        const x = Math.min(width, Math.max(0, ((timestamp - startTime) / rangeMs) * width));
        const ratio = span > 0 ? (select(point) - min) / span : 0.5;
        const y = height - paddingY - ratio * (height - paddingY * 2);
        return { x, y };
      });
      const points = coordinates
        .map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`)
        .join(" ");
      const first = coordinates[0];
      const last = coordinates.at(-1);
      return {
        points,
        area: first && last ? `${first.x.toFixed(2)},${height} ${points} ${last.x.toFixed(2)},${height}` : "",
      };
    };

    const detailSelect = mode === "ollama"
      ? (point: TokenActivityPoint) => point.ollama_tokens
      : mode === "codex"
        ? (point: TokenActivityPoint) => point.codex_tokens
        : (point: TokenActivityPoint) => point.antigravity_tokens ?? 0;
    const detailValues = mode === "overview" ? [] : safe.map(detailSelect);
    const detailMin = detailValues.length ? Math.min(...detailValues) : 0;
    const detailMax = detailValues.length ? Math.max(...detailValues) : 0;
    const detailSpan = detailMax - detailMin;
    const detailPadding = detailSpan > 0
      ? detailSpan * 0.08
      : Math.max(detailMax * 0.04, 1);
    const detailDomainMin = Math.max(0, detailMin - detailPadding);
    const detailDomainMax = Math.max(detailDomainMin + 1, detailMax + detailPadding);
    const detailDomainSpan = detailDomainMax - detailDomainMin;

    // 明细曲线共享同一条真实 token 数值轴，不再带入另一个供应商的数据。
    const detailCoordinates = mode === "overview" ? [] : safe.map((point) => {
      const timestamp = new Date(point.timestamp).getTime();
      const x = Math.min(width, Math.max(0, ((timestamp - startTime) / rangeMs) * width));
      const ratio = (detailSelect(point) - detailDomainMin) / detailDomainSpan;
      const y = height - paddingY - ratio * (height - paddingY * 2);
      return { x, y };
    });
    const detailPoints = detailCoordinates
      .map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`)
      .join(" ");
    const detailFirst = detailCoordinates[0];
    const detailLast = detailCoordinates.at(-1);
    const detailArea = detailFirst && detailLast
      ? `${detailFirst.x.toFixed(2)},${height} ${detailPoints} ${detailLast.x.toFixed(2)},${height}`
      : "";
    return {
      ollama: toNormalizedSeries((point) => point.ollama_tokens),
      codex: toNormalizedSeries((point) => point.codex_tokens),
      antigravity: toNormalizedSeries((point) => point.antigravity_tokens ?? 0),
      detail: { points: detailPoints, area: detailArea },
      detailAxis: Array.from({ length: 4 }, (_, index) => (
        detailDomainMax - (index / 3) * detailDomainSpan
      )),
      endTime,
      startTime,
      pointCount: safe.length,
      recorded: recordedTokenTotals(safe),
      recordedAt: safe.at(-1)?.timestamp,
    };
  }, [activity, endTimestamp, mode, range, startTimestamp]);
  const nowLabel = t("common.now");
  const axisLabels = useMemo(
    () => buildAxisLabels(range, chart.startTime, chart.endTime, nowLabel),
    [chart.startTime, chart.endTime, nowLabel, range],
  );

  const ollamaTotal = chart.recorded?.ollama;
  const codexTotal = chart.recorded?.codex;
  const antigravityTotal = chart.recorded?.antigravity;
  const total = chart.recorded
    ? chart.recorded.ollama + chart.recorded.codex + (chart.recorded.antigravity ?? 0)
    : undefined;
  const displayTotal = (value: number | undefined) => value === undefined ? "—" : formatCompact(value);
  const rangeLabel = range === "24H" ? t("common.today") : range;
  const isOverview = mode === "overview";
  const isOllama = mode === "ollama";
  const isCodex = mode === "codex";
  const isAntigravity = mode === "antigravity";
  const providerName = isOllama ? "OLLAMA" : isCodex ? "CODEX" : "ANTIGRAVITY";
  const providerTotal = isOllama ? ollamaTotal : isCodex ? codexTotal : antigravityTotal;
  const providerLabel = isOllama ? "Ollama" : isCodex ? "Codex" : "Antigravity";
  const heading = isOverview
    ? t("chart.tokenActivity")
    : t("chart.providerActivity", { provider: providerLabel });
  const yAxisLabels = isOverview
    ? ["100%", "66%", "33%", "0%"]
    : chart.detailAxis.map(formatCompact);
  const summary = isOverview
    ? [
        [t("chart.totalTokens"), displayTotal(total)],
        [t("chart.ollamaTotal"), displayTotal(ollamaTotal)],
        [t("chart.codexTotal"), displayTotal(codexTotal)],
        [t("chart.antigravityTotal", { defaultValue: "Antigravity Total" }), displayTotal(antigravityTotal)],
        [t("chart.liveThroughput"), `${ollamaSpeed.toFixed(1)} T/S`],
      ]
    : isOllama
      ? [
          [t("chart.ollamaTokens"), displayTotal(providerTotal)],
          [t("chart.timeRange"), rangeLabel],
          [t("chart.dataPoints"), String(chart.pointCount)],
          [t("chart.liveThroughput"), `${ollamaSpeed.toFixed(1)} T/S`],
        ]
      : isCodex
        ? [
            [t("chart.codexTokensRange", { range: rangeLabel }), displayTotal(providerTotal)],
            [t("chart.timeRange"), rangeLabel],
            [t("chart.dataPoints"), String(chart.pointCount)],
            [t("chart.axis"), t("chart.tokenCount")],
          ]
        : [
            [t("chart.antigravityTokensRange", { range: rangeLabel, defaultValue: `Antigravity Tokens (${rangeLabel})` }), displayTotal(providerTotal)],
            [t("chart.timeRange"), rangeLabel],
            [t("chart.dataPoints"), String(chart.pointCount)],
            [t("chart.axis"), t("chart.tokenCount")],
          ];
  const gradientColor = mode === "codex" ? "#8b7cf6" : mode === "antigravity" ? "#f59e0b" : "#38d9e6";
  const gradientId = `token-area-${mode}`;

  return (
    <section className="panel token-panel">
      <div className="panel-heading">
        <div>
          <h2>{heading}</h2>
          <div className="chart-legend">
            {isOverview || isOllama ? <span><i className="legend-line" />OLLAMA · {displayTotal(ollamaTotal)}</span> : null}
            {isOverview || isCodex ? <span><i className="legend-line is-codex" />CODEX · {displayTotal(codexTotal)}</span> : null}
            {isOverview || isAntigravity ? <span><i className="legend-line is-antigravity" />ANTIGRAVITY · {displayTotal(antigravityTotal)}</span> : null}
          </div>
        </div>
        <span className="panel-context" title={t("chart.dailyCounters")}>
          {loading
            ? t("common.syncing")
            : `${range === "24H" ? t("common.today") : range} · ${chart.pointCount} ${t("chart.points")} · ${t("chart.recorded")}`} · {t(isOverview ? "chart.dualScale" : "chart.tokenScale")}
        </span>
      </div>
      <div className="token-chart-wrap">
        <div className="y-axis" aria-hidden="true">
          {yAxisLabels.map((label, index) => <span key={`${label}-${index}`}>{label}</span>)}
        </div>
        <svg
          className="token-chart"
          viewBox="0 0 900 250"
          preserveAspectRatio="none"
          role="img"
          aria-label={isOverview ? t("chart.overviewAria") : t("chart.providerAria", { provider: providerName })}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={gradientColor} stopOpacity="0.12" />
              <stop offset="100%" stopColor={gradientColor} stopOpacity="0" />
            </linearGradient>
          </defs>
          <g className="chart-grid">
            {[0, 1, 2, 3].map((line) => <line key={`h-${line}`} x1="0" y1={line * 83.33} x2="900" y2={line * 83.33} />)}
            {[0, 1, 2, 3, 4, 5, 6].map((line) => <line key={`v-${line}`} x1={line * 150} y1="0" x2={line * 150} y2="250" />)}
          </g>
          <polygon className="chart-area" style={{ fill: `url(#${gradientId})` }} points={isOverview ? chart.ollama.area : chart.detail.area} />
          {isOverview || isOllama ? <ChartLine className="chart-line ollama-line" points={isOverview ? chart.ollama.points : chart.detail.points} /> : null}
          {isOverview || isCodex ? <ChartLine className="chart-line codex-line" points={isOverview ? chart.codex.points : chart.detail.points} /> : null}
          {isOverview || isAntigravity ? <ChartLine className="chart-line antigravity-line" points={isOverview ? chart.antigravity.points : chart.detail.points} /> : null}
        </svg>
        <div className="x-axis" aria-hidden="true">
          {axisLabels.map((label, index) => <span key={`${label}-${index}`}>{label}</span>)}
        </div>
      </div>
      <div className="chart-summary">
        {summary.map(([label, value]) => (
          <div key={label}><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>
      <p className="chart-accounting-note">
        {t("chart.recordedNote")}
        {chart.recordedAt ? ` ${t("chart.recordedAt", { time: formatAccountingBoundary(chart.recordedAt) })}` : ""}
      </p>
    </section>
  );
}
