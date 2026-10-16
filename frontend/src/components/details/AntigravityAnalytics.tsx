import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useAntigravityAnalytics } from "../../hooks/useAntigravityAnalytics";
import type { CodexModelUsage, CodexWorkspaceUsage } from "../../types/codexAnalytics";
import type { TimeRange } from "../../types/dashboard";
import { formatCompact } from "../../utils/format";

interface AntigravityAnalyticsProps {
  range: TimeRange;
}

interface RankedUsageProps {
  label: string;
  usage: CodexModelUsage | CodexWorkspaceUsage;
  rank: number;
  meta: string;
  tintColor?: string;
}

function RankedUsage({ label, usage, rank, meta, tintColor }: RankedUsageProps) {
  return (
    <li className="ledger-rank-row">
      <div className="ledger-rank-heading">
        <span>{String(rank).padStart(2, "0")}</span>
        <strong title={label}>{label}</strong>
        <b title={usage.total_tokens.toLocaleString()}>{formatCompact(usage.total_tokens)}</b>
      </div>
      <div className="ledger-rank-track" aria-hidden="true">
        <span
          style={{
            width: `${Math.max(1.5, Math.min(100, usage.share_percent))}%`,
            background: tintColor ?? "var(--v-amber)",
          }}
        />
      </div>
      <small>{meta}</small>
    </li>
  );
}

/** 功能：把 Antigravity 持久化账本拆为模型、项目工作区和会话三个可核对维度。 */
export function AntigravityAnalytics({ range }: AntigravityAnalyticsProps) {
  const { t, i18n } = useTranslation();
  const { data, loading, error } = useAntigravityAnalytics(range);
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US";
  const isZh = i18n.resolvedLanguage?.startsWith("zh") ?? false;
  const dateTimeFormatter = useMemo(() => new Intl.DateTimeFormat(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }), [locale]);
  const rangeLabel = range === "24H" ? t("common.today") : range;

  const context = loading && !data
    ? t("common.syncing")
    : error
      ? t("common.stale")
      : data
        ? `SNAPSHOT #${data.snapshot_id}`
        : "LOCAL LEDGER";

  return (
    <section className="panel codex-ledger-panel" aria-labelledby="ag-ledger-title">
      <div className="panel-heading codex-ledger-heading">
        <div>
          <h2 id="ag-ledger-title">
            {isZh ? "Antigravity 用量下钻账本" : "Antigravity Usage Breakdown"}
          </h2>
          <p>
            {isZh
              ? `${rangeLabel} · 洞察 Token 产生在哪些工作区项目、模型与具体会话。`
              : `${rangeLabel} · Inspect which models, workspaces and sessions drive token usage.`}
          </p>
        </div>
        <span className="panel-context">{context}</span>
      </div>

      {!data ? (
        <div className="ledger-empty" role="status">
          {error
            ? (isZh ? "Antigravity 账本分析暂不可用" : "Antigravity ledger analysis unavailable")
            : t("common.syncing")}
        </div>
      ) : (
        <>
          <dl className="ledger-summary" aria-label="Antigravity Ledger Summary">
            <div>
              <dt>{isZh ? "全量吞吐" : "Total Tokens"}</dt>
              <dd title={data.summary.total_tokens.toLocaleString(locale)}>
                {formatCompact(data.summary.total_tokens)}
              </dd>
            </div>
            <div>
              <dt>{isZh ? "活跃会话" : "Sessions"}</dt>
              <dd>{data.summary.sessions}</dd>
            </div>
            <div>
              <dt>{isZh ? "工作区项目" : "Workspaces"}</dt>
              <dd>{data.summary.workspaces}</dd>
            </div>
            <div>
              <dt>{isZh ? "涉及模型" : "Models"}</dt>
              <dd>{data.summary.models}</dd>
            </div>
            <div>
              <dt>{isZh ? "响应次数" : "Responses"}</dt>
              <dd>{data.summary.completions}</dd>
            </div>
            <div>
              <dt>{isZh ? "上下文缓存率" : "Cache Ratio"}</dt>
              <dd>{data.summary.cache_ratio.toFixed(0)}%</dd>
            </div>
          </dl>

          <div className="ledger-dimensions">
            {/* 1. 模型分布 */}
            <article className="ledger-dimension ledger-models">
              <header>
                <div>
                  <span className="eyeline">MODEL / 01</span>
                  <h3>{isZh ? "模型用量分布" : "Model Distribution"}</h3>
                </div>
                <small>{isZh ? "用量占比" : "Token Share"}</small>
              </header>
              {data.models.length ? (
                <ol className="ledger-ranking">
                  {data.models.map((item, index) => (
                    <RankedUsage
                      key={item.model || "unknown-model"}
                      label={item.model || (isZh ? "未知模型" : "Unknown Model")}
                      usage={item}
                      rank={index + 1}
                      meta={isZh
                        ? `${item.sessions} 会话 · ${item.completions} 次响应 · ${formatCompact(item.cached_tokens)} 缓存`
                        : `${item.sessions} sess · ${item.completions} resp · ${formatCompact(item.cached_tokens)} cached`}
                      tintColor="#f59e0b"
                    />
                  ))}
                </ol>
              ) : (
                <div className="ledger-column-empty">
                  {isZh ? "此范围内暂无事件" : "No events in range"}
                </div>
              )}
            </article>

            {/* 2. 工作区项目分布 */}
            <article className="ledger-dimension ledger-workspaces">
              <header>
                <div>
                  <span className="eyeline">WORKSPACE / 02</span>
                  <h3>{isZh ? "工作区项目分布" : "Workspace Projects"}</h3>
                </div>
                <small>{isZh ? "本地代码库" : "Projects"}</small>
              </header>
              {data.workspaces.length ? (
                <ol className="ledger-ranking">
                  {data.workspaces.map((item, index) => (
                    <RankedUsage
                      key={item.workspace_id || "unassigned-workspace"}
                      label={item.workspace || (isZh ? "未命名工作区" : "Unassigned")}
                      usage={item}
                      rank={index + 1}
                      meta={isZh ? `${item.sessions} 个会话` : `${item.sessions} sessions`}
                      tintColor="#06b6d4"
                    />
                  ))}
                </ol>
              ) : (
                <div className="ledger-column-empty">
                  {isZh ? "此范围内暂无事件" : "No events in range"}
                </div>
              )}
            </article>

            {/* 3. 重度会话排行榜 */}
            <article className="ledger-dimension ledger-sessions">
              <header>
                <div>
                  <span className="eyeline">SESSION / 03</span>
                  <h3>{isZh ? "高用量会话排行" : "Heavy Sessions"}</h3>
                </div>
                <small>TOP 12</small>
              </header>
              {data.sessions.length ? (
                <div className="ledger-session-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{isZh ? "会话" : "Session"}</th>
                        <th>{isZh ? "项目" : "Workspace"}</th>
                        <th>{isZh ? "模型" : "Model"}</th>
                        <th>{isZh ? "用量 / 最后活跃" : "Tokens / Active"}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.sessions.map((session) => (
                        <tr key={session.session_id}>
                          <td>
                            <strong>{session.session}</strong>
                            <small>
                              {session.completions} {isZh ? "次响应" : "resp"}
                            </small>
                          </td>
                          <td title={session.workspace}>
                            {session.workspace || "—"}
                          </td>
                          <td title={session.model}>
                            {session.model || "—"}
                          </td>
                          <td>
                            <strong title={session.total_tokens.toLocaleString()}>
                              {formatCompact(session.total_tokens)}
                            </strong>
                            <time dateTime={session.last_active}>
                              {dateTimeFormatter.format(new Date(session.last_active))}
                            </time>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="ledger-column-empty">
                  {isZh ? "此范围内暂无事件" : "No events in range"}
                </div>
              )}
            </article>
          </div>
          <footer className="ledger-privacy">
            {isZh
              ? "本地只读安全：仅提取会话 Token 数值与工作区目录名；绝不读取对话正文、工具调用与代码细节。"
              : "Local read-only: Only numeric usage, model names, and workspace folder basenames are collected; prompt and response texts are never read."}
          </footer>
        </>
      )}
    </section>
  );
}
