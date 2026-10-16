import type { DashboardView, OverviewSnapshot, TimeRange, TokenActivityPoint, TrendPoint } from "../../types/dashboard";
import { formatCompact, formatPercent } from "../../utils/format";
import { getRangeTokenTotal, getRangeUsage } from "../../utils/tokens";
import { useTranslation } from "react-i18next";
import { Sparkline } from "../common/Sparkline";
import { StatusDot } from "../common/StatusDot";
import { SignalsTable } from "../overview/SignalsTable";
import { TelemetryBand } from "../overview/TelemetryBand";
import { TokenChart } from "../overview/TokenChart";
import { AntigravityAnalytics } from "./AntigravityAnalytics";
import { CodexAnalytics } from "./CodexAnalytics";

interface DetailProps {
  snapshot: OverviewSnapshot;
  history: TrendPoint[];
  tokenActivity: TokenActivityPoint[];
  range: TimeRange;
  historyLoading: boolean;
  activityLoading: boolean;
  onNavigate?: (view: DashboardView) => void;
}

interface MetricItem {
  label: string;
  value: string;
  detail: string;
  estimated?: boolean;
  exactValue?: number;
}

function MetricGrid({ items }: { items: MetricItem[] }) {
  const { t } = useTranslation();
  return (
    <section className="detail-metric-grid" aria-label={t("details.metrics")}>
      {items.map((item) => (
        <article className={`detail-metric panel${item.estimated ? " is-estimated" : ""}`} key={item.label}>
          <span>{item.label}</span>
          <strong title={item.exactValue?.toLocaleString()}>{item.value}</strong>
          <small>{item.detail}</small>
        </article>
      ))}
    </section>
  );
}

function DetailHero({
  eyebrow,
  title,
  detail,
  online,
  status,
  onNavigate,
  badge,
  children,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  online: boolean;
  status: string;
  onNavigate?: (view: DashboardView) => void;
  badge?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const statusLabel = t(`common.${status.toLowerCase()}`, { defaultValue: status.toUpperCase() });
  return (
    <section className="detail-hero panel">
      <div className="detail-hero-copy">
        {onNavigate ? (
          <nav className="vitals-breadcrumb" aria-label="Breadcrumb">
            <button type="button" className="breadcrumb-btn" onClick={() => onNavigate("overview")}>
              {t("operations.breadcrumbOverview", { defaultValue: "总览看板" })}
            </button>
            <span className="breadcrumb-sep">›</span>
            <span className="breadcrumb-curr">{eyebrow}</span>
          </nav>
        ) : null}
        <div className="detail-hero-heading">
          <span className="eyeline">{eyebrow}</span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {badge}
            <StatusDot online={online} label={statusLabel} />
          </div>
        </div>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
      {children}
    </section>
  );
}

/** 功能：展示 Ollama 驻留状态、代理接入说明以及真实请求级 token 指标。 */
export function OllamaDetail({ snapshot, tokenActivity, range, activityLoading, onNavigate }: DetailProps) {
  const { t, i18n } = useTranslation();
  const ollama = snapshot.ollama;
  const rangeUsage = getRangeUsage(ollama, range);
  const rangeLabel = range === "24H" ? t("common.today") : range;
  const isStreaming = ollama.metric_precision === "estimated" && ollama.inflight_requests > 0;
  const proxyUrl = "http://127.0.0.1:11435";
  const signals = snapshot.recent_signals.filter((signal) => signal.source === "OLLAMA");
  const isChinese = i18n.resolvedLanguage?.startsWith("zh");
  const detail = isChinese
    ? t(ollama.online ? "details.ollama.online" : "details.ollama.unavailable")
    : ollama.detail ?? t("details.ollama.unavailable");
  return (
    <>
      <DetailHero
        eyebrow={t("details.ollama.provider")}
        title={ollama.model}
        detail={detail}
        online={ollama.online}
        status={ollama.status}
        onNavigate={onNavigate}
      >
        <div className={`proxy-card${isStreaming ? " is-streaming" : ""}`} aria-live="polite">
          <span className="eyeline">{t("details.ollama.baseUrl")}</span>
          <code>{proxyUrl}</code>
          <strong>
            {isStreaming
              ? t("details.ollama.streaming", { count: ollama.inflight_requests })
              : ollama.sessions_today
                ? t("details.ollama.capturing")
                : t("details.ollama.waiting")}
          </strong>
          <small>{t("details.ollama.routeNote")}</small>
        </div>
      </DetailHero>
      <MetricGrid items={[
        { label: t("details.ollama.inputTokens"), value: formatCompact(rangeUsage.input_tokens), detail: t("details.ollama.rangeExact", { range: rangeLabel }) },
        {
          label: `${t("details.ollama.outputTokens")}${isStreaming ? " ~" : ""}`,
          value: `${isStreaming ? "~" : ""}${formatCompact(rangeUsage.output_tokens)}`,
          detail: isStreaming ? t("details.ollama.liveCalibrates", { count: ollama.live_output_tokens }) : t("details.ollama.proxyExact"),
          estimated: isStreaming,
        },
        {
          label: t("details.ollama.generationSpeed"),
          value: `${isStreaming ? "~" : ""}${ollama.tokens_per_second.toFixed(1)} t/s`,
          detail: isStreaming ? t("details.ollama.liveEstimate") : ollama.last_tokens_per_second > 0
            ? t("details.ollama.idleLast", { speed: ollama.last_tokens_per_second.toFixed(1) })
            : t("details.ollama.idleNoSpeed"),
          estimated: isStreaming,
        },
        { label: t("details.ollama.requestsRange", { range: rangeLabel }), value: String(rangeUsage.interactions), detail: t("details.ollama.trackedProxyCounts", { count: rangeUsage.exact_completions }) },
        { label: t("details.ollama.contextWindow"), value: ollama.context_size > 0 ? formatCompact(ollama.context_size) : "—", detail: t("details.ollama.runtimeLimit") },
      ]} />
      <div className="detail-content-grid">
        <TokenChart mode="ollama" activity={tokenActivity} range={range} loading={activityLoading} ollamaSpeed={ollama.tokens_per_second} endTimestamp={snapshot.timestamp} startTimestamp={snapshot.range_starts?.[range]} />
        <SignalsTable signals={signals} />
      </div>
    </>
  );
}

/** 功能：拆分 Codex 输入、输出、缓存与推理 token，便于判断上下文效率。 */
export function CodexDetail({ snapshot, tokenActivity, range, activityLoading, onNavigate }: DetailProps) {
  const { t, i18n } = useTranslation();
  const codex = snapshot.codex;
  const codexRangeTotal = getRangeTokenTotal(codex, range);
  const rangeUsage = getRangeUsage(codex, range);
  const rangeLabel = range === "24H" ? t("common.today") : range;
  const accounting = snapshot.codex_accounting?.[range];
  const balanced = accounting
    ? accounting.raw_tokens === accounting.accepted_tokens + accounting.duplicate_tokens
      && accounting.accepted_tokens === codexRangeTotal
    : false;
  // 口径：源日志清理后持久账本仍保留用量，不能把缺少扫描证据误报为去重计算错误。
  const retainedTokens = accounting ? Math.max(0, codexRangeTotal - accounting.accepted_tokens) : 0;
  const cacheRatio = formatPercent(rangeUsage.cached_tokens, rangeUsage.input_tokens);
  const signals = snapshot.recent_signals.filter((signal) => signal.source === "CODEX");
  const isChinese = i18n.resolvedLanguage?.startsWith("zh");
  const detail = isChinese
    ? t("details.codex.sessionDetail", { count: codex.sessions_today })
    : codex.detail ?? t("details.codex.collector");
  return (
    <>
      <DetailHero eyebrow={t("details.codex.provider")} title={codex.model} detail={detail} online={codex.online} status={codex.status} onNavigate={onNavigate}>
        <div className="proxy-card">
          <span className="eyeline">{t("details.codex.usageRange", { range: rangeLabel })}</span>
          <strong title={`${codexRangeTotal.toLocaleString()} Token`}>{t("details.codex.tokensRange", { value: formatCompact(codexRangeTotal), range: rangeLabel })}</strong>
          <small>{t("details.codex.privacy")}</small>
        </div>
      </DetailHero>
      <section className="accounting-strip panel" aria-label={t("details.codex.accountingTitle")}>
        <div><span>{t("details.codex.accountingTitle")}</span><strong className={balanced ? "is-balanced" : "is-pending"}>{t(balanced ? "details.codex.balanced" : "details.codex.pending")}</strong></div>
        <dl>
          <div><dt>{t("details.codex.rawTokens")}</dt><dd title={accounting?.raw_tokens.toLocaleString()}>{accounting ? formatCompact(accounting.raw_tokens) : "—"}</dd></div>
          <div><dt>{t("details.codex.acceptedTokens")}</dt><dd title={accounting?.accepted_tokens.toLocaleString()}>{accounting ? formatCompact(accounting.accepted_tokens) : "—"}</dd></div>
          <div><dt>{t("details.codex.filteredDuplicates")}</dt><dd title={accounting?.duplicate_tokens.toLocaleString()}>{accounting ? formatCompact(accounting.duplicate_tokens) : "—"}</dd></div>
          <div><dt>{t("details.codex.duplicateEvents")}</dt><dd>{accounting?.duplicate_events ?? "—"}</dd></div>
        </dl>
        <small>{t("details.codex.accountingNote", { range: range === "24H" ? t("common.today") : range })}</small>
        {retainedTokens > 0 ? <small>{t("usageAudit.retained", { count: retainedTokens.toLocaleString() })}</small> : null}
      </section>
      <MetricGrid items={[
        { label: t("details.codex.inputTokens"), value: formatCompact(rangeUsage.input_tokens), detail: t("details.codex.rangeSessions", { range: rangeLabel, count: rangeUsage.interactions }) },
        { label: t("details.codex.outputTokens"), value: formatCompact(rangeUsage.output_tokens), detail: t("details.codex.rangeSessions", { range: rangeLabel, count: rangeUsage.interactions }) },
        { label: t("details.codex.cachedInput"), value: formatCompact(rangeUsage.cached_tokens), detail: t("details.codex.cachedRatioRange", { ratio: cacheRatio.toFixed(0), range: rangeLabel }) },
        { label: t("details.codex.reasoning"), value: formatCompact(rangeUsage.reasoning_tokens), detail: t("details.codex.reportedRange", { range: rangeLabel }) },
        { label: t("details.codex.yesterdayTokens"), value: formatCompact(codex.previous_day_tokens), detail: t("details.codex.localDay") },
        { label: t("details.codex.sessionsRange", { range: rangeLabel }), value: String(rangeUsage.interactions), detail: t("details.codex.localJsonl") },
      ]} />
      <CodexAnalytics range={range} />
      <div className="detail-content-grid">
        <TokenChart mode="codex" activity={tokenActivity} range={range} loading={activityLoading} ollamaSpeed={snapshot.ollama.tokens_per_second} endTimestamp={snapshot.timestamp} startTimestamp={snapshot.range_starts?.[range]} />
        <SignalsTable signals={signals} />
      </div>
    </>
  );
}

function HardwareTrend({ label, value, values }: { label: string; value: string; values: number[] }) {
  return (
    <article className="hardware-trend panel">
      <span>{label}</span>
      <strong>{value}</strong>
      <Sparkline values={values} />
    </article>
  );
}

/** 功能：集中展示 GPU/CPU/RAM 状态及所选时间范围内的硬件趋势。 */
export function HardwareDetail({ snapshot, history, onNavigate }: DetailProps) {
  const { t } = useTranslation();
  const hardware = snapshot.hardware;
  const isInferenceActive = snapshot.ollama.tokens_per_second > 0 || (snapshot.antigravity.online && snapshot.antigravity.status === "active");

  return (
    <>
      <DetailHero
        eyebrow={t("hardware.provider")}
        title={hardware.gpu_name}
        detail={t("hardware.description")}
        online={hardware.gpu_available}
        status={hardware.gpu_available ? "online" : "offline"}
        onNavigate={onNavigate}
        badge={isInferenceActive ? <span className="badge-inference-active">⚡ INFERENCE ACTIVE</span> : null}
      />
      <TelemetryBand hardware={hardware} history={history} />
      <section className="hardware-trend-grid" aria-label={t("hardware.trendSummary")}>
        <HardwareTrend label={t("hardware.gpuUtilization")} value={`${hardware.gpu_usage.toFixed(0)}%`} values={history.map((point) => point.gpu_usage)} />
        <HardwareTrend label={t("hardware.cpuUtilization")} value={`${hardware.cpu_usage.toFixed(0)}%`} values={history.map((point) => point.cpu_usage)} />
        <HardwareTrend label={t("hardware.ramPressure")} value={`${formatPercent(hardware.ram_used_gb, hardware.ram_total_gb).toFixed(0)}%`} values={history.map((point) => point.ram_usage)} />
        <HardwareTrend label={t("hardware.vramPressure")} value={`${formatPercent(hardware.vram_used_gb, hardware.vram_total_gb).toFixed(0)}%`} values={history.map((point) => point.vram_usage)} />
      </section>
      <SignalsTable signals={snapshot.recent_signals.filter((signal) => ["GPU", "HARDWARE", "SYSTEM"].includes(signal.source))} />
    </>
  );
}

/** 功能：拆分 Antigravity 输入、输出、缓存 token，便于分析 IDE 内部模型消耗。 */
export function AntigravityDetail({ snapshot, tokenActivity, range, activityLoading, onNavigate }: DetailProps) {
  const { t, i18n } = useTranslation();
  const antigravity = snapshot.antigravity;
  const antigravityRangeTotal = getRangeTokenTotal(antigravity, range);
  const rangeUsage = getRangeUsage(antigravity, range);
  const rangeLabel = range === "24H" ? t("common.today") : range;
  const accounting = snapshot.antigravity_accounting?.[range];
  const balanced = accounting
    ? accounting.raw_tokens === accounting.accepted_tokens + accounting.duplicate_tokens
      && accounting.accepted_tokens === antigravityRangeTotal
    : false;
  const retainedTokens = accounting ? Math.max(0, antigravityRangeTotal - accounting.accepted_tokens) : 0;
  const cacheRatio = formatPercent(rangeUsage.cached_tokens, rangeUsage.cached_tokens + rangeUsage.input_tokens);
  const signals = snapshot.recent_signals.filter((signal) => signal.source === "ANTIGRAVITY");
  const isChinese = i18n.resolvedLanguage?.startsWith("zh");
  const detail = isChinese
    ? t("details.antigravity.sessionDetail", { count: antigravity.sessions_today, defaultValue: `今日有 ${antigravity.sessions_today} 个活跃会话` })
    : antigravity.detail ?? t("details.antigravity.collector", { defaultValue: "Local Antigravity transcript metadata" });

  return (
    <>
      <DetailHero
        eyebrow={t("details.antigravity.provider", { defaultValue: "Antigravity IDE Provider" })}
        title={antigravity.model}
        detail={detail}
        online={antigravity.online}
        status={antigravity.status}
        onNavigate={onNavigate}
      >
        <div className="proxy-card">
          <span className="eyeline">{t("details.antigravity.usageRange", { range: rangeLabel, defaultValue: `${rangeLabel} 用量` })}</span>
          <strong title={`${antigravityRangeTotal.toLocaleString()} Token`}>
            {t("details.antigravity.tokensRange", {
              value: formatCompact(antigravityRangeTotal),
              range: rangeLabel,
              defaultValue: `${formatCompact(antigravityRangeTotal)} (${rangeLabel})`,
            })}
          </strong>
          <small>{t("details.antigravity.privacy", { defaultValue: "全量模型上下文吞吐（含 Prompt Caching 缓存）" })}</small>
        </div>
      </DetailHero>
      <section className="accounting-strip panel" aria-label={t("details.antigravity.accountingTitle", { defaultValue: "Antigravity 日对账" })}>
        <div>
          <span>{t("details.antigravity.accountingTitle", { defaultValue: "Antigravity 日对账" })}</span>
          <strong className={balanced ? "is-balanced" : "is-pending"}>
            {t(balanced ? "details.codex.balanced" : "details.codex.pending")}
          </strong>
        </div>
        <dl>
          <div>
            <dt>{t("details.codex.rawTokens")}</dt>
            <dd title={accounting?.raw_tokens.toLocaleString()}>{accounting ? formatCompact(accounting.raw_tokens) : "—"}</dd>
          </div>
          <div>
            <dt>{t("details.codex.acceptedTokens")}</dt>
            <dd title={accounting?.accepted_tokens.toLocaleString()}>{accounting ? formatCompact(accounting.accepted_tokens) : "—"}</dd>
          </div>
          <div>
            <dt>{t("details.codex.filteredDuplicates")}</dt>
            <dd title={accounting?.duplicate_tokens.toLocaleString()}>{accounting ? formatCompact(accounting.duplicate_tokens) : "—"}</dd>
          </div>
          <div>
            <dt>{t("details.codex.duplicateEvents")}</dt>
            <dd>{accounting?.duplicate_events ?? "—"}</dd>
          </div>
        </dl>
        <small>{t("details.antigravity.accountingNote", { range: range === "24H" ? t("common.today") : range, defaultValue: `与本地 transcript 逐行对账 (${range === "24H" ? t("common.today") : range})` })}</small>
        {retainedTokens > 0 ? <small>{t("usageAudit.retained", { count: retainedTokens.toLocaleString() })}</small> : null}
      </section>
      <MetricGrid items={[
        { label: t("details.antigravity.totalTokens", { defaultValue: `${rangeLabel} 全量吞吐` }), value: formatCompact(antigravityRangeTotal), detail: t("details.antigravity.totalTokensDetail", { defaultValue: "含上下文缓存吞吐规模" }) },
        { label: t("details.antigravity.inputTokens", { defaultValue: "新输入 Token" }), value: formatCompact(rangeUsage.input_tokens), detail: t("details.antigravity.rangeSessions", { range: rangeLabel, count: rangeUsage.interactions, defaultValue: `${rangeLabel} 共 ${rangeUsage.interactions} 次交互` }) },
        { label: t("details.antigravity.outputTokens", { defaultValue: "生成输出 Token" }), value: formatCompact(rangeUsage.output_tokens), detail: t("details.antigravity.rangeSessions", { range: rangeLabel, count: rangeUsage.interactions, defaultValue: `${rangeLabel} 共 ${rangeUsage.interactions} 次交互` }) },
        { label: t("details.antigravity.cachedInput", { defaultValue: "缓存读取" }), value: formatCompact(rangeUsage.cached_tokens), detail: `缓存命中率 ${cacheRatio.toFixed(1)}%` },
        { label: t("details.antigravity.yesterdayTokens", { defaultValue: "昨日 Token" }), value: formatCompact(antigravity.previous_day_tokens), detail: t("details.antigravity.localDay", { defaultValue: "本地自然日" }) },
        { label: t("details.antigravity.sessionsRange", { range: rangeLabel, defaultValue: `${rangeLabel} 会话数` }), value: String(rangeUsage.interactions), detail: t("details.antigravity.localJsonl", { defaultValue: "本地 transcript 会话" }) },
      ]} />
      <AntigravityAnalytics range={range} />
      <div className="detail-content-grid">
        <TokenChart mode="antigravity" activity={tokenActivity} range={range} loading={activityLoading} ollamaSpeed={snapshot.ollama.tokens_per_second} endTimestamp={snapshot.timestamp} startTimestamp={snapshot.range_starts?.[range]} />
        <SignalsTable signals={signals} />
      </div>
    </>
  );
}
