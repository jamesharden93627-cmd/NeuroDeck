import type { SignalEvent } from "../../types/dashboard";
import { formatTime } from "../../utils/format";
import { useTranslation } from "react-i18next";

interface SignalsTableProps {
  signals: SignalEvent[];
}

const signalEventKeys: Record<string, string> = {
  "TOKEN UPDATE": "signals.events.tokenUpdate",
  "INFERENCE COMPLETE": "signals.events.inferenceComplete",
  "MODEL LOADED": "signals.events.modelLoaded",
  "HIGH UTILIZATION": "signals.events.highUtilization",
  "THERMAL STABLE": "signals.events.thermalStable",
  "COLLECTORS READY": "signals.events.collectorsReady",
  "REQUEST COMPLETE": "signals.events.requestComplete",
};

export function SignalsTable({ signals }: SignalsTableProps) {
  const { t, i18n } = useTranslation();
  const isChinese = i18n.resolvedLanguage?.startsWith("zh");

  // 处理：只翻译可识别的系统事件与单位，模型名和原始诊断内容保持不变。
  const translateEvent = (event: string) => signalEventKeys[event] ? t(signalEventKeys[event]) : event;
  const translateDetail = (detail: string) => isChinese
    ? detail.replace(/\btokens?\b/gi, "Token").replace(/\bsources active\b/gi, "个数据源活跃")
    : detail;

  return (
    <section className="panel signals-panel">
      <div className="panel-heading compact-heading"><h2>{t("signals.title")}</h2><span className="panel-context">{t("signals.autoScan")}</span></div>
      <div className="signals-scroll">
        <table>
          <thead><tr><th>{t("signals.time")}</th><th>{t("signals.source")}</th><th>{t("signals.event")}</th><th>{t("signals.details")}</th></tr></thead>
          <tbody>
            {signals.length ? signals.map((signal, index) => (
              <tr key={`${signal.timestamp}-${signal.event}-${index}`}>
                <td><span className={`signal-dot tone-${signal.severity}`} />{formatTime(signal.timestamp)}</td>
                <td>{signal.source}</td><td>{translateEvent(signal.event)}</td><td>{translateDetail(signal.detail)}</td>
              </tr>
            )) : (
              <tr><td colSpan={4} className="empty-row">{t("signals.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
