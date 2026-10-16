import type { OverviewSnapshot, TimeRange, TokenActivityPoint, TrendPoint } from "../../types/dashboard";
import { formatCompact, formatDuration } from "../../utils/format";
import { getRangeTokenTotal } from "../../utils/tokens";
import { useTranslation } from "react-i18next";
import { AntigravityIcon, CodeIcon, HardwareIcon, ModelIcon, OverviewIcon } from "../icons/Icons";
import { Sparkline } from "../common/Sparkline";
import { StatusDot } from "../common/StatusDot";

interface KpiStripProps {
  snapshot: OverviewSnapshot;
  range: TimeRange;
  history: TrendPoint[];
  tokenActivity: TokenActivityPoint[];
}

export function KpiStrip({ snapshot, range, history, tokenActivity }: KpiStripProps) {
  const { t, i18n } = useTranslation();
  const hardwareTail = history.slice(-18);
  const tokenTail = tokenActivity.slice(-18);
  const gpuWarning = snapshot.hardware.gpu_usage >= 90;
  const ollamaRangeTotal = getRangeTokenTotal(snapshot.ollama, range);
  const codexRangeTotal = getRangeTokenTotal(snapshot.codex, range);
  const antigravityRangeTotal = getRangeTokenTotal(snapshot.antigravity, range);
  const items = [
    {
      label: t("kpi.ollamaTokens"),
      icon: ModelIcon,
      value: formatCompact(ollamaRangeTotal),
      exactValue: ollamaRangeTotal,
      unit: range === "24H" ? t("kpi.tokensToday") : t("kpi.rangeTotal", { range }),
      online: snapshot.ollama.online,
      values: tokenTail.map((point) => point.ollama_tokens),
    },
    {
      label: t("kpi.codexTokens"),
      icon: CodeIcon,
      value: formatCompact(codexRangeTotal),
      exactValue: codexRangeTotal,
      unit: range === "24H"
        ? t("kpi.outputToday", { value: formatCompact(snapshot.codex.output_tokens) })
        : t("kpi.rangeTotal", { range }),
      online: snapshot.codex.online,
      values: tokenTail.map((point) => point.codex_tokens),
    },
    {
      label: t("kpi.antigravityTokens", { defaultValue: "Antigravity Tokens" }),
      icon: AntigravityIcon,
      value: formatCompact(antigravityRangeTotal),
      exactValue: antigravityRangeTotal,
      unit: range === "24H"
        ? t("kpi.outputToday", { value: formatCompact(snapshot.antigravity.output_tokens) })
        : t("kpi.rangeTotal", { range }),
      online: snapshot.antigravity.online,
      values: tokenTail.map((point) => point.antigravity_tokens ?? 0),
    },
    {
      label: t("kpi.gpuLoad"),
      icon: HardwareIcon,
      value: snapshot.hardware.gpu_available ? `${snapshot.hardware.gpu_usage.toFixed(0)}%` : "—",
      unit: snapshot.hardware.gpu_available ? snapshot.hardware.gpu_name : t("kpi.notDetected"),
      online: snapshot.hardware.gpu_available,
      warning: gpuWarning,
      values: hardwareTail.map((point) => point.gpu_usage),
    },
    {
      label: t("kpi.systemUptime"),
      icon: OverviewIcon,
      value: formatDuration(snapshot.hardware.uptime_seconds, i18n.resolvedLanguage),
      unit: t("kpi.collectorOnline"),
      online: true,
      values: hardwareTail.map((point) => point.cpu_usage),
    },
  ];

  return (
    <section className="kpi-strip" aria-label={t("overview.operationalSummary")}>
      {items.map(({ label, icon: Icon, value, exactValue, unit, online, warning, values }) => (
        <article className="kpi-item" key={label}>
          <div className="kpi-heading">
            <span className="kpi-label"><Icon />{label}</span>
            <StatusDot online={online} warning={warning} label={warning ? t("common.high") : undefined} />
          </div>
          <div className="kpi-body">
            <div>
              <strong title={exactValue?.toLocaleString()}>{value}</strong>
              <span>{unit}</span>
            </div>
            <Sparkline values={values} warning={warning} />
          </div>
        </article>
      ))}
    </section>
  );
}
