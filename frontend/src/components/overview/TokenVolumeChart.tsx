import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { TimeRange, TokenVolumeBucket } from "../../types/dashboard";
import { formatCompact } from "../../utils/format";
import { niceTokenCeiling, summarizeTokenVolume } from "../../utils/tokenVolume";

interface TokenVolumeChartProps {
  buckets: TokenVolumeBucket[];
  range: TimeRange;
  loading: boolean;
  error: boolean;
}

interface VolumeTooltipState {
  provider: "Ollama" | "Codex" | "Antigravity";
  timestamp: string;
  value: number;
  x: number;
  y: number;
  placement: "above" | "below";
}

const CHART_WIDTH = 900;
const CHART_HEIGHT = 176;

/** 功能：根据范围控制横轴标签密度，30 天仍保留所有柱子但只显示关键日期。 */
function shouldShowLabel(index: number, count: number, range: TimeRange): boolean {
  if (index === 0 || index === count - 1) return true;
  const targetLabels = range === "24H" ? 6 : range === "7D" ? 7 : 6;
  return index % Math.max(1, Math.ceil(count / targetLabels)) === 0;
}

/** 功能：展示真实事件增量，帮助快速比较每小时/每日的 Token 产量与供应商构成。 */
export function TokenVolumeChart({ buckets, range, loading, error }: TokenVolumeChartProps) {
  const { t, i18n } = useTranslation();
  const [tooltip, setTooltip] = useState<VolumeTooltipState | null>(null);
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const chart = useMemo(() => {
    const maxProviderValue = buckets.reduce(
      (maximum, bucket) => Math.max(maximum, bucket.ollama_tokens, bucket.codex_tokens, bucket.antigravity_tokens ?? 0),
      0,
    );
    const ceiling = niceTokenCeiling(maxProviderValue);
    const count = Math.max(1, buckets.length);
    const groupWidth = CHART_WIDTH / count;
    const barWidth = Math.min(12, Math.max(2, groupWidth * 0.22));
    const gap = Math.min(4, Math.max(1, groupWidth * 0.05));
    const bars = buckets.map((bucket, index) => {
      const center = index * groupWidth + groupWidth / 2;
      const ollamaHeight = bucket.ollama_tokens / ceiling * CHART_HEIGHT;
      const codexHeight = bucket.codex_tokens / ceiling * CHART_HEIGHT;
      const agTokens = bucket.antigravity_tokens ?? 0;
      const antigravityHeight = agTokens / ceiling * CHART_HEIGHT;
      return {
        bucket,
        ollama: {
          x: center - barWidth * 1.5 - gap,
          y: CHART_HEIGHT - ollamaHeight,
          height: ollamaHeight,
        },
        codex: {
          x: center - barWidth * 0.5,
          y: CHART_HEIGHT - codexHeight,
          height: codexHeight,
        },
        antigravity: {
          x: center + barWidth * 0.5 + gap,
          y: CHART_HEIGHT - antigravityHeight,
          height: antigravityHeight,
        },
        barWidth,
      };
    });
    return {
      bars,
      ceiling,
      summary: summarizeTokenVolume(buckets),
    };
  }, [buckets]);

  const labelFormatter = useMemo(() => new Intl.DateTimeFormat(locale, range === "24H"
    ? { hour: "2-digit", minute: "2-digit", hour12: false }
    : { month: "numeric", day: "numeric" }), [locale, range]);
  const peakBucket = chart.summary.peakIndex >= 0 ? buckets[chart.summary.peakIndex] : undefined;
  const yAxisLabels = [chart.ceiling, chart.ceiling * 2 / 3, chart.ceiling / 3, 0];
  // 口径：查询失败或尚未返回时的空数组不是零用量，避免与其他卡片形成虚假差额。
  const displayTotal = (value: number) => loading || error || !buckets.length ? "—" : formatCompact(value);
  const context = loading
    ? t("common.syncing")
    : t("volume.context", { count: buckets.length, unit: range === "24H" ? t("volume.hours") : t("volume.days") });

  /** 交互：将 SVG 柱子的实际屏幕位置换算到图表容器，避免缩放后浮层偏移。 */
  const showTooltip = (
    target: SVGRectElement,
    provider: VolumeTooltipState["provider"],
    timestamp: string,
    value: number,
  ) => {
    const wrapper = target.closest(".volume-chart-wrap");
    if (!(wrapper instanceof HTMLElement)) return;
    const wrapperRect = wrapper.getBoundingClientRect();
    const barRect = target.getBoundingClientRect();
    const barTop = barRect.top - wrapperRect.top;
    const placement = barTop < 58 ? "below" : "above";
    setTooltip({
      provider,
      timestamp,
      value,
      x: Math.min(wrapperRect.width - 64, Math.max(64, barRect.left + barRect.width / 2 - wrapperRect.left)),
      y: placement === "below" ? barRect.bottom - wrapperRect.top + 8 : barTop - 8,
      placement,
    });
  };

  return (
    <section className="panel token-volume-panel">
      <div className="panel-heading">
        <div>
          <h2>{t("volume.title")}</h2>
          <div className="chart-legend">
            <span><i className="legend-bar ollama-bar" />OLLAMA</span>
            <span><i className="legend-bar codex-bar" />CODEX</span>
            <span><i className="legend-bar antigravity-bar" />ANTIGRAVITY</span>
          </div>
        </div>
        <span className="panel-context">{context}</span>
      </div>
      <div className="volume-chart-wrap">
        <div className="y-axis volume-y-axis" aria-hidden="true">
          {yAxisLabels.map((label, index) => <span key={`${label}-${index}`}>{formatCompact(label)}</span>)}
        </div>
        {error ? <div className="volume-empty" role="status">{t("volume.unavailable")}</div> : (
          <svg
            className="volume-chart"
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={t("volume.aria")}
          >
            <g className="chart-grid">
              {[0, 1, 2, 3].map((line) => (
                <line key={line} x1="0" y1={line * (CHART_HEIGHT / 3)} x2={CHART_WIDTH} y2={line * (CHART_HEIGHT / 3)} />
              ))}
            </g>
            <g className="volume-bars">
              {chart.bars.map(({ bucket, ollama, codex, antigravity, barWidth }, index) => (
                <g key={bucket.timestamp} className={index === chart.bars.length - 1 ? "is-latest" : undefined}>
                  <rect
                    className="volume-bar ollama-bar"
                    x={ollama.x}
                    y={ollama.y}
                    width={barWidth}
                    height={ollama.height}
                    rx="2"
                    tabIndex={bucket.ollama_tokens > 0 ? 0 : -1}
                    aria-label={t("volume.tooltipAria", {
                      provider: "Ollama",
                      time: labelFormatter.format(new Date(bucket.timestamp)),
                      value: bucket.ollama_tokens.toLocaleString(locale),
                    })}
                    onPointerEnter={(event) => showTooltip(event.currentTarget, "Ollama", bucket.timestamp, bucket.ollama_tokens)}
                    onPointerLeave={() => setTooltip(null)}
                    onFocus={(event) => showTooltip(event.currentTarget, "Ollama", bucket.timestamp, bucket.ollama_tokens)}
                    onBlur={() => setTooltip(null)}
                  />
                  <rect
                    className="volume-bar codex-bar"
                    x={codex.x}
                    y={codex.y}
                    width={barWidth}
                    height={codex.height}
                    rx="2"
                    tabIndex={bucket.codex_tokens > 0 ? 0 : -1}
                    aria-label={t("volume.tooltipAria", {
                      provider: "Codex",
                      time: labelFormatter.format(new Date(bucket.timestamp)),
                      value: bucket.codex_tokens.toLocaleString(locale),
                    })}
                    onPointerEnter={(event) => showTooltip(event.currentTarget, "Codex", bucket.timestamp, bucket.codex_tokens)}
                    onPointerLeave={() => setTooltip(null)}
                    onFocus={(event) => showTooltip(event.currentTarget, "Codex", bucket.timestamp, bucket.codex_tokens)}
                    onBlur={() => setTooltip(null)}
                  />
                  <rect
                    className="volume-bar antigravity-bar"
                    x={antigravity.x}
                    y={antigravity.y}
                    width={barWidth}
                    height={antigravity.height}
                    rx="2"
                    tabIndex={(bucket.antigravity_tokens ?? 0) > 0 ? 0 : -1}
                    aria-label={t("volume.tooltipAria", {
                      provider: "Antigravity",
                      time: labelFormatter.format(new Date(bucket.timestamp)),
                      value: (bucket.antigravity_tokens ?? 0).toLocaleString(locale),
                    })}
                    onPointerEnter={(event) => showTooltip(event.currentTarget, "Antigravity", bucket.timestamp, bucket.antigravity_tokens ?? 0)}
                    onPointerLeave={() => setTooltip(null)}
                    onFocus={(event) => showTooltip(event.currentTarget, "Antigravity", bucket.timestamp, bucket.antigravity_tokens ?? 0)}
                    onBlur={() => setTooltip(null)}
                  />
                </g>
              ))}
            </g>
          </svg>
        )}
        {tooltip ? (
          <div
            id="volume-chart-tooltip"
            className={`volume-tooltip is-${tooltip.placement}`}
            role="tooltip"
            style={{ left: tooltip.x, top: tooltip.y }}
          >
            <span>{tooltip.provider} · {labelFormatter.format(new Date(tooltip.timestamp))}</span>
            <strong>{t("volume.tooltipValue", { value: tooltip.value.toLocaleString(locale) })}</strong>
          </div>
        ) : null}
        <div
          className="volume-x-axis"
          aria-hidden="true"
          style={{ gridTemplateColumns: `repeat(${Math.max(1, buckets.length)}, minmax(0, 1fr))` }}
        >
          {buckets.length ? buckets.map((bucket, index) => (
            <span key={bucket.timestamp}>{shouldShowLabel(index, buckets.length, range) ? labelFormatter.format(new Date(bucket.timestamp)) : ""}</span>
          )) : <span>{t("common.now")}</span>}
        </div>
      </div>
      <div className="chart-summary volume-summary">
        <div><span>{t("volume.recordedTotal")}</span><strong>{displayTotal(chart.summary.total)}</strong></div>
        <div><span>{t("chart.ollamaTotal")}</span><strong>{displayTotal(chart.summary.ollama)}</strong></div>
        <div><span>{t("chart.codexTotal")}</span><strong>{displayTotal(chart.summary.codex)}</strong></div>
        <div><span>{t("chart.antigravityTotal", { defaultValue: "Antigravity Total" })}</span><strong>{displayTotal(chart.summary.antigravity)}</strong></div>
        <div>
          <span>{t("volume.peakBucket")}</span>
          <strong title={chart.summary.peakTotal.toLocaleString()}>
            {peakBucket ? `${labelFormatter.format(new Date(peakBucket.timestamp))} · ${formatCompact(chart.summary.peakTotal)}` : "—"}
          </strong>
        </div>
      </div>
    </section>
  );
}
