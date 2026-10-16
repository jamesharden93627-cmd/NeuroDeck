import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useCodexAnalytics } from "../../hooks/useCodexAnalytics";
import type { CodexModelUsage, CodexWorkspaceUsage } from "../../types/codexAnalytics";
import type { TimeRange } from "../../types/dashboard";
import { formatCompact } from "../../utils/format";
import { formatAccountingBoundary } from "../../utils/usagePresentation";
import { CodexInsights } from "./CodexInsights";

interface CodexAnalyticsProps {
  range: TimeRange;
}

interface RankedUsageProps {
  label: string;
  usage: CodexModelUsage | CodexWorkspaceUsage;
  rank: number;
  meta: string;
}

function RankedUsage({ label, usage, rank, meta }: RankedUsageProps) {
  return (
    <li className="ledger-rank-row">
      <div className="ledger-rank-heading">
        <span>{String(rank).padStart(2, "0")}</span>
        <strong title={label}>{label}</strong>
        <b title={usage.total_tokens.toLocaleString()}>{formatCompact(usage.total_tokens)}</b>
      </div>
      <div className="ledger-rank-track" aria-hidden="true">
        <span style={{ width: `${Math.max(1.5, Math.min(100, usage.share_percent))}%` }} />
      </div>
      <small>{meta}</small>
    </li>
  );
}

/** 功能：把 Codex 持久化账本拆为模型、匿名工作区和匿名会话三个可核对维度。 */
export function CodexAnalytics({ range }: CodexAnalyticsProps) {
  const { t, i18n } = useTranslation();
  const { data, loading, error } = useCodexAnalytics(range);
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const dateTimeFormatter = useMemo(() => new Intl.DateTimeFormat(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }), [locale]);
  const rangeLabel = range === "24H" ? t("common.today") : range;
  const desktopEstimate = data?.period_comparison?.find(item => item.period === "utc_today");

  const context = loading && !data
    ? t("common.syncing")
    : error
      ? t("common.stale")
      : data
        ? t("codexAnalytics.snapshot", { id: data.snapshot_id })
        : t("codexAnalytics.localLedger");

  return (
    <section className="panel codex-ledger-panel" aria-labelledby="codex-ledger-title">
      <div className="panel-heading codex-ledger-heading">
        <div>
          <h2 id="codex-ledger-title">{t("codexAnalytics.title")}</h2>
          <p>{t("codexAnalytics.description", { range: rangeLabel })}</p>
        </div>
        <span className="panel-context">{context}</span>
      </div>

      {!data ? (
        <div className="ledger-empty" role="status">
          {error ? t("codexAnalytics.unavailable") : t("common.syncing")}
        </div>
      ) : (
        <>
          {/* 功能：完整数值与时间边界直接可查，不依赖 M/K 缩写推测统计范围。 */}
          <details className="usage-audit">
            <summary>{t("usageAudit.title")} · {data.summary.total_tokens.toLocaleString(locale)} Token</summary>
            <div className="usage-audit-body">
              <p><strong>{t("usageAudit.range")}</strong><br />
                {formatAccountingBoundary(data.local_start ?? data.start)} → {formatAccountingBoundary(data.local_end ?? data.updated_at)}
              </p>
              <p>{t("usageAudit.source")}</p>
              <p>{t("usageAudit.units")}</p>
              {desktopEstimate && (desktopEstimate.activity_events ?? 0) > 0 ? (
                <p className="usage-audit-callout">
                  <span>{t("usageAudit.desktopEstimate")}</span>
                  <strong>{(desktopEstimate.activity_tokens ?? 0).toLocaleString(locale)} Token</strong>
                  <small>{desktopEstimate.activity_events?.toLocaleString(locale)} {t("usageAudit.activityEvents")}</small>
                  <em>{t("usageAudit.desktopEstimateNote")}</em>
                </p>
              ) : null}
              {data.period_comparison ? <div className="usage-audit-scroll">
                <table>
                  <caption>{t("usageAudit.compare")}</caption>
                  <thead><tr><th>{t("usageAudit.period")}</th><th>{t("usageAudit.exact")}</th><th>{t("usageAudit.activityExact")}</th><th>{t("usageAudit.events")}</th></tr></thead>
                  <tbody>{data.period_comparison.map(item => <tr key={item.period}>
                    <td><strong>{t(`usageAudit.${item.period}`)}</strong><small>{formatAccountingBoundary(item.start)} → {formatAccountingBoundary(item.end)}</small></td>
                    <td>{item.total_tokens.toLocaleString(locale)}</td>
                    <td>{item.activity_tokens?.toLocaleString(locale) ?? "—"}</td>
                    <td>{item.events} / {item.sessions}</td>
                  </tr>)}</tbody>
                </table>
              </div> : null}
              <p>{t("usageAudit.compareNote")}</p>
            </div>
          </details>
          <dl className="ledger-summary" aria-label={t("codexAnalytics.summary")}>
            <div><dt>{t("codexAnalytics.totalTokens")}</dt><dd title={data.summary.total_tokens.toLocaleString(locale)}>{formatCompact(data.summary.total_tokens)}</dd></div>
            <div><dt>{t("codexAnalytics.sessions")}</dt><dd>{data.summary.sessions}</dd></div>
            <div><dt>{t("codexAnalytics.workspaces")}</dt><dd>{data.summary.workspaces}</dd></div>
            <div><dt>{t("codexAnalytics.models")}</dt><dd>{data.summary.models}</dd></div>
            <div><dt>{t("codexAnalytics.responses")}</dt><dd>{data.summary.completions}</dd></div>
            <div><dt>{t("codexAnalytics.cacheRatio")}</dt><dd>{data.summary.cache_ratio.toFixed(0)}%</dd></div>
          </dl>

          <CodexInsights data={data} />

          <div className="ledger-dimensions">
            <article className="ledger-dimension ledger-models">
              <header>
                <div><span className="eyeline">MODEL / 01</span><h3>{t("codexAnalytics.modelRanking")}</h3></div>
                <small>{t("codexAnalytics.share")}</small>
              </header>
              {data.models.length ? (
                <ol className="ledger-ranking">
                  {data.models.map((item, index) => (
                    <RankedUsage
                      key={item.model || "unknown-model"}
                      label={item.model || t("codexAnalytics.unknownModel")}
                      usage={item}
                      rank={index + 1}
                      meta={t("codexAnalytics.modelMeta", {
                        sessions: item.sessions,
                        completions: item.completions,
                        cached: formatCompact(item.cached_tokens),
                      })}
                    />
                  ))}
                </ol>
              ) : <div className="ledger-column-empty">{t("codexAnalytics.noEvents")}</div>}
            </article>

            <article className="ledger-dimension ledger-workspaces">
              <header>
                <div><span className="eyeline">WORKSPACE / 02</span><h3>{t("codexAnalytics.workspaceRanking")}</h3></div>
                <small>{t("codexAnalytics.anonymous")}</small>
              </header>
              {data.workspaces.length ? (
                <ol className="ledger-ranking">
                  {data.workspaces.map((item, index) => (
                    <RankedUsage
                      key={item.workspace_id || "unassigned-workspace"}
                      label={item.workspace || t("codexAnalytics.unassigned")}
                      usage={item}
                      rank={index + 1}
                      meta={t("codexAnalytics.workspaceMeta", {
                        sessions: item.sessions,
                        id: item.workspace_id ? item.workspace_id.slice(0, 6).toUpperCase() : "—",
                      })}
                    />
                  ))}
                </ol>
              ) : <div className="ledger-column-empty">{t("codexAnalytics.noEvents")}</div>}
            </article>

            <article className="ledger-dimension ledger-sessions">
              <header>
                <div><span className="eyeline">SESSION / 03</span><h3>{t("codexAnalytics.sessionRanking")}</h3></div>
                <small>{t("codexAnalytics.topSessions")}</small>
              </header>
              {data.sessions.length ? (
                <div className="ledger-session-scroll">
                  <table>
                    <thead><tr>
                      <th>{t("codexAnalytics.session")}</th>
                      <th>{t("codexAnalytics.workspace")}</th>
                      <th>{t("codexAnalytics.model")}</th>
                      <th>{t("codexAnalytics.tokens")}</th>
                    </tr></thead>
                    <tbody>
                      {data.sessions.map((session) => (
                        <tr key={session.session_id}>
                          <td><strong>{session.session}</strong><small>{session.completions} {t("codexAnalytics.events")}</small></td>
                          <td title={session.workspace || t("codexAnalytics.unassigned")}>{session.workspace || t("codexAnalytics.unassigned")}</td>
                          <td title={session.model || t("codexAnalytics.unknownModel")}>{session.model || t("codexAnalytics.unknownModel")}</td>
                          <td><strong title={session.total_tokens.toLocaleString()}>{formatCompact(session.total_tokens)}</strong><time dateTime={session.last_active}>{dateTimeFormatter.format(new Date(session.last_active))}</time></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div className="ledger-column-empty">{t("codexAnalytics.noEvents")}</div>}
            </article>
          </div>
          <footer className="ledger-privacy">{t("codexAnalytics.privacy")}</footer>
        </>
      )}
    </section>
  );
}
