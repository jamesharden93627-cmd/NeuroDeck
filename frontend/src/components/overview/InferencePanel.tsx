import { useTranslation } from "react-i18next";

import type { ProviderSnapshot, TrendPoint } from "../../types/dashboard";
import { formatCompact, formatPercent } from "../../utils/format";
import { Sparkline } from "../common/Sparkline";
import { StatusDot } from "../common/StatusDot";

interface InferencePanelProps {
  ollama: ProviderSnapshot;
  codex: ProviderSnapshot;
  antigravity?: ProviderSnapshot;
  history: TrendPoint[];
}

interface ProviderInferenceCardProps {
  provider: ProviderSnapshot;
  speeds: number[];
}

/** 功能：独立展示单个推理提供方，不再通过“活跃优先”隐藏另一个提供方。 */
function ProviderInferenceCard({ provider, speeds }: ProviderInferenceCardProps) {
  const { t } = useTranslation();
  const estimated = provider.metric_precision === "estimated";
  const hasContextLimit = provider.context_size > 0;
  const contextPercent = formatPercent(provider.context_used, provider.context_size);
  const statusLabel = t(`common.${provider.status}`, {
    defaultValue: provider.status.toUpperCase(),
  });
  const modelLabel = provider.model === "No model loaded"
    ? t("inference.noModel")
    : provider.model;
  const supportsThroughput = provider.provider === "ollama";

  return (
    <article className={`inference-provider-card provider-${provider.provider}`}>
      <div className="provider-card-heading">
        <strong>{provider.provider.toUpperCase()}</strong>
        <StatusDot online={provider.online} label={statusLabel} />
      </div>
      <div className="provider-card-main">
        <span className="eyeline">{t("inference.currentModel")}</span>
        <strong className="model-name" title={modelLabel}>{modelLabel}</strong>
        <div className="context-row">
          <span>{t("inference.context")}</span>
          <strong>{formatCompact(provider.context_used)} <small>/ {hasContextLimit ? formatCompact(provider.context_size) : "—"}</small></strong>
        </div>
        <div className="progress-track"><span style={{ width: `${hasContextLimit ? contextPercent : 0}%` }} /></div>
        <span className="progress-value">{hasContextLimit ? `${contextPercent.toFixed(0)}%` : "—"}</span>
      </div>
      <div className="provider-card-speed">
        <span className="eyeline">{t(estimated ? "inference.estimatedSpeed" : "inference.speed")}</span>
        <strong>
          {supportsThroughput
            ? `${estimated ? "~" : ""}${provider.tokens_per_second.toFixed(1)}`
            : "—"}
          <small>{supportsThroughput ? " TOK/S" : ""}</small>
        </strong>
        {supportsThroughput
          ? <Sparkline values={speeds} />
          : <small className="metadata-only">{t("inference.metadataOnly")}</small>}
      </div>
      <dl className="inference-details">
        <div><dt>{t(provider.provider === "ollama" ? "inference.requests" : "inference.sessions")}</dt><dd>{provider.sessions_today}</dd></div>
        <div><dt>{t("inference.input")}</dt><dd>{formatCompact(provider.input_tokens)}</dd></div>
        <div><dt>{t("inference.output")}</dt><dd>{formatCompact(provider.output_tokens)}</dd></div>
        <div><dt>{t("inference.cached")}</dt><dd>{formatCompact(provider.cached_tokens)}</dd></div>
        <div><dt>{t("inference.state")}</dt><dd>{statusLabel}</dd></div>
        <div><dt>{t("inference.provider")}</dt><dd>{provider.online ? t("common.online") : t("common.offline")}</dd></div>
      </dl>
    </article>
  );
}

/** 功能：Ollama、Codex 与 Antigravity 并列显示。 */
export function InferencePanel({ ollama, codex, antigravity, history }: InferencePanelProps) {
  const { t } = useTranslation();
  const ollamaSpeeds = history.slice(-28).map((point) => point.ollama_tokens_per_second);

  return (
    <div className="inference-column">
      <section className="panel inference-panel">
        <div className="panel-heading compact-heading">
          <h2>{t("inference.title")}</h2>
          <span className="panel-context">{t("inference.providers")}</span>
        </div>
        <div className="inference-provider-grid">
          <ProviderInferenceCard provider={ollama} speeds={ollamaSpeeds} />
          <ProviderInferenceCard provider={codex} speeds={[]} />
          {antigravity && <ProviderInferenceCard provider={antigravity} speeds={[]} />}
        </div>
      </section>
    </div>
  );
}
