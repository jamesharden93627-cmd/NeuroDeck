import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOperations } from "../../hooks/useOperations";
import type { DashboardView, TimeRange } from "../../types/dashboard";
import { formatCompact } from "../../utils/format";
import "../../styles/operations.css";
import { OperationsPerformance } from "./OperationsPerformance";

const statuses = ["completed", "failed", "cancelled", "unmetered", "incomplete"];
const duration = (value: number | null | undefined) => value == null ? "—" : `${value.toFixed(2)} s`;
const number = (value: number | null) => value == null ? "—" : value.toLocaleString();

interface OperationsViewProps {
  range: TimeRange;
  onNavigate?: (view: DashboardView) => void;
}

function OperationsQuickStart() {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const curlCmd = `curl -X POST http://127.0.0.1:11435/api/generate -d '{"model": "qwen2.5:7b", "prompt": "Hi, NeuroDeck!"}'`;

  const copyToClipboard = () => {
    if (navigator.clipboard) {
      void navigator.clipboard.writeText(curlCmd);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <section className="ops-quickstart-card panel" aria-label={t("operations.quickStartTitle")}>
      <div className="ops-quickstart-header">
        <div className="ops-quickstart-badge">
          <span className="ops-pulse-dot" />
          <strong>{t("operations.proxyListening")}</strong>
        </div>
        <span className="ops-upstream-pill">{t("operations.proxyTarget")}</span>
      </div>
      <div className="ops-quickstart-body">
        <h3>{t("operations.quickStartTitle")}</h3>
        <p className="ops-quickstart-desc">{t("operations.quickStartSubtitle")}</p>
        <div className="ops-steps-box">
          <span className="ops-steps-title">{t("operations.stepTitle")}</span>
          <div className="ops-steps-grid">
            <div className="ops-step-item">
              <span className="ops-step-tag">WebUI</span>
              <span>{t("operations.stepWebUI")}</span>
            </div>
            <div className="ops-step-item">
              <span className="ops-step-tag">IDE</span>
              <span>{t("operations.stepContinue")}</span>
            </div>
          </div>
        </div>
        <div className="ops-test-block">
          <span>{t("operations.testCmdTitle")}</span>
          <div className="ops-code-row">
            <code>{curlCmd}</code>
            <button type="button" className="ops-button primary" onClick={copyToClipboard}>
              {copied ? t("operations.copied") : t("operations.copyCommand")}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

/** 功能：将代理请求转为可筛选的运营视图；缺失用量不按零处理，分页使用固定水位。 */
export function OperationsView({ range, onNavigate }: OperationsViewProps) {
  const { t, i18n } = useTranslation();
  const [filters, setFilters] = useState({ model: "", status: "", search: "" });
  const [draft, setDraft] = useState(filters);
  const [pagination, setPagination] = useState<{ page: number; snapshot?: number }>({ page: 1 });
  const [revision, setRevision] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [expanded, setExpanded] = useState<string | null>(null);
  const params = new URLSearchParams({ range, ...filters, page: String(pagination.page), page_size: String(pageSize), refresh: String(revision) });
  if (pagination.snapshot !== undefined) params.set("snapshot_id", String(pagination.snapshot));
  const { data, error, loading } = useOperations(params.toString(), pagination.page === 1);
  const summary = data?.summary;
  const totalTokens = summary ? summary.input_tokens + summary.output_tokens : 0;
  const maxDaily = Math.max(1, ...(data?.series.map(point => point.input_tokens + point.output_tokens) ?? []));
  const hasFilters = Boolean(filters.model || filters.status || filters.search);
  const isZeroState = Boolean(summary && summary.requests === 0 && !hasFilters);

  /** 处理：筛选和刷新回到最新首页，避免复用旧水位导致看不到新增记录。 */
  function refresh() {
    setPagination({ page: 1 });
    setExpanded(null);
    setRevision(value => value + 1);
  }

  // 处理：导出复用当前页面水位与筛选，避免下载期间新增请求改变导出内容。
  const exportParams = new URLSearchParams(params);
  if (data) {
    exportParams.set("snapshot_id", String(data.snapshot_id));
    exportParams.set("page", String(data.page));
  }
  exportParams.set("format", "csv");

  return <main className="operations-center">
    {onNavigate ? (
      <nav className="vitals-breadcrumb" aria-label="Breadcrumb">
        <button type="button" className="breadcrumb-btn" onClick={() => onNavigate("overview")}>
          {t("operations.breadcrumbOverview")}
        </button>
        <span className="breadcrumb-sep">›</span>
        <span className="breadcrumb-curr">{t("operations.breadcrumbRequests")}</span>
      </nav>
    ) : null}
    <section className="ops-intro">
      <div><span className="ops-eyebrow">{t("operations.scope")}</span><h1>{t("operations.title")}</h1><p>{t("operations.description")}</p></div>
      <button className="ops-button" type="button" onClick={refresh}>{t("operations.refresh")}</button>
    </section>
    <p className="ops-source">{t("operations.source")}</p>

    {isZeroState ? <OperationsQuickStart /> : null}

    <form className="ops-filters" aria-label={t("operations.filters")} onSubmit={event => {
      event.preventDefault(); setFilters({ ...draft, search: draft.search.trim() }); refresh();
    }}>
      <label>{t("operations.model")}<select value={draft.model} onChange={event => setDraft({ ...draft, model: event.target.value })}>
        <option value="">{t("operations.allModels")}</option>
        {draft.model && !data?.model_options.includes(draft.model) ? <option value={draft.model}>{draft.model}</option> : null}
        {data?.model_options.map(model => <option key={model} value={model}>{model}</option>)}
      </select></label>
      <label>{t("operations.status")}<select value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value })}>
        <option value="">{t("operations.allStatuses")}</option>
        {statuses.map(status => <option key={status} value={status}>{t(`operations.outcome.${status}`)}</option>)}
      </select></label>
      <label className="ops-search">{t("operations.search")}<input type="search" maxLength={128} value={draft.search} placeholder={t("operations.search")} onChange={event => setDraft({ ...draft, search: event.target.value })} /></label>
      <button type="submit" className="ops-button primary">{t("operations.apply")}</button>
      <button type="button" className="ops-button" onClick={() => {
        const empty = { model: "", status: "", search: "" }; setDraft(empty); setFilters(empty); refresh();
      }}>{t("operations.reset")}</button>
    </form>
    {loading || error ? <div className="ops-empty" role="status">{t(error ? "operations.loadError" : "operations.loading")}</div> : null}
    {data && summary ? <>
      <section className="ops-kpis" aria-label={t("overview.operationalSummary")}>
        <article><span>{t("operations.requests")}</span><strong>{number(summary.requests)}</strong><small>{t("operations.failed")} {summary.failed} · {t("operations.cancelled")} {summary.cancelled} · {t("operations.incomplete")} {summary.incomplete}</small></article>
        <article><span>{t("operations.success")}</span><strong className="ops-green">{summary.success_rate == null ? "—" : `${summary.success_rate.toFixed(1)}%`}</strong><small>{t("operations.successNote")}</small></article>
        <article><span>{t("operations.tokens")}</span><strong title={number(totalTokens)}>{formatCompact(totalTokens)}</strong><small>{t("operations.metered", { count: summary.metered })} · {t("operations.tokensNote")}</small></article>
        <article><span>{t("operations.duration")}</span><strong>{duration(summary.avg_duration_seconds)}</strong><small>{t("operations.p95")} {duration(summary.p95_duration_seconds)} · {t("operations.samples", { count: summary.duration_samples })}</small></article>
      </section>
      <div className="ops-analysis-grid">
        <section className="ops-panel">
          <div className="ops-heading"><h2>{t("operations.daily")}</h2><span>{t("operations.dailyNote")}</span></div>
          <div className="ops-legend"><span className="input">{t("operations.input")} {formatCompact(summary.input_tokens)}</span><span className="output">{t("operations.output")} {formatCompact(summary.output_tokens)}</span></div>
          <div className="ops-bars" role="img" aria-label={t("operations.daily")}>
            <div className="ops-axis"><span>{formatCompact(maxDaily === 1 && !totalTokens ? 0 : maxDaily)}</span><span>0</span></div>
            {data.series.map((point, index) => <div className="ops-day" key={point.day} title={`${point.day} · ${t("operations.requests")} ${point.requests} · ${t("operations.input")} ${number(point.input_tokens)} · ${t("operations.output")} ${number(point.output_tokens)}`}>
              <div className="ops-stack">
                <i className="output" style={{ height: `${point.output_tokens / maxDaily * 100}%` }} />
                <i className="input" style={{ height: `${point.input_tokens / maxDaily * 100}%` }} />
              </div>
              <span>{data.series.length <= 7 || index % 5 === 0 || index === data.series.length - 1 ? point.day.slice(5).replace("-", "/") : ""}</span>
            </div>)}
          </div>
        </section>
        <section className="ops-panel">
          <div className="ops-heading"><h2>{t("operations.rankings")}</h2><span>{t("operations.top")}</span></div>
          <div className="ops-rankings">{data.models.length ? data.models.map((model, index) => <div className="ops-rank" key={model.model}>
            <span className="ops-rank-number">{String(index + 1).padStart(2, "0")}</span>
            <div><div className="ops-rank-title"><strong title={model.model}>{model.model || t("operations.unavailable")}</strong><span>{formatCompact(model.tokens)}</span></div>
              <meter min={0} max={Math.max(1, totalTokens)} value={model.tokens} aria-label={`${model.model} ${t("operations.share")}`} />
              <small>{model.requests} {t("operations.requests")} · {t("operations.success")} {(model.succeeded / model.requests * 100).toFixed(1)}%</small>
            </div>
          </div>) : <p className="ops-empty">{t("operations.empty")}</p>}</div>
        </section>
      </div>
      <OperationsPerformance points={data.performance_series ?? []} range={range} />
      <section className="ops-panel">
        <div className="ops-heading"><div><h2>{t("operations.logs")} <span className="ops-count">{summary.requests}</span></h2><p>{t(pagination.page === 1 ? "operations.live" : "operations.frozen")} · {t("operations.updated")} {new Date(data.updated_at).toLocaleTimeString(i18n.language)}</p></div>
          <a className="ops-button" href={data.requests.length ? `/api/analytics/operations?${exportParams}` : undefined} download aria-disabled={!data.requests.length}>{t("operations.export")}</a>
        </div>
        {!data.requests.length ? <div className="ops-empty"><strong>{t("operations.empty")}</strong><p>{t(hasFilters ? "operations.noMatch" : "operations.emptyHint")}</p></div> :
          <div className="ops-table-scroll" tabIndex={0} aria-label={t("operations.logs")}>
            <table className="ops-table"><thead><tr>{["time", "model", "status", "input", "output", "elapsed", "speed", "details"].map(key => <th key={key} scope="col">{t(`operations.${key}`)}</th>)}</tr></thead>
              <tbody>{data.requests.map(request => <Fragment key={request.request_id}>
                <tr>
                  <td><time dateTime={request.timestamp}>{new Date(request.timestamp).toLocaleString(i18n.language, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time></td>
                  <td className="ops-model" title={request.model}>{request.model || "—"}</td>
                  <td><span className={`ops-status ${request.status}`}>{t(`operations.outcome.${request.status}`, { defaultValue: request.status })}</span></td>
                  <td>{number(request.input_tokens)}</td><td>{number(request.output_tokens)}</td>
                  <td>{duration(request.duration_seconds)}</td><td>{request.tokens_per_second == null ? "—" : `${request.tokens_per_second.toFixed(1)} t/s`}</td>
                  <td><button className="ops-text-button" type="button" aria-expanded={expanded === request.request_id} aria-controls={`request-${request.request_id}`} onClick={() => setExpanded(expanded === request.request_id ? null : request.request_id)}>{t(expanded === request.request_id ? "operations.close" : "operations.open")}</button></td>
                </tr>
                {expanded === request.request_id ? <tr id={`request-${request.request_id}`}><td colSpan={8}><dl className="ops-request-detail">
                  {[[t("operations.requestId"), request.request_id], [t("operations.endpoint"), request.endpoint], ["HTTP", request.http_status ?? "—"], [t("operations.precision"), t(`operations.${request.metric_precision}`, { defaultValue: request.metric_precision })], [t("operations.errorType"), request.error_type ?? "—"]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
                </dl></td></tr> : null}
              </Fragment>)}</tbody>
            </table>
          </div>}
        <footer className="ops-pagination"><small>{t("operations.durationNote")}</small><div>
          <select aria-label={t("operations.pageSize")} value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); refresh(); }}>
            {[10, 20, 50].map(size => <option key={size} value={size}>{t("operations.perPage", { count: size })}</option>)}
          </select>
          <button className="ops-button" type="button" disabled={data.page <= 1} onClick={() => { setPagination({ page: data.page - 1, snapshot: data.page === 2 ? undefined : data.snapshot_id }); setExpanded(null); }}>{t("operations.previous")}</button>
          <span>{t("operations.page", { page: data.page, count: data.page_count })}</span>
          <button className="ops-button" type="button" disabled={data.page >= data.page_count} onClick={() => { setPagination({ page: data.page + 1, snapshot: data.snapshot_id }); setExpanded(null); }}>{t("operations.next")}</button>
        </div></footer>
      </section>
    </> : null}
  </main>;
}
